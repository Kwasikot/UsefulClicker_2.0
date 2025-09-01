# extnodes/rare_terms_node.py
from __future__ import annotations
import random, textwrap

# ——— ШИРОКАЯ КОРЗИНА ДИСЦИПЛИН (можно расширять) ———
BROAD_DISCIPLINES = [
    # Философия и гуманитарные
    "philosophy", "logic", "epistemology", "metaphysics", "ethics", "aesthetics",
    "philosophy of mind", "philosophy of science", "phenomenology", "hermeneutics",
    "semiotics", "rhetoric", "linguistics", "pragmatics", "sociolinguistics",
    "anthropology", "archaeology", "history", "art history", "music theory",
    "media studies", "literary theory",
    # Соц-науки, экономика, право
    "sociology", "political science", "international relations", "economics",
    "game theory", "operations research", "law", "education",
    # Математика и ИТ
    "mathematics", "algebra", "geometry", "topology", "number theory", "analysis",
    "probability", "statistics", "combinatorics", "graph theory", "category theory",
    "set theory", "theoretical computer science", "information theory",
    "cryptography", "computer science", "algorithms", "HCI", "UX",
    "software engineering", "databases",
    # AI/ML/DS
    "artificial intelligence", "machine learning", "deep learning", "data science",
    "reinforcement learning", "natural language processing", "computer vision",
    "causal inference", "AI safety", "alignment",
    # Физика и родственные
    "physics", "classical mechanics", "quantum mechanics", "statistical mechanics",
    "thermodynamics", "electrodynamics", "optics", "condensed matter physics",
    "particle physics", "astrophysics", "cosmology", "quantum information",
    "photonics", "nanotechnology",
    # Химия и материалы
    "chemistry", "organic chemistry", "inorganic chemistry", "physical chemistry",
    "analytical chemistry", "biochemistry", "materials science",
    # Земля и климат
    "earth science", "geology", "geochemistry", "geophysics", "climatology",
    "meteorology", "oceanography", "hydrology", "remote sensing",
    # Жизненные науки и медицина
    "biology", "molecular biology", "genetics", "epigenetics", "microbiology",
    "virology", "immunology", "physiology", "neuroscience", "developmental biology",
    "ecology", "evolutionary biology", "systems biology", "synthetic biology",
    "bioinformatics", "medicine", "psychiatry", "psychology", "cognitive science",
    "pharmacology", "public health",
    # Инженерия и прикладные
    "electrical engineering", "electronics", "signal processing", "control theory",
    "robotics", "mechanical engineering", "civil engineering", "aerospace engineering",
    "nuclear engineering", "chemical engineering", "biomedical engineering",
    "architecture", "urban planning", "energy systems", "renewable energy",
    "cybersecurity", "blockchain", "operations management",
]

def _split_csv(s: str | None) -> list[str]:
    if not s: return []
    return [x.strip() for x in s.split(",") if x.strip()]

def _to_bool(x, default=False) -> bool:
    if isinstance(x, bool): return x
    if x is None: return default
    return str(x).strip().lower() in {"1","true","yes","y","on"}

def _llm_call(llm, prompt: str, max_tokens=800, temperature=0.7):
    """Пробуем несколько возможных интерфейсов клиента LLM, не ломая чужие сигнатуры."""
    if not llm: return None
    for api in ("complete", "chat", "generate", "ask", "__call__"):
        fn = getattr(llm, api, None)
        if callable(fn):
            try:
                return fn(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
            except TypeError:
                try:
                    return fn(prompt)
                except Exception:
                    pass
            except Exception:
                pass
    return None

def _compose_prompt(language: str, discipline: str, n: int,
                    include_definitions: bool, rarity: str, ban_jargon: bool) -> str:
    gloss = ("Include a concise 6–12 word plain-language gloss for each term."
             if include_definitions else "List terms only; no definitions.")
    style = "Avoid gratuitous opacity; prefer precision. No slurs or insults."
    if ban_jargon:
        style += " Avoid internal lab acronyms and ultra-niche argot."
    return textwrap.dedent(f"""
    You are a precise term curator.
    Language: {language}.
    Discipline: {discipline}.
    Task: Produce exactly {n} rare but legitimate terms used by experts in this discipline.
    Rarity target: {rarity} (uncommon yet meaningful to domain experts).
    {gloss}
    Output format: one item per line. If definitions are included, use "term — short gloss".
    Constraints: {style}
    Do not number the items. No extra commentary before or after.
    """)

def _sanitize_lines(text: str) -> list[str]:
    lines = [ln.strip(" •\t\r") for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    # убираем маркеры/нумерацию
    cleaned = []
    for ln in lines:
        ln = ln.lstrip("0123456789.-) ").strip()
        cleaned.append(ln)
    # дедуп по регистронезависимой форме
    seen = set()
    uniq = []
    for ln in cleaned:
        key = ln.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(ln)
    return uniq

class RareTermsNode:
    """
    RareTermsNode
    - run(...)            -> генерирует список терминов через LLM (дисциплина случайна по широкой корзине, если не указана явно)
    - choose_discipline(...) -> отдаёт случайно выбранную дисциплину (полезно отобразить в UI)
    - build_prompt(...)   -> создаёт стиль-промт для «редкотерминального» общения
    """

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._last_discipline = None

    def choose_discipline(self, **kwargs) -> str:
        """Вернуть (и запомнить) случайную дисциплину из пула."""
        seed = kwargs.get("seed") or self.kwargs.get("seed")
        pool_csv = kwargs.get("discipline_pool") or self.kwargs.get("discipline_pool")
        pool = _split_csv(pool_csv) or BROAD_DISCIPLINES
        rng = random.Random()
        if seed is not None:
            try: rng.seed(int(seed))
            except Exception: rng.seed(str(seed))
        self._last_discipline = rng.choice(pool)
        return self._last_discipline

    def _decide_discipline(self, **kwargs) -> str:
        # приоритет: явно переданная > random=true > _last_discipline > случайная
        explicit = kwargs.get("discipline") or self.kwargs.get("discipline")
        if explicit: 
            self._last_discipline = explicit.strip()
            return self._last_discipline
        if _to_bool(kwargs.get("random_discipline") or self.kwargs.get("random_discipline"), True):
            return self.choose_discipline(**kwargs)
        if self._last_discipline:
            return self._last_discipline
        return self.choose_discipline(**kwargs)

    def run(self, **kwargs) -> str:
        """Сгенерировать список терминов (строками) через LLM. Возвращает N строк, разделённых separator."""
        language = (kwargs.get("language") or self.kwargs.get("language") or "en").strip()
        n = int(kwargs.get("num_terms") or self.kwargs.get("num_terms") or 15)
        rarity = (kwargs.get("rarity") or self.kwargs.get("rarity") or "medium-rare").strip()
        include_definitions = _to_bool(kwargs.get("include_definitions") or self.kwargs.get("include_definitions"), True)
        ban_jargon = _to_bool(kwargs.get("ban_jargon") or self.kwargs.get("ban_jargon"), False)
        separator = kwargs.get("separator") or self.kwargs.get("separator") or "\n"

        # дисциплина
        discipline = self._decide_discipline(**kwargs)

        # LLM
        llm = kwargs.get("llm") or self.kwargs.get("llm") or self.kwargs.get("client")
        prompt = _compose_prompt(language, discipline, n, include_definitions, rarity, ban_jargon)
        out = _llm_call(llm, prompt)
        lines = _sanitize_lines(out if isinstance(out, str) else "")

        # нормируем ровно к N
        if len(lines) < n:
            # если LLM дало меньше — просто не добиваем мусором: вернём сколько есть
            pass
        elif len(lines) > n:
            lines = lines[:n]

        return separator.join(lines)

    def build_prompt(self, **kwargs) -> str:
        """Промт для общения с умеренно редкой лексикой и первой глоссой."""
        language = (kwargs.get("language") or self.kwargs.get("language") or "en").strip()
        density = (kwargs.get("density") or self.kwargs.get("density") or "medium").strip()  # light/medium/high
        first_gloss = (kwargs.get("first_gloss") or self.kwargs.get("first_gloss") or "one-gloss").strip()  # none/one-gloss/all
        simplify_on_confusion = _to_bool(kwargs.get("simplify_on_confusion") or self.kwargs.get("simplify_on_confusion"), True)

        per_para = {"light":"~1", "medium":"1–2", "high":"2–3"}.get(density, "1–2")
        gloss_rule = {
            "none": "Do not add glosses.",
            "one-gloss": "Give a brief parenthetical gloss the first time each rare term appears; do not repeat later.",
            "all": "Always add a brief parenthetical gloss for each rare term."
        }.get(first_gloss, "Give a brief parenthetical gloss the first time each rare term appears; do not repeat later.")

        safety = "Avoid obscure neologisms with no published usage. No slurs or derogatory labels."
        clarity = "Clarity first; rare wording must not obscure meaning."
        adapt = "If the user signals confusion, immediately restate with common synonyms."

        prompt = f"""\
You are a clear, precise conversational partner.
Language: {language}.
Style: weave {per_para} rare, domain-appropriate terms per paragraph, naturally.
Glossing rule: {gloss_rule}
Priorities: {clarity} {safety}
Adaptation: {adapt if simplify_on_confusion else ""}
Do not overdo jargon; choose elegant, meaningful rarity, not noise.
"""
        return textwrap.dedent(prompt)
