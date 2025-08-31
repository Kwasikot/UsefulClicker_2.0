You are Codex CLI working inside my project UsefulClicker.
The project consists of:
- core/xml_engine.py — XML execution engine. It parses XML scripts (<program>, <func>, <extnode>, <foreach>, etc.) and runs them.
- voice_daemon.py — background speech recognition service (Whisper). It can accumulate recognized phrases in _text_buffer and expose them via manual_flush().
- llm/openai_client.py — main LLM client (generate_text(prompt: str) -> str).
- llm/openai_client_compat.py — adapter that makes LLM usable from XML (<extnode>) by supporting multiple generate_text signatures.
- examples/*.xml — scenarios to run (pragmatism_youtube.xml, curiosity_drive_test_broad_topics.xml, etc.). They orchestrate voice input, LLM, and YouTube search actions.

Main requirements:


1. LLM must work inside XML scenarios. When XML engine sees <llmcall output_var="pragmatism_tips"  output_format="list" separator="\n" prompt="Generate...", it should call LLM and save the result into the specified output_var.
2. VoiceDaemon should accumulate recognized text into buffer and only send it to LLM on flush (Ctrl+S). Buffer must be inspectable (Ctrl+D) and clearable.
3. The system should gracefully degrade: if LLM or YouTube orchestrator is not available, just log and continue without crash.
4. Everything should log clearly what happens: XML nodes, VoiceDaemon events, LLM calls, YouTube searches.

From now on, when I give you instructions, you will produce **direct code modifications** (patches or replacements of functions/classes) for this project, compatible with Python 3.10+.

Вынеси настройки LLM такие как температура и имя модели в параметры XML-ноды.
Сделай такие параметры у двух нод например:

В ноде
<extnode module="curiosity_drive_node"
         class="CuriosityDriveNode"
         method="run"
         output_var="science_terms_list"
         output_format="list"
         separator="\n"
		 model="gpt4o-mini"
         num_terms="15"/>
		 
сейчас настройки model и температура не прокидываются в llm

--------------------------------------------------------------------

1. Сделай чтобы CuriosityDriveNode и <llmcall поддерживали ollama модели. 
Соответсвенно сделай в каталоге /llm ollama клиент.
В данный момент у меня запущена llama3.2:latest. Поставь ее как дефолтную ollama модель.
2. Сгенерируй новый тестовый кейс (xml файл) на основе pragmatism_youtube.xml, но поменяй параметры для работы с olama и llama3.2:latest.