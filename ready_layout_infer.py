#!/usr/bin/env python3
"""Layout inference helper that groups OCR tokens into lines using off-the-shelf detectors.

The script tries the following detectors in order:
 - HuggingFace object-detection model (microsoft/dit-base-finetuned-doclaynet) via transformers
 - layoutparser Detectron2 PubLayNet model
 - fallback CV baseline (binarization + contours)

It accepts OCR tokens (from JSON) or can run EasyOCR inline (--run-ocr).
Outputs JSON with image_size, blocks and grouped lines. Optionally writes preview image.

Designed to be robust: optional packages are used only if present; otherwise fallback used.
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
from typing import List, Dict, Tuple, Any, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Optional: transformers/torch
try:
    from transformers import AutoImageProcessor, AutoModelForObjectDetection
    HF_AVAILABLE = True
except Exception:
    HF_AVAILABLE = False

# Optional: layoutparser + detectron2
try:
    import layoutparser as lp
    LP_AVAILABLE = True
except Exception:
    LP_AVAILABLE = False

# Optional: easyocr
try:
    import easyocr
    EASYOCR_AVAILABLE = True
except Exception:
    EASYOCR_AVAILABLE = False


def load_image(path: str) -> Tuple[np.ndarray, Tuple[int,int]]:
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(path)
    h, w = img.shape[:2]
    return img, (w, h)


def detect_blocks_hf(img: np.ndarray) -> List[Dict[str, Any]]:
    """Try HF object detection model for layout. Returns list of blocks with bbox and score.
    bbox coordinates are ints [x1,y1,x2,y2]."""
    if not HF_AVAILABLE:
        raise RuntimeError('HF transformers not available')
    # use CPU auto model if torch available
    try:
        proc = AutoImageProcessor.from_pretrained('microsoft/dit-base-finetuned-doclaynet')
        model = AutoModelForObjectDetection.from_pretrained('microsoft/dit-base-finetuned-doclaynet')
    except Exception as e:
        raise RuntimeError(f'HF model load failed: {e}')
    # transformers expects PIL
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    inputs = proc(images=pil, return_tensors='pt')
    with np.errstate(all='ignore'):
        outputs = model(**inputs)
    # postprocess using processor
    try:
        target_sizes = torch.tensor([pil.size[::-1]])
        results = proc.post_process_object_detection(outputs, target_sizes=target_sizes, threshold=0.5)[0]
    except Exception:
        # fallback: try using outputs directly
        results = []
    blocks: List[Dict[str, Any]] = []
    for i, (score, label, box) in enumerate(zip(results['scores'], results['labels'], results['boxes'])):
        x1, y1, x2, y2 = [int(float(v)) for v in box]
        blocks.append({'block_id': i+1, 'bbox': [x1, y1, x2, y2], 'type': str(int(label)), 'score': float(score)})
    return blocks


def detect_blocks_layoutparser(img: np.ndarray) -> List[Dict[str, Any]]:
    if not LP_AVAILABLE:
        raise RuntimeError('layoutparser not available')
    try:
        model = lp.Detectron2LayoutModel('lp://PubLayNet/faster_rcnn_R_50_FPN_3x/config')
    except Exception as e:
        raise RuntimeError(f'LP model load failed: {e}')
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    layout = model.detect(pil)
    blocks = []
    bid = 1
    for r in layout:
        x1, y1, x2, y2 = int(r.coordinates[0]), int(r.coordinates[1]), int(r.coordinates[2]), int(r.coordinates[3])
        blocks.append({'block_id': bid, 'bbox': [x1, y1, x2, y2], 'type': r.type if hasattr(r, 'type') else 'block', 'score': float(getattr(r, 'score', 1.0))})
        bid += 1
    return blocks


def detect_blocks_cv(img: np.ndarray, min_area: int = 1000) -> List[Dict[str, Any]]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.bitwise_not(th)
    # dilate to merge text into blocks
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 5))
    dil = cv2.dilate(th, kernel, iterations=2)
    contours, _ = cv2.findContours(dil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blocks = []
    bid = 1
    H, W = gray.shape[:2]
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area:
            continue
        x2, y2 = x + w, y + h
        # clip
        x, y, x2, y2 = max(0, x), max(0, y), min(W, x2), min(H, y2)
        blocks.append({'block_id': bid, 'bbox': [int(x), int(y), int(x2), int(y2)], 'type': 'block', 'score': 1.0})
        bid += 1
    # sort by y
    blocks.sort(key=lambda b: (b['bbox'][1], b['bbox'][0]))
    return blocks


def run_easyocr(img_path: str, langs: str = 'en') -> List[Dict[str, Any]]:
    if not EASYOCR_AVAILABLE:
        raise RuntimeError('easyocr not available')
    reader = easyocr.Reader([langs]) if isinstance(langs, str) else easyocr.Reader(langs)
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(img_path)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    res = reader.readtext(rgb)
    tokens = []
    for i, (bbox, text, conf) in enumerate(res):
        try:
            pts = [(int(p[0]), int(p[1])) for p in bbox]
        except Exception:
            pts = []
        if pts:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            xmin, ymin, xmax, ymax = min(xs), min(ys), max(xs), max(ys)
        else:
            xmin = ymin = xmax = ymax = 0
        tokens.append({'id': i, 'text': text, 'conf': float(conf), 'bbox': [int(xmin), int(ymin), int(xmax), int(ymax)]})
    return tokens


def load_ocr_json(path: str) -> List[Dict[str, Any]]:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    toks = data.get('tokens', [])
    # ensure ids and bbox present
    out = []
    for i, t in enumerate(toks):
        tid = t.get('id', i)
        text = t.get('text', '')
        conf = float(t.get('conf', 0.0) or 0.0)
        bbox = t.get('bbox') or [0,0,0,0]
        out.append({'id': int(tid), 'text': text, 'conf': conf, 'bbox': [int(b) for b in bbox]})
    return out


def token_centroid(tok: Dict[str, Any]) -> Tuple[float,float]:
    x1,y1,x2,y2 = tok['bbox']
    return ((x1+x2)/2.0, (y1+y2)/2.0)


def assign_tokens_to_blocks(tokens: List[Dict[str, Any]], blocks: List[Dict[str, Any]], assign_pad: int = 4) -> Dict[int, List[Dict[str,Any]]]:
    # map block_id -> list of tokens
    mapping: Dict[int, List[Dict[str, Any]]] = {b['block_id']: [] for b in blocks}
    # default unassigned bucket -1
    mapping[-1] = []
    for t in tokens:
        cx, cy = token_centroid(t)
        assigned = False
        for b in blocks:
            x1,y1,x2,y2 = b['bbox']
            if (cx >= x1 - assign_pad) and (cx <= x2 + assign_pad) and (cy >= y1 - assign_pad) and (cy <= y2 + assign_pad):
                mapping[b['block_id']].append(t)
                assigned = True
                break
        if not assigned:
            mapping[-1].append(t)
    return mapping


def group_tokens_into_lines(tokens: List[Dict[str, Any]], y_overlap_ratio: float = 0.6, y_merge_tol_px: int = 4) -> List[Dict[str,Any]]:
    # simple grouping similar to previous logic
    if not tokens:
        return []
    toks = sorted(tokens, key=lambda t: (t['bbox'][1], (t['bbox'][0]+t['bbox'][2])//2))
    groups: List[List[Dict[str,Any]]] = []
    for t in toks:
        placed = False
        for g in groups:
            for gt in g:
                # check vertical overlap
                inter = max(0, min(t['bbox'][3], gt['bbox'][3]) - max(t['bbox'][1], gt['bbox'][1]))
                min_h = max(1, min((t['bbox'][3]-t['bbox'][1]), (gt['bbox'][3]-gt['bbox'][1])))
                if inter >= y_overlap_ratio * min_h and abs(((t['bbox'][1]+t['bbox'][3])/2.0) - ((gt['bbox'][1]+gt['bbox'][3])/2.0)) <= y_merge_tol_px:
                    g.append(t)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            groups.append([t])
    lines = []
    for lid, g in enumerate(groups):
        g_sorted = sorted(g, key=lambda x: x['bbox'][0])
        xs = [tt['bbox'][0] for tt in g_sorted] + [tt['bbox'][2] for tt in g_sorted]
        ys = [tt['bbox'][1] for tt in g_sorted] + [tt['bbox'][3] for tt in g_sorted]
        xmin, ymin, xmax, ymax = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
        avg_conf = float(sum(tt.get('conf',0.0) for tt in g_sorted)/max(1,len(g_sorted)))
        line = {'line_id': lid+1, 'token_ids': [tt['id'] for tt in g_sorted], 'text': ' '.join([tt.get('text','').strip() for tt in g_sorted]).strip(), 'bbox':[xmin,ymin,xmax,ymax], 'avg_conf': avg_conf}
        lines.append(line)
    # sort lines by reading order
    lines.sort(key=lambda L: (L['bbox'][1], L['bbox'][0]))
    return lines


def merge_top_menubar(lines_tokens: List[Dict[str,Any]], menubar_top: int, menubar_height_ratio: float, median_h: float) -> Optional[Dict[str,Any]]:
    # compute threshold
    thr = menubar_top + menubar_height_ratio * median_h
    top_tokens = []
    others = []
    for t in lines_tokens:
        # here t are tokens
        cx, cy = token_centroid(t)
        if cy <= thr:
            top_tokens.append(t)
        else:
            others.append(t)
    if not top_tokens:
        return None
    # create merged line
    sorted_top = sorted(top_tokens, key=lambda x: x['bbox'][0])
    xs = [tt['bbox'][0] for tt in sorted_top] + [tt['bbox'][2] for tt in sorted_top]
    ys = [tt['bbox'][1] for tt in sorted_top] + [tt['bbox'][3] for tt in sorted_top]
    xmin, ymin, xmax, ymax = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
    text = ' '.join([tt.get('text','').strip() for tt in sorted_top]).strip()
    avg_conf = float(sum(tt.get('conf',0.0) for tt in sorted_top)/max(1,len(sorted_top)))
    merged = {'line_id': -1, 'token_ids': [tt['id'] for tt in sorted_top], 'text': text, 'bbox':[xmin,ymin,xmax,ymax], 'avg_conf': avg_conf}
    return merged


def draw_preview(img: np.ndarray, blocks: List[Dict[str,Any]], lines: List[Dict[str,Any]], out_path: str) -> None:
    pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    # draw blocks
    for b in blocks:
        x1,y1,x2,y2 = b['bbox']
        draw.rectangle([x1,y1,x2,y2], outline='red', width=2)
        draw.text((x1, max(0,y1-10)), f"B{b['block_id']}", fill='red')
    # draw lines
    for L in lines:
        x1,y1,x2,y2 = L['bbox']
        draw.rectangle([x1,y1,x2,y2], outline='blue', width=1)
        draw.text((x1, y1-10), f"L{L.get('line_id')}", fill='blue')
    pil.save(out_path)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', required=True)
    ap.add_argument('--ocr-json', default=None)
    ap.add_argument('--run-ocr', action='store_true')
    ap.add_argument('--ocr-lang', default='en')
    ap.add_argument('--out', default=None)
    ap.add_argument('--preview', default=None)
    ap.add_argument('--menubar-top', type=int, default=0)
    ap.add_argument('--menubar-height-ratio', type=float, default=1.5)
    ap.add_argument('--assign-pad', type=int, default=4)
    ap.add_argument('--cv-baseline', type=int, default=1)
    ap.add_argument('--min-token-area', type=int, default=12)
    args = ap.parse_args(argv)

    img, (W,H) = load_image(args.image)

    # get tokens
    tokens: List[Dict[str,Any]] = []
    if args.ocr_json:
        tokens = load_ocr_json(args.ocr_json)
    elif args.run_ocr:
        try:
            tokens = run_easyocr(args.image, langs=args.ocr_lang)
        except Exception as e:
            print(f'Warning: OCR failed: {e}', file=sys.stderr)
            tokens = []
    else:
        print('No OCR input provided; use --ocr-json or --run-ocr', file=sys.stderr)

    # filter tiny tokens
    tokens = [t for t in tokens if (t['bbox'][2]-t['bbox'][0])*(t['bbox'][3]-t['bbox'][1]) >= args.min_token_area]

    # detect blocks
    blocks: List[Dict[str,Any]] = []
    used_method = None
    if HF_AVAILABLE:
        try:
            blocks = detect_blocks_hf(img)
            used_method = 'hf'
        except Exception as e:
            print(f'HF detection failed: {e}', file=sys.stderr)
    if not blocks and LP_AVAILABLE:
        try:
            blocks = detect_blocks_layoutparser(img)
            used_method = 'layoutparser'
        except Exception as e:
            print(f'LayoutParser detection failed: {e}', file=sys.stderr)
    if not blocks and args.cv_baseline:
        blocks = detect_blocks_cv(img)
        used_method = 'cv_baseline'

    # assign tokens
    mapping = assign_tokens_to_blocks(tokens, blocks, assign_pad=args.assign_pad)

    # compute median token height
    heights = [max(1, t['bbox'][3]-t['bbox'][1]) for t in tokens]
    median_h = float(np.median(heights)) if heights else 0.0

    all_lines: List[Dict[str,Any]] = []
    lid = 1
    # special top menubar merge across all tokens
    merged_top = merge_top_menubar(tokens, args.menubar_top, args.menubar_height_ratio, median_h)
    if merged_top:
        merged_top['line_id'] = lid; lid += 1
        merged_top['block_id'] = None
        all_lines.append(merged_top)

    # group per block
    for b in blocks:
        toks = mapping.get(b['block_id'], [])
        lines = group_tokens_into_lines(toks)
        for L in lines:
            L['line_id'] = lid; lid += 1
            L['block_id'] = b['block_id']
            all_lines.append(L)

    # unassigned tokens (-1)
    unassigned = mapping.get(-1, [])
    if unassigned:
        lines = group_tokens_into_lines(unassigned)
        for L in lines:
            L['line_id'] = lid; lid += 1
            L['block_id'] = None
            all_lines.append(L)

    out = {'image_size': [int(W), int(H)], 'blocks': blocks, 'lines': all_lines, 'method': used_method}

    s = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(s)
    else:
        print(s)

    if args.preview:
        try:
            draw_preview(img, blocks, all_lines, args.preview)
        except Exception as e:
            print(f'Preview generation failed: {e}', file=sys.stderr)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
