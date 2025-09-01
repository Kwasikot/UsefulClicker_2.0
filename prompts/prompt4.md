Слушай у меня такая идея пришла. А что если мы создадим в UsefulClicker новую ноду для развития iq. Не уверен что это научно оправдано. Назовем ее не IqRazer а как нибудь более завуалировано например CuriosityCatalyst. А что если CuriosityCatalyst будет использовать запрос к LLM чтобы генерировать список терминов. По максимально широкому списку дисциплин. Дисциплина выбирается случайным образом.
-----------------------------------------------------------------------------------------------------
В корневом каталоге лежит файл rare_terms_node.py. Это нода для развития iq.
Твоя задача сделать рефакторинг этого кода чтобы он работал с нашими llm клиентами OllamaClient и LLMClient.
provider="ollama" model="llama3.2:latest"

<extnode module="rare_terms_node"
         class="RareTermsNode"
         method="run"
         output_var="rare_terms"
         output_format="list"
         provider="ollama"
         model="llama3.2:latest"
         separator="\n"
         language="en"
         num_terms="12"
         rarity="medium-rare"
         include_definitions="true"
         ban_jargon="true"
         random_discipline="true"
         seed="20250901"/>
-----------------------------------------------------------------------------------------------------
You are a senior Python dev. Wire up an existing PyQt5 GUI (from .ui) to call an LLM, save JSON, and populate fields.

In mainwindow.ui you have CuriosityCatalystTab.

Object names (must exist or be set after load):
- QListWidget: listDisciplines, listRarity, listNovelty, listAudience
- QCheckBox:   checkRandomDisciplines
- QPushButton: btnGenerate, btnNext, btnPrev
- QLineEdit:   editTerm, editConcept, editGloss, editHook, editTask
- QPlainTextEdit: textRaw
- QLabel:      labelIndex
- (optional) QSpinBox: spinCount (default N=12 if absent)

On **Generate**:
1) Read GUI state:
   - disciplines = selection from listDisciplines (all if none selected)
   - rarity ∈ {light, medium-rare, rare, ultra-rare}
   - novelty ∈ {low, mid, high}
   - audience ∈ {kids, teens, adults}
   - pick_random = checkRandomDisciplines.isChecked()
   - n = spinCount.value() if present else 12
2) Build an LLM prompt that asks for EXACT JSON with schema:

{
  "meta": {
    "audience": "...",
    "rarity": "...",
    "novelty": "...",
    "discipline_pool": ["..."],
    "picked_discipline": "...",
    "n": 12,
    "timestamp": "ISO 8601"
  },
  "items": [
    {
      "concept": "string",
      "rare_term": "string or null",
      "kid_gloss": "≤ 12 words",
      "hook_question": "open question",
      "mini_task": "small at-home activity",
      "yt_query": "2–6 words"
    }
  ]
}

3) Call LLM (LLMProvider.generate(prompt)); with llm clients OllamaClient и LLMClient.
 if no API key, return deterministic fallback JSON (12 items). 
Prompt:
"""
Generate exactly {{N}} items that spark curiosity for {{AUDIENCE}}.
Topic: pick ONE random discipline from {{DISCIPLINES}} (a JSON array of strings) and use it for all items.
Language: write all fields in {{LANG}}, except yt_query in {{YT_LANG}}.
Use at most one rare/scientific term per item.

Return ONLY a valid JSON object with this exact structure (no markdown, no comments, no extra keys):
{
  "meta": {
    "audience": "{{AUDIENCE}}",
    "rarity": "{{RARITY}}",
    "novelty": "{{NOVELTY}}",
    "discipline_pool": {{DISCIPLINES}},
    "picked_discipline": "string in {{LANG}}",
    "n": {{N}}
  },
  "items": [
    {
      "concept": "string in {{LANG}}",
      "rare_term": "string in {{LANG}} or null",
      "kid_gloss": "≤ 12 words, simple, in {{LANG}}",
      "hook_question": "open question in {{LANG}}",
      "mini_task": "small at-home activity in {{LANG}}",
      "yt_query": "2–6 words in {{YT_LANG}}"
    }
  ]
}
"""


Constraints:
- Keep clarity high; avoid piling up jargon.
- Prefer decontextualized talk (brief explanations, what-if, causes).
- Output must be valid JSON only (no code fences, no trailing commas).

4) Robustly parse JSON (strip code fences/BOM). On success, save to UTF-8 file:
   output/curiosity_hooks_YYYYMMDD_HHMMSS.json (indent=2, ensure_ascii=False).
5) In textRaw: show “Saved: <absolute_path>”, then raw LLM text.
6) Populate item #1 into fields:
   editTerm ← rare_term
   editConcept ← concept
   editGloss ← kid_gloss
   editHook ← hook_question
   editTask ← mini_task
   labelIndex ← "1 / <total>"

**Next/Previous**:
- Iterate through parsed items, update fields and labelIndex accordingly.

Acceptance:
- Clicking Generate creates the file in /output, displays its path in textRaw, and fills the first item.
- Next/Previous browse all items reliably.
- Works with fallback JSON when no API key is present.

-----------------------------------------------------------------------------------------------------
Далее идет задача на доработку qui.
Там есть RareTermsNodeTab BROAD_DISCIPLINES
-----------------------------------------------------------------------------------------------------
В файловом меню есть actionLLM_Settings. По этому действию должен создаваться диалог настроек из llm_settings_dialog.ui. 
Он должен писать в QSettings настройки LLM. И сохранять их в каталоге кликера в папке settings. Формат ini.
Там должны быть текущие настройки LLM.
provider="ollama" 
model="llama3.2:latest"

В настройках должны быть список моделей openai.
gpt-5
gpt-5-mini
gpt-5-nano
o4-mini
o3
o3-mini
gpt-4.1
gpt-4.1-mini
gpt-4.1-nano
gpt-4o
gpt-4o-mini

В настройках должен быть списко ollama моделей доступных через http.

В настройках должен быть выбор языка
-----------------------------------------------------------------------------------------------------
UsefulClicker должен поддерживать несколько языков.
По actionLanguage должен вызываться окно выбора языков.


-----------------------------------------------------------------------------------------------------
Надо создать обычную ноду со простым списком поисковых запросов 
<list> . Посмотри пример в examples/sophisticated_vocabulary_kids.xml. 
Расширь движок добавлением этой ноды. 
Обнови README.MD информацией о том что Python должен быть версии 3.11.
-----------------------------------------------------------------------------------------------------
В paginatorLabel добавь номер текущего запроса в виде {current_item}\{number_of_items}.
Читай настройки дисциплин оттуда.
------------------------------------------------------------------------------------------------------
Ранее я давал такие инструкции. Тебе надо отменить их действие.
"Если в xml дереве присутсвует нода CuriosityNode, то страница CuriosityNodeTab становится видимой, иначе она скрыта.
Если в xml дереве присутсвует нода llmcall, то страница llmcall_tab становится видимой, иначе она скрыта."
Потому что при запуске программы выскакивает глюк: две страницы накладываются друг надруга и лечится это только переисовкой tab.
------------------------------------------------------------------------------------------------------
в ответе llama3.2 поле rare_term почему-то нулевое
items": [
    {
      "concept": "What happens when you share a password online?",
      "rare_term": null,
      "kid_gloss": "a password shared too much",
      "hook_question": "Do you think your username is safe?",
      "mini_task": "Think of 3 things that can make your password less safe.",
      "yt_query": ""
    },
модифицируй как-то промт чтобы там появлялось что-то осмысленное
------------------------------------------------------------------------------------------------------