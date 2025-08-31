# ------------------------ curiosity_drive_node.py --------------------------
import random
import logging

logger = logging.getLogger("curiosity_drive")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] CURIO: %(message)s"))
    logger.addHandler(h)
    logger.setLevel(logging.INFO)

disciplines = [
    "Physics", "Mathematics", "Computer Science", "Biology", "Chemistry",
    "Economics", "Psychology", "Philosophy", "Linguistics", "History",
    "Geography", "Engineering", "Medicine", "Astronomy", "Sociology",
    "Political Science", "Anthropology", "Literature", "Art History", "Musicology",
    "Environmental Science", "Geology", "Oceanography", "Meteorology", "Ecology",
    "Neuroscience", "Genetics", "Biochemistry", "Microbiology", "Zoology",
    "Botany", "Pharmacology", "Immunology", "Epidemiology", "Pathology",
    "Mechanical Engineering", "Electrical Engineering", "Civil Engineering", "Chemical Engineering", "Aerospace Engineering",
    "Biomedical Engineering", "Software Engineering", "Robotics", "Materials Science", "Energy Engineering",
    "Statistics", "Probability Theory", "Applied Mathematics", "Pure Mathematics", "Numerical Analysis",
    "Artificial Intelligence", "Data Science", "Cybersecurity", "Database Systems", "Web Development",
    "Archaeology", "Cultural Studies", "Gender Studies", "Ethnography", "Social Work",
    "Education", "Pedagogy", "Curriculum Studies", "Educational Psychology", "Special Education",
    "Law", "International Law", "Constitutional Law", "Criminal Justice", "Human Rights Law",
    "Business Administration", "Marketing", "Finance", "Operations Management", "Entrepreneurship",
    "Architecture", "Urban Planning", "Landscape Architecture", "Interior Design", "Sustainable Design",
    "Theology", "Religious Studies", "Ethics", "Moral Philosophy", "Comparative Religion",
    "Journalism", "Media Studies", "Communication Studies", "Public Relations", "Advertising",
    "Psychology of Personality", "Clinical Psychology", "Developmental Psychology", "Social Psychology", "Cognitive Psychology",
    "Astrophysics", "Cosmology", "Planetary Science", "Stellar Astronomy", "Radio Astronomy",
    "Paleontology", "Evolutionary Biology", "Marine Biology", "Conservation Biology", "Molecular Biology",
    "Organic Chemistry", "Inorganic Chemistry", "Physical Chemistry", "Analytical Chemistry", "Polymer Chemistry",
    "Quantum Mechanics", "Thermodynamics", "Electrodynamics", "Optics", "Relativistic Physics",
    "Sociology of Culture", "Sociology of Education", "Sociology of Religion", "Social Stratification", "Urban Sociology",
    "Political Theory", "International Relations", "Comparative Politics", "Public Policy", "Political Economy",
    "Anthropology of Religion", "Medical Anthropology", "Cultural Anthropology", "Physical Anthropology", "Linguistic Anthropology",
    "Literary Theory", "Comparative Literature", "Creative Writing", "Poetry Studies", "Prose Studies",
    "Art Criticism", "Renaissance Art", "Modern Art", "Contemporary Art", "Art Conservation",
    "Music Theory", "Ethnomusicology", "Music Composition", "Music Performance", "Music Technology",
    "Climate Science", "Atmospheric Science", "Hydrology", "Geomorphology", "Biogeography",
    "Neurosurgery", "Cardiology", "Oncology", "Endocrinology", "Radiology",
    "Game Theory", "Behavioral Economics", "Econometrics", "Development Economics", "Financial Economics",
    "Linguistic Typology", "Phonology", "Syntax", "Semantics", "Pragmatics",
    "Medieval History", "Modern History", "Ancient History", "Economic History", "Military History",
    "Bioinformatics", "Computational Biology", "Systems Biology", "Synthetic Biology", "Genomics",
    "Structural Engineering", "Transportation Engineering", "Environmental Engineering", "Geotechnical Engineering", "Hydraulic Engineering",
    "Cognitive Science", "Philosophy of Mind", "Logic", "Epistemology", "Metaphysics",
    "Public Health", "Health Policy", "Global Health", "Occupational Health", "Environmental Health",
    "Cryptography", "Network Security", "Ethical Hacking", "Blockchain Technology", "Quantum Computing",
    "Demography", "Population Studies", "Migration Studies", "Urban Studies", "Rural Sociology"
]

subtopics = {
    "Physics": ["Quantum Mechanics", "Thermodynamics", "Electrodynamics", "Astrophysics", "Mechanics", "Optics", "Relativistic Physics", "Solid State Physics", "Nuclear Physics", "Statistical Physics"],
    "Mathematics": ["Algebra", "Geometry", "Number Theory", "Differential Equations", "Probability Theory", "Statistics", "Topology", "Combinatorics", "Mathematical Analysis", "Linear Algebra"],
    "Computer Science": ["Algorithms", "Data Structures", "Machine Learning", "Functional Programming", "Object-Oriented Programming", "Databases", "DevOps", "Cybersecurity", "Distributed Systems", "Web Development"],
    "Biology": ["Genetics", "Ecology", "Microbiology", "Evolutionary Biology", "Biochemistry", "Botany", "Zoology", "Neuroscience", "Molecular Biology", "Bioinformatics"],
    "Chemistry": ["Organic Chemistry", "Inorganic Chemistry", "Physical Chemistry", "Analytical Chemistry", "Biochemistry", "Polymer Chemistry", "Chemical Kinetics", "Thermochemistry", "Materials Chemistry", "Quantum Chemistry"],
    "Economics": ["Microeconomics", "Macroeconomics", "Econometrics", "Game Theory", "Financial Economics", "Behavioral Economics", "Economic History", "International Economics", "Labor Economics", "Development Economics"],
    "Psychology": ["Cognitive Psychology", "Social Psychology", "Clinical Psychology", "Neuropsychology", "Personality Psychology", "Developmental Psychology", "Experimental Psychology", "Psychoanalysis", "Behavioral Psychology", "Perceptual Psychology"],
    "Philosophy": ["Metaphysics", "Epistemology", "Ethics", "Logic", "Philosophy of Science", "Political Philosophy", "Philosophy of Mind", "Aesthetics", "Existentialism", "Phenomenology"],
    "Linguistics": ["Phonetics", "Syntax", "Semantics", "Pragmatics", "Psycholinguistics", "Sociolinguistics", "Computational Linguistics", "Historical Linguistics", "Morphology", "Lexicology"],
    "History": ["Ancient History", "Medieval History", "Modern History", "Contemporary History", "History of Science", "Economic History", "Social History", "Cultural History", "Political History", "Military History"],
    # Extend for other disciplines similarly...
    # For brevity, I'll provide a pattern for the remaining disciplines
}

# Генерим дефолтные подтемы для дисциплин без явного списка
default_subtopics = [
    "Introduction", "Theory", "Applications", "History", "Modern Developments",
    "Experimental Methods", "Interdisciplinary Approaches", "Case Studies",
    "Advanced Topics", "Emerging Trends"
]
for d in disciplines:
    if d not in subtopics:
        subtopics[d] = list(default_subtopics)

def generate_prompt(discipline, used_terms=None, num_terms=None):
    """
    Оригинальная логика построения промта (слегка адаптировал: пробрасываем num_terms).
    """
    st = random.choice(subtopics.get(discipline, ["any subtopic"]))
    complexity = random.choice(["beginner", "intermediate", "advanced", "research-level"])
    aspect = random.choice(["theoretical", "applied", "historical", "modern", "experimental"])
    style = random.choice(["academic", "popular science", "practical", "innovative"])
    if num_terms is None:
        num_terms = random.randint(5, 15)
    seed = random.randint(1, 10000)

    prompt = f"""
You are an expert in {discipline}.
Generate a list of {num_terms} unique terms or concepts related to {discipline}, focusing on the subtopic '{st}'.
The terms should be of {complexity} complexity, represent {aspect} aspects, and align with a {style} style.
Each term must include a brief description (1-2 sentences).
Ensure the terms are maximally diverse and include rare or unconventional concepts.
Use the random seed value {seed} to ensure uniqueness. 
Output format: only a list of items separated by line breaks.
""".strip()

    if used_terms:
        prompt += f"\nAvoid the following terms: {', '.join(used_terms)}."

    return prompt

# --------------------- Внешний интерфейс ноды -----------------------------

def _llm_generate_text(prompt: str, llm=None, model: str | None = None, temperature: float | None = None) -> str:
    """Попытка вызвать реальный LLMClient, иначе — мок-ответ."""
    if llm is not None:
        try:
            # try to pass model/temperature if the client supports them
            try:
                text = llm.generate_text(prompt, model=model, temperature=temperature)
            except TypeError:
                try:
                    text = llm.generate_text(prompt, model=model)
                except TypeError:
                    text = llm.generate_text(prompt)
            if isinstance(text, str) and text.strip():
                logger.info("LLM output received.")
                # логируем первые строки, чтобы не засорять консоль
                preview = "\n".join(text.splitlines()[:5])
                logger.info(f"LLM OUTPUT (preview):\n{preview}\n...")
                return text.strip()
        except Exception as e:
            logger.info(f"LLM get exception {e}.")
            pass
            
    logger.info("LLM is none.")
    # Мок: вернём 10 «терминов» (без жирных, чтобы проще парсить)
    mock = [
        "Quantum Entanglement — non-classical correlations between particles",
        "Thermodynamic Entropy — measure of disorder and information",
        "Turing Completeness — ability to simulate any computation",
        "Gene Regulation — mechanisms controlling gene expression",
        "Catalysis — acceleration of chemical reactions via catalysts",
        "Graph Neural Networks — deep learning on graphs",
        "CRISPR-Cas9 — genome editing technology",
        "Topological Insulators — materials with surface conduction",
        "Monte Carlo Methods — stochastic computational algorithms",
        "Quantum Error Correction — protecting quantum information",
    ]
    return "\n".join(mock)

def _ensure_list(text: str) -> list[str]:
    """
    Делает из ответа построчный список.
    Удаляет нумерацию '1. ' / '- ' и т.п., подсказки с **term** не ломаем.
    """
    import re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    num_re = re.compile(r"^\s*(?:\d+[\)\.\-:]|[\-\•\*])\s*")
    out = []
    for ln in lines:
        out.append(num_re.sub("", ln).strip())
    return out

# Вариант А: модульная точка входа
def run_node(disciplines=None, subtopics=None, num_terms=20, llm=None, model: str | None = None, temperature: float | None = None, **kwargs):
    """
    disciplines: список/строка дисциплин; если None → из глобального списка
    subtopics:  игнорируем здесь (учтены внутри generate_prompt)
    num_terms:  сколько терминов просить у LLM
    llm:        опциональный экземпляр LLMClient

    Возвращает: СТРОКУ — список (по строке на термин).
    """
    # нормализуем дисциплины
    if not disciplines:
        dlist = list(globals()["disciplines"])
    elif isinstance(disciplines, (list, tuple)):
        dlist = list(disciplines)
    else:
        dlist = [str(disciplines).strip()]

    # выберем случайную дисциплину (или можешь объединять несколько — по желанию)
    d = random.choice(dlist) if dlist else "Science"

    prompt = generate_prompt(d, used_terms=None, num_terms=int(num_terms) if num_terms else None)
    text = _llm_generate_text(prompt, llm=llm, model=model, temperature=temperature)

    # ⚠️ Движку удобнее отдать текст (он сам умеет разложить в список при output_format="list")
    return text

# Вариант Б: классическая нода (если ты хочешь вызывать class+method)
class CuriosityDriveNode:
    def __init__(self, llm=None):
        self.llm = llm

    def run(self, disciplines=None, subtopics=None, num_terms=20, **kwargs):
        return run_node(disciplines=disciplines, subtopics=subtopics,
                        num_terms=num_terms, llm=self.llm, **kwargs)
