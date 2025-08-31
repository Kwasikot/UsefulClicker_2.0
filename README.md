# 📖 README.md (updated)

## 🔹 UsefulClicker

**UsefulClicker** is an XML-driven clicker that automates mouse and keyboard actions, executes shell commands, calls LLM models, and supports modular extensions.

* * *

## 🚀 New Feature: Curiosity Drive Node

### What is it?

**Curiosity Drive Node** is a pluggable node (`<extnode>`) that generates *lists of scientific and technical terms* for exploration and content discovery.  
It uses the module `curiosity_drive_node.py` and builds dynamic prompts for LLM (via `LLMClient` or a built-in mock).

This allows UsefulClicker to automatically discover and browse **science & technology content** on YouTube (or other platforms) based on random disciplines, subtopics, and criteria.

* * *

### `<extnode>` Supported Parameters

`<extnode module="curiosity_drive_node" func="run_node" output_var="science_terms" output_format="list" separator="\n" disciplines="Physics, Computer Science" subtopics="Quantum Mechanics, Algorithms" num_terms="20"/>`

- **module** — Python module name (e.g. `curiosity_drive_node`).
    
- **func/class/method** — entrypoint. You can call `run_node` or `CuriosityDriveNode.run`.
    
- **output_var** — UsefulClicker variable where the result will be stored.
    
- **output_format** — `"list"` or `"text"`.
    
    - `list` → result is stored as an array of strings.
        
    - `text` → result is stored as multiline text.
        
- **separator** — string separator (default: `\n`).
    
- **disciplines** *(optional)* — comma-separated list of disciplines (e.g. `"Physics, Biology"`).
    
- **subtopics** *(optional)* — comma-separated list of subtopics (e.g. `"Quantum Mechanics, Thermodynamics"`).
    
- **num_terms** *(optional)* — number of terms to request from LLM.
    

* * *

### Example: YouTube Search Workflow

```
<!-- Generate a list of science & technology terms -->
<extnode module="curiosity_drive_node"
         func="run_node"
         output_var="science_terms"
         output_format="list"
         separator="\n"
         disciplines="Physics, Computer Science"
         num_terms="15"/>

<!-- Define a function to search on YouTube -->
<func name="SearchYoutube">
  <hotkey hotkey="ctrl+l"/>
  <wait ms="200"/>
  <type mode="copy_paste" text="https://www.youtube.com/results?search_query=${arg0|url}"/>
  <wait ms="300"/>
  <hotkey hotkey="enter"/>
</func>

<!-- Iterate over terms in random order -->
<foreach list="science_terms" do="SearchYoutube" random_shuffle="1"/>
```

Now the clicker:

1.  Generates a new set of scientific terms.
    
2.  Opens YouTube in Google Chrome.
    
3.  Runs a search for each term.
    
4.  Scrolls randomly and clicks on results.
    

Note: UsefulClicker relies on an external LLM (Large Language Model) for generating keywords and prompts. To enable this functionality, set your API key as an environment variable before running the program:

On Linux/macOS: export OPENAI_API_KEY="your_api_key_here"

On Windows (PowerShell): setx OPENAI_API_KEY "your_api_key_here"

* * *

### Logging

`curiosity_drive_node.py` logs:

- the generated prompt,
    
- the raw LLM output (or mock output),
    
- a preview of the first few lines.
    

Logs are prefixed with `[CURIO]` in UsefulClicker output.

* * *

## 🆕 Other New Features in UsefulClicker

- **Extensible nodes**:  
    via `<extnode>` you can connect any Python module with custom logic.
    
- **LLM integration**:  
    in addition to `<llmcall>`, you can now call advanced prompt builders (like Curiosity Drive).
    
- **`random_shuffle` in `<foreach>`**:  
    iterate over list items in random order.
    
- **Pause control from console**:  
    pressing `Space` pauses/resumes execution.
    
- **Robust copy-paste typing**:  
    `mode="copy_paste"` now retries clipboard updates and falls back to typing if needed.
    
- **New `<repeat>` tag**:  
    repeat child actions multiple times, with support for `randint()` directly in XML.
    
- **Screen variables**:  
    `SCREEN_W` and `SCREEN_H` are available for coordinate calculations.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Run
run.bat

UI frontends
- The runner supports pluggable UI frontends. Use --ui to select one, for example:
  python main.py examples/new_music.xml --ui qt_ui
- A Qt5 frontend is provided in ui/qt_ui (requires PyQt5). It implements basic
  controls: Play/Pause, Next (skip), Restart, XML load/save and simple LLM/Curiosity
  regeneration buttons.

Extras:
- Tesseract OCR required for `<clicktext>`. Install and ensure `tesseract.exe` is in PATH.
- Windows focus: use `<focus title="..."/>` (pygetwindow).

## GUI hash tool
```bash
python gui/usefulcliker_gui.py --mode hash
```

```bash
python main.py examples/stage1.xml --debug
```

Draw a rectangle, press **Enter** or click **Save Hash**. The hex pHash is printed and saved to `gui/hashes/last_hash.txt`.

## Examples
- `examples/stage2_notepad_clickimg.xml`
- `examples/stage2_clicktext.xml`
