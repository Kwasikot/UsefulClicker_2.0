"""OCR preprocessing utilities for EasyOCR output.

Provides normalization, parsing, grouping, scoring and prompt building
for LLM reranking of OCR-detected texts.

Functions are pure-Python and do not call external services.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re
import json
import math
import sys
from typing import List, Dict, Tuple, Any, Optional
from collections import defaultdict


@dataclass
class Token:
    id: int
    raw_text: str
    text: str
    conf: float
    bbox: Tuple[int, int, int, int]
    cx: float
    cy: float
    w: int
    h: int


@dataclass
class Line:
    line_id: int
    text: str
    raw_texts: List[str]
    token_ids: List[int]
    avg_conf: float
    bbox: Tuple[int, int, int, int]
    cx: float
    cy: float


_RE_BBOX = re.compile(r"\(\s*(?P<x>-?\d+)\s*,\s*(?P<y>-?\d+)\s*\)")


def normalize_text(s: str) -> str:
    """Normalize OCR text: lowercase, trim, fix common OCR errors.

    Replacements: '|' -> 'l', '+ +' -> '++', em-dash-like to '-', collapse spaces.
    """
    if s is None:
        return ""
    s = str(s)
    s = s.strip()
    # lowercase
    s = s.lower()
    # common fixes
    s = s.replace('|', 'l')
    s = s.replace('+ +', '++')
    s = s.replace('\u2014', '-')
    s = s.replace('\u2013', '-')
    # collapse multiple spaces
    s = re.sub(r'\s+', ' ', s)
    return s


def parse_bbox(points: List[str]) -> Tuple[int, int, int, int]:
    """Parse list of strings like ['(x1,y1)','(x2,y2)',...] to (xmin,ymin,xmax,ymax).
    Non-integer values are coerced to int; malformed points raise ValueError.
    """
    xs = []
    ys = []
    for p in points:
        if not isinstance(p, str):
            raise ValueError(f'Invalid bbox point: {p!r}')
        m = _RE_BBOX.search(p)
        if not m:
            # try to eval fallback like "[x,y]"
            raise ValueError(f'Cannot parse bbox point: {p!r}')
        xs.append(int(m.group('x')))
        ys.append(int(m.group('y')))
    xmin = min(xs)
    ymin = min(ys)
    xmax = max(xs)
    ymax = max(ys)
    return (xmin, ymin, xmax, ymax)


def parse_ocr_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """Parse textual OCR lines (as produced by easyocr formatting) into token dicts.

    Expected line examples:
      "Some text (conf=0.92) bbox: ['(26,5)', '(285,5)', '(285,26)', '(26,26)']"

    Returns list of token dicts compatible with downstream grouping.
    """
    tokens: List[Dict[str, Any]] = []
    for idx, line in enumerate(lines):
        raw = line.strip()
        if not raw:
            continue
        # try to extract conf and bbox
        # conf: look for (conf=number)
        conf_m = re.search(r"\(\s*conf\s*=\s*([0-9]*\.?[0-9]+)\s*\)", raw, flags=re.IGNORECASE)
        bbox_m = re.search(r"bbox\s*:\s*(\[.*\])", raw, flags=re.IGNORECASE)
        # raw_text is portion before '(conf=' or 'bbox:'
        cut_at = None
        cm = re.search(r"\(\s*conf\s*=", raw, flags=re.IGNORECASE)
        bm = re.search(r"bbox\s*:\s*", raw, flags=re.IGNORECASE)
        if cm:
            cut_at = cm.start()
        elif bm:
            cut_at = bm.start()
        raw_text = raw if cut_at is None else raw[:cut_at].strip()
        try:
            conf = float(conf_m.group(1)) if conf_m else 0.0
        except Exception:
            conf = 0.0
        bbox_list: List[str] = []
        if bbox_m:
            try:
                # evaluate the list literal safely by extracting occurrences of '(x,y)'
                pts = _RE_BBOX.findall(bbox_m.group(1))
                # rebuild as strings
                bbox_list = [f"({x},{y})" for x, y in pts]
            except Exception:
                bbox_list = []
        try:
            if bbox_list:
                bx = parse_bbox(bbox_list)
            else:
                raise ValueError('no bbox')
        except Exception:
            # skip unparseable entries but warn
            print(f'Warning: cannot parse bbox or conf in line: {raw!r}', file=sys.stderr)
            continue
        xmin, ymin, xmax, ymax = bx
        w = xmax - xmin
        h = ymax - ymin
        cx = xmin + w / 2.0
        cy = ymin + h / 2.0
        tok = {
            'id': idx,
            'raw_text': raw_text,
            'text': normalize_text(raw_text),
            'conf': conf,
            'bbox': [xmin, ymin, xmax, ymax],
            'cx': cx,
            'cy': cy,
            'w': w,
            'h': h,
        }
        tokens.append(tok)
    return tokens


def _vertical_overlap(a: Tuple[int,int,int,int], b: Tuple[int,int,int,int]) -> int:
    # overlap in pixels between vertical spans
    ay1, ay2 = a[1], a[3]
    by1, by2 = b[1], b[3]
    inter = max(0, min(ay2, by2) - max(ay1, by1))
    return inter


def group_into_lines(tokens: List[Dict[str, Any]],
                     y_overlap_ratio: float = 0.6,
                     y_merge_tol_px: int = 4) -> List[Dict[str, Any]]:
    """Group tokens into text lines by vertical overlap and center proximity.

    Returns list of line dicts with aggregated bbox, avg_conf, concatenated normalized text.
    """
    if not tokens:
        return []
    # copy tokens and sort by cy
    toks = sorted(tokens, key=lambda t: (t['cy'], t['cx']))
    groups: List[List[Dict[str, Any]]] = []
    for t in toks:
        placed = False
        for g in groups:
            # check overlap with any token in group
            for gt in g:
                inter = _vertical_overlap(tuple(t['bbox']), tuple(gt['bbox']))
                min_h = min(t['h'] or 1, gt['h'] or 1)
                if min_h <= 0:
                    continue
                if inter >= y_overlap_ratio * min_h and abs(t['cy'] - gt['cy']) <= y_merge_tol_px:
                    g.append(t)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            groups.append([t])

    lines: List[Dict[str, Any]] = []
    for lid, g in enumerate(groups):
        # sort tokens in line by x
        g_sorted = sorted(g, key=lambda x: x['cx'])
        xs = [tt['bbox'][0] for tt in g_sorted] + [tt['bbox'][2] for tt in g_sorted]
        ys = [tt['bbox'][1] for tt in g_sorted] + [tt['bbox'][3] for tt in g_sorted]
        xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
        w = xmax - xmin
        h = ymax - ymin
        cx = xmin + w / 2.0
        cy = ymin + h / 2.0
        raw_texts = [tt['raw_text'] for tt in g_sorted]
        texts = [tt['text'] for tt in g_sorted if tt.get('text')]
        line_text = ' '.join([t for t in texts if t])
        avg_conf = float(sum(tt.get('conf', 0.0) for tt in g_sorted) / max(1, len(g_sorted)))
        line = {
            'line_id': lid,
            'text': line_text,
            'raw_texts': raw_texts,
            'token_ids': [tt['id'] for tt in g_sorted],
            'avg_conf': avg_conf,
            'bbox': [xmin, ymin, xmax, ymax],
            'cx': cx,
            'cy': cy,
        }
        lines.append(line)

    # sort lines by reading order: top to bottom (y), then left to right (x)
    lines.sort(key=lambda L: (L['bbox'][1], L['bbox'][0]))
    return lines


def _levenshtein(a: str, b: str) -> int:
    # simple DP
    la, lb = len(a), len(b)
    if la == 0:
        return lb
    if lb == 0:
        return la
    prev = list(range(lb+1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0]*lb
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j-1] + 1, prev[j-1] + cost)
        prev = cur
    return prev[lb]


def fuzzy_ratio(a: str, b: str) -> float:
    """Return similarity 0..100 between strings. Try rapidfuzz if present.
    Otherwise use token-sort style ratio based on normalized levenshtein.
    """
    a = normalize_text(a)
    b = normalize_text(b)
    try:
        from rapidfuzz.fuzz import token_sort_ratio
        return float(token_sort_ratio(a, b))
    except Exception:
        # token-sort like: sort tokens alphabetically
        def norm_tokens(s: str) -> str:
            toks = [t for t in re.split(r"\s+", s) if t]
            toks.sort()
            return ' '.join(toks)
        sa = norm_tokens(a)
        sb = norm_tokens(b)
        if not sa and not sb:
            return 100.0
        if not sa or not sb:
            return 0.0
        dist = _levenshtein(sa, sb)
        maxlen = max(len(sa), len(sb))
        if maxlen == 0:
            return 100.0
        ratio = max(0.0, 1.0 - dist / maxlen)
        return ratio * 100.0


def score_line(line: Dict[str, Any], intent: str) -> float:
    """Compute score combining fuzzy, avg_conf and bbox area boost.
    Returns numeric score (higher = better).
    """
    fuzzy = fuzzy_ratio(line.get('text', ''), intent)
    conf = float(line.get('avg_conf', 0.0) or 0.0) * 100.0
    bbox = line.get('bbox', [0,0,0,0])
    area = max(1, (bbox[2]-bbox[0]) * (bbox[3]-bbox[1]))
    area_boost = min(30.0, (math.sqrt(area))/10.0)
    score = 0.8 * fuzzy + 0.1 * conf + 0.1 * area_boost
    return float(score)


def rank_candidates(lines: List[Dict[str, Any]], intent: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """Filter, score, and return top_k candidate lines with 'score' field.
    Ignores empty text, area < 15 or avg_conf < 0.25.
    """
    cands = []
    for L in lines:
        text = (L.get('text') or '').strip()
        if not text:
            continue
        bbox = L.get('bbox', [0,0,0,0])
        area = max(0, (bbox[2]-bbox[0])*(bbox[3]-bbox[1]))
        if area < 15:
            continue
        if float(L.get('avg_conf',0.0)) < 0.25:
            continue
        sc = score_line(L, intent)
        Lc = dict(L)
        Lc['score'] = sc
        cands.append(Lc)
    cands.sort(key=lambda x: x['score'], reverse=True)
    return cands[:top_k]


def build_llm_prompt(candidates: List[Dict[str, Any]], intent: str) -> str:
    """Build a compact prompt for LLM rerank/selection. Exclude coordinates.

    For each candidate include [ID=<line_id>] text="..." context_hint="..."
    End with instruction to return only the ID number or NONE.
    """
    lines = []
    header = "You are a helper that selects the best match for the user's intent from OCR-detected text snippets."
    lines.append(header)
    lines.append(f"Intent: {intent}")
    lines.append('Candidates:')
    for c in candidates:
        lid = c.get('line_id')
        text = c.get('text','').strip()
        context = ''
        raw = c.get('raw_texts')
        if raw:
            context = ' | '.join([r.strip() for r in raw if r.strip()])[:120]
        lines.append(f'[ID={lid}] text="{text}" context_hint="{context}" score={c.get("score"):.2f}')
    lines.append('')
    lines.append("Instructions: Review the candidates and return the single ID (number) of the best match for the intent. If none match, return NONE.")
    # Also provide a short Russian line to enforce output format
    lines.append("Format: Верни только ID (число) лучшего совпадения; если ни один не подходит — верни 'NONE'.")
    return '\n'.join(lines)


def _demo():
    sample = [
"*d: Projects | UsefulClicker_2 Otperceive (conf=0.5865894764688891) bbox: ['(26,5)', '(285,5)', '(285,26)', '(26,26)']",
"node_promttxt (conf=0.925656959369695) bbox: ['(289,9)', '(395,9)', '(395,25)', '(289,25)']",
"Notepad+ + (conf=0.9482106320445134) bbox: ['(405,7)', '(485,7)', '(485,25)', '(405,25)']",
"Eile (conf=0.967438614596726) bbox: ['(7,33)', '(35,33)', '(35,51)', '(7,51)']",
"Edit (conf=0.9999983310699463) bbox: ['(47,33)', '(79,33)', '(79,53)', '(47,53)']",
"Search (conf=0.9999990753271193) bbox: ['(93,35)', '(141,35)', '(141,53)', '(93,53)']",
    ]
    tokens = parse_ocr_lines(sample)
    lines = group_into_lines(tokens)
    cands = rank_candidates(lines, intent='open search menu', top_k=8)
    prompt = build_llm_prompt(cands, intent='open search menu')
    out = {
        'tokens': tokens,
        'lines': lines,
        'candidates': cands,
        'llm_prompt': prompt,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', '-i', type=str, help='Input OCR text file (one line each)')
    ap.add_argument('--intent', '-t', type=str, default='', help='User intent string')
    ap.add_argument('--topk', type=int, default=8)
    ap.add_argument('--output', '-o', type=str, help='Output JSON file')
    ap.add_argument('--demo', action='store_true')
    args = ap.parse_args(argv)
    if args.demo:
        _demo(); return
    if not args.input:
        print('Either --input or --demo must be provided', file=sys.stderr); return
    with open(args.input, encoding='utf-8') as f:
        raw_lines = [l.rstrip('\n') for l in f]
    tokens = parse_ocr_lines(raw_lines)
    lines = group_into_lines(tokens)
    cands = rank_candidates(lines, intent=args.intent or '', top_k=args.topk)
    prompt = build_llm_prompt(cands, intent=args.intent or '')
    out = {'tokens': tokens, 'lines': lines, 'candidates': cands, 'llm_prompt': prompt}
    s = json.dumps(out, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(s)
    else:
        print(s)


if __name__ == '__main__':
    main()
