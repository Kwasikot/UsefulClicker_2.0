Для модуля xml_engine.py реализуй абстрактную ноду, реализация пайтон кода которой будет вынесена в отдельный модуль. Сделай так чтобы я мог легко подключать ноды к движку из других пайтон модулей. Этот модуль тоже выдает текстовую переменную, в которой будет список от некоего генератора (на самом деле он использует класс LLMClient, но формирует промт по особому ). Фактически она должна иметь интерфейс к коду который вынесен в отдельный модуль curiosity_drive_node.py.
Параметры к этой xml ноды будут disciplines, subtopics, num_terms.
 
Ниже идет реализация curiosity_drive_node.py.

#------------------------ curiosity_drive_node.py --------------------------

disciplines = [
    "Physics", "Mathematics", "Computer Science", "Biology", "Chemistry"
  
]

subtopics = {
    "Physics": ["Quantum Mechanics", "Thermodynamics", "Electrodynamics", "Astrophysics", "Mechanics", "Optics", "Relativistic Physics", "Solid State Physics", "Nuclear Physics", "Statistical Physics"],
    "Mathematics": ["Algebra", "Geometry", "Number Theory", "Differential Equations", "Probability Theory", "Statistics", "Topology", "Combinatorics",   # For brevity, I'll provide a pattern for the remaining disciplines
}

# Generate subtopics for remaining disciplines programmatically
default_subtopics = ["Introduction", "Theory", "Applications", "History", "Modern Developments", "Experimental Methods", "Interdisciplinary Approaches", "Case Studies", "Advanced Topics", "Emerging Trends"]
for discipline in disciplines:
    if discipline not in subtopics:
        subtopics[discipline] = default_subtopics
        
def generate_prompt(discipline, used_terms=None):
    import random

    subtopic = random.choice(subtopics.get(discipline, ["any subtopic"]))
    complexity = random.choice(["beginner", "intermediate", "advanced", "research-level"])
    aspect = random.choice(["theoretical", "applied", "historical", "modern", "experimental"])
    style = random.choice(["academic", "popular science", "practical", "innovative"])
    num_terms = random.randint(5, 15)
    seed = random.randint(1, 10000)

    prompt = f"""
    You are an expert in {discipline}. 
    Generate a list of {num_terms} unique terms or concepts related to {discipline}, focusing on the subtopic '{subtopic}'. 
    The terms should be of {complexity} complexity, represent {aspect} aspects, and align with a {style} style. 
    Each term must include a brief description (1-2 sentences). 
    Ensure the terms are maximally diverse and include rare or unconventional concepts. 
    Use the random seed value {seed} to ensure uniqueness. 
    Format the response as a numbered list, with each item starting with the term in bold (**term**).
    """

    if used_terms:
        prompt += f"\nAvoid the following terms: {', '.join(used_terms)}."

    return prompt
    
 
 