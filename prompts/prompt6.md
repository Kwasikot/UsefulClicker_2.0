You are Codex CLI working inside my project UsefulClicker.
The project consists of:
- core/xml_engine.py — XML execution engine. It parses XML scripts (<program>, <func>, <extnode>, <foreach>, etc.) and runs them.
- voice_daemon.py — background speech recognition service (Whisper). It can accumulate recognized phrases in _text_buffer and expose them via manual_flush().
- llm/openai_client.py — main LLM client (generate_text(prompt: str) -> str).
- llm/openai_client_compat.py — adapter that makes LLM usable from XML (<extnode>) by supporting multiple generate_text signatures.
- examples/*.xml — scenarios to run (pragmatism_youtube.xml, curiosity_drive_test_broad_topics.xml, etc.). They orchestrate voice input, LLM, and YouTube search actions.
- ui/qt_ui - gui based on PyQt library
Main requirements:


В окне mainwindow есть вкладка editorPanelGB на ней кнопка addClickButton.
По нажатию этой кнопки должна выполняться следующая логика:
1. Должно появляться полупрозрачное окно для выбора координат клика на весь экран, немного зеленоватое, с очень низким значением полупрозрачности.
	1.1. Когда это окно на экране и мышка двигается лейбл mouseCoordinatesLabel обновляется новыми координатами мыши.
2. После кликания в область левой или правой кнопкой мыши в редактор xml программы xmlEditor вставляется строчка 
например <click button="left" x="200" y="10" />
3. Поведение эдит бокса pressAKeyTB: при кажатии комбинации клавиш клавиатуры туда вносится сочетание клавиш. Но только если виджет в фокусе.
4. При нажатии addHotkeyButton то сочетание которое в pressAKeyTB заносится в xml программу. Например добавляется тег <hotkey hotkey="ctrl+l"/>
5. По кнопке saveProgram xml программа должна сохраняться на диске, открывается file save dialog с дефолтным путем eamples/
6. По кнопке editPromptButton редактируется самый первый промт тега <llmcall. Т.е. открывается отдельное окно с текстом промта который можно изменить.
7. По кнопке addType открывается окно где надо ввести тест того что кликер будет писать в окне. добавляется тег type например <type mode="type" text="https://www.youtube.com/results?search_query=${arg0|url}"/>



