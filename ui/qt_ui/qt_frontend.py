"""Lightweight Qt5 frontend for UsefulClicker XML engine.

This module implements a minimal UI that can be used to control the
XMLProgram engine: play/pause, next (skip), restart, load/save XML and
inspect program tree. The UI is intentionally lightweight so other
frontends (web_ui etc.) can be plugged in similarly.
"""
from pathlib import Path
import threading, sys, time, datetime, os
try:
    from PyQt5 import QtWidgets, QtCore, uic
except Exception:
    QtWidgets = None
import json

from core.xml_engine import XMLProgram
import logging
logger = logging.getLogger('usefulclicker.ui')

def _load_ui_file(ui_path: Path):
    # Workaround: some .ui files produced by QtDesigner contain C++-style enum
    # qualifiers like "Qt::WindowModality::NonModal" which older/newer PyQt
    # uic.loadUi may fail to resolve. Replace such qualifiers with plain
    # enum names before loading.
    txt = Path(ui_path).read_text(encoding='utf-8')
    # Workarounds for C++-style enum qualifiers that uic may not resolve
    if 'Qt::WindowModality::' in txt:
        txt = txt.replace('Qt::WindowModality::', '')
    if 'QAbstractItemView::SelectionMode::' in txt:
        txt = txt.replace('QAbstractItemView::SelectionMode::', '')
    # Generic strip of C++-style qualifiers like SomeEnum::Sub::Value -> Value
    import re
    txt = re.sub(r"\b[A-Za-z0-9_]+::", "", txt)
    # Replace empty enum tags which may produce None during uic processing
    txt = re.sub(r"<enum\s*/>", "<enum>0</enum>", txt)
    txt = re.sub(r"<enum\s*>\s*</enum>", "<enum>0</enum>", txt)
    # Use temporary file to feed uic
    import tempfile
    tf = tempfile.NamedTemporaryFile(mode='w', suffix='.ui', delete=False, encoding='utf-8')
    try:
        tf.write(txt); tf.flush(); tf.close()
        try:
            return uic.loadUi(tf.name)
        except Exception as e:
            # save problematic ui for inspection
            try:
                err_path = tf.name + '.failed'
                with open(err_path, 'w', encoding='utf-8') as ef:
                    ef.write(txt[:4000])
            except Exception:
                err_path = '<unavailable>'
            import traceback
            tb = traceback.format_exc()
            raise RuntimeError(f'uic.loadUi failed: {e}\nSaved preview: {err_path}\nTrace:\n{tb}')
    finally:
        try:
            import os; os.unlink(tf.name)
        except Exception:
            pass

class ProgramThread(threading.Thread):
    def __init__(self, prog: XMLProgram, on_finish=None):
        super().__init__(daemon=True)
        self.prog = prog
        self.on_finish = on_finish

    def run(self):
        try:
            self.prog.run()
        except Exception:
            # let UI observe via on_finish
            pass
        if callable(self.on_finish):
            try:
                self.on_finish()
            except Exception:
                pass

class MainWindowWrapper:
    def __init__(self, xml_path: Path):
        if QtWidgets is None:
            raise RuntimeError("PyQt5 is required for qt_ui")
        self.app = QtWidgets.QApplication(sys.argv)
        # Ensure repo root is on sys.path so modules like cv.gui and perceive_node
        # can be imported from UI callbacks (on_perceive etc.).
        try:
            repo_root = Path(__file__).resolve().parents[2]
            rp = str(repo_root)
            import sys as _sys
            if rp not in _sys.path:
                _sys.path.insert(0, rp)
        except Exception:
            pass
        ui_file = Path(__file__).parent / "mainwindow.ui"
        self.win = _load_ui_file(ui_file)
        self.xml_path = Path(xml_path)
        self.prog = None
        self.worker = None
        # curiosity output variable name (detected from XML extnode) and last cached value
        self._curiosity_output_var = None
        self._last_curiosity_value = None
        # cached lists to keep UI stable if other code clears widgets
        self._cached_disciplines = []
        self._cached_subtopics = {}
        # name of foreach list variable (for current/next display)
        self._foreach_list_name = None

        # Wire basic controls
        self.win.playButton.clicked.connect(self.on_play_pause)
        # toolButton_2 -> next/skip
        try:
            self.win.toolButton_2.clicked.connect(self.on_next)
        except Exception:
            pass
        # toolButton_3 -> restart
        try:
            self.win.toolButton_3.clicked.connect(self.on_restart)
        except Exception:
            pass

        # XML load/save via shortcuts (use QKeySequence to avoid operator misuse)
        try:
            from PyQt5.QtGui import QKeySequence
            save_sc = QtWidgets.QShortcut(QKeySequence('Ctrl+S'), self.win)
            save_sc.activated.connect(self.save_xml)
            open_sc = QtWidgets.QShortcut(QKeySequence('Ctrl+O'), self.win)
            open_sc.activated.connect(self.open_xml)
        except Exception:
            # fallback: ignore shortcuts if QKeySequence isn't available
            pass

        # regenerate buttons (best-effort behaviour)
        try:
            self.win.regenerateButton.clicked.connect(self.on_regenerate_curiosity)
        except Exception:
            pass
        try:
            self.win.regenerateList.clicked.connect(self.on_regenerate_llmcall)
        except Exception:
            pass

        # Populate initial XML and tree
        self.load_xml_file(self.xml_path)

        # Optional: connect a 'loadProgram' button from the UI (if present)
        btn = getattr(self.win, 'loadProgram', None)
        if btn is not None:
            try:
                btn.clicked.connect(self.on_load_program_clicked)
            except Exception:
                pass
        # connect nextButton to skip (ctrl+N behavior)
        try:
            self.win.nextButton.clicked.connect(self.on_next)
        except Exception:
            pass

        # CuriosityCatalyst tab wiring: schedule init after event loop to ensure widgets exist
        try:
            QtCore.QTimer.singleShot(300, lambda: self._init_curiosity_catalyst())
        except Exception:
            try:
                self._init_curiosity_catalyst()
            except Exception:
                pass

        # PerceiveNode testing: connect Perceive button if present
        try:
            if getattr(self.win, 'perceiveButton', None) is not None:
                self.win.perceiveButton.clicked.connect(self.on_perceive)
        except Exception:
            pass
        # Add a second perceive button (Perceive full OCR) if not present in UI
        try:
            if getattr(self.win, 'PerceiveNodeTab', None) is not None:
                tab = self.win.PerceiveNodeTab
                if getattr(tab, 'perceiveButton_2', None) is None:
                    btn2 = QtWidgets.QPushButton('Perceive FullOCR', tab)
                    btn2.setObjectName('perceiveButton_2')
                    # place it near existing perceiveButton if possible
                    try:
                        orig = getattr(tab, 'perceiveButton', None)
                        if orig is not None:
                            geo = orig.geometry()
                            btn2.setGeometry(geo.x()+140, geo.y(), 140, geo.height())
                        else:
                            btn2.setGeometry(10, 120, 140, 40)
                    except Exception:
                        btn2.setGeometry(10, 120, 140, 40)
                    btn2.show()
                    btn2.clicked.connect(self.on_perceive_full)
        except Exception:
            pass

        # timer to refresh state (buttons, labels)
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.refresh_state)
        self.timer.start(200)

    def _log_console(self, msg: str):
        try:
            cur = self.win.consoleText.toPlainText()
            self.win.consoleText.setPlainText(cur + "\n" + str(msg))
        except Exception:
            pass
        try:
            logger.info(msg)
        except Exception:
            pass

    def start_program(self):
        # create XMLProgram and start thread
        self.prog = XMLProgram(self.current_xml_path)
        # unpause engine to run immediately
        try:
            self.prog.paused = False
        except Exception:
            pass
        self.worker = ProgramThread(self.prog, on_finish=self.on_thread_finish)
        self.worker.start()

    def on_thread_finish(self):
        # called in worker thread; schedule UI update in main thread
        QtCore.QTimer.singleShot(0, self.refresh_state)

    def on_play_pause(self):
        if not self.prog:
            return
        self.prog._toggle_pause()

    def on_next(self):
        if not self.prog:
            return
        self.prog._skip_now()

    def on_restart(self):
        if not self.prog:
            # start fresh
            self.start_program()
            return
        # request restart — engine will stop at next checkpoint
        self.prog.request_restart()

    def refresh_state(self):
        # update play button visual based on program state
        running = self.worker is not None and self.worker.is_alive()
        paused = getattr(self.prog, 'paused', False) if self.prog else False
        if running and not paused:
            self.win.playButton.setText('PAUSE')
            self.win.playButton.setStyleSheet('border: 2px solid #9ece1b')
        elif running and paused:
            self.win.playButton.setText('RESUME')
            self.win.playButton.setStyleSheet('border: 2px solid #e5c07b')
        else:
            self.win.playButton.setText('PLAY')
            self.win.playButton.setStyleSheet('')

        # update listIndex if engine provides any index info
        idx = None
        if self.prog and isinstance(self.prog.variables.get('index', None), int):
            idx = self.prog.variables.get('index')
        if idx is not None:
            self.win.listIndex.setText(f"{idx}")

        # NOTE: do not change visibility of tabs here to avoid flicker/hiding
        # after they are initialized. Visibility is managed once at XML load time.
        # Poll curiosity output variable (if engine running) and update UI when it changes
        try:
            ov = getattr(self, '_curiosity_output_var', None)
            if ov and self.prog:
                val = self.prog.variables.get(ov)
                if val is not None and val != self._last_curiosity_value:
                    self._last_curiosity_value = val
                    # normalize into list of strings
                    if isinstance(val, (list, tuple)):
                        items = [str(x) for x in val]
                        raw = '\n'.join(items)
                    else:
                        raw = str(val)
                        items = [l for l in raw.splitlines() if l.strip()]
                    try:
                        if hasattr(self.win, 'raw_llm_output_textarea'):
                            try:
                                self.win.raw_llm_output_textarea.setPlainText(raw)
                            except Exception:
                                try:
                                    self.win.raw_llm_output_textarea.setHtml('<pre>%s</pre>' % raw)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    try:
                        if hasattr(self.win, 'termsList'):
                            self.win.termsList.clear()
                            for it in items:
                                self.win.termsList.addItem(str(it))
                    except Exception:
                        pass
        except Exception:
            pass
        # update currentClickerItemLabel for foreach list elements
        try:
            flist = getattr(self, '_foreach_list_name', None)
            if flist and self.prog:
                items = self.prog.variables.get(flist)
                idx = self.prog.variables.get('index')
                if isinstance(items, (list, tuple)) and isinstance(idx, int):
                    cur = items[idx] if 0 <= idx < len(items) else ''
                    nxt = items[(idx + 1) % len(items)] if len(items) > 0 else ''
                    html = (
                        f'<html><head/><body>'
                        f'<p><span style=" font-size:10pt; font-weight:700; color:#9ece1b;">Now: {cur}</span></p>'
                        f'<p><span style=" font-size:10pt; font-weight:700; color:#9ece1b;">Next: {nxt}</span></p>'
                        f'</body></html>'
                    )
                    try:
                        self.win.currentClickerItemLabel.setText(html)
                    except Exception:
                        pass
        except Exception:
            pass
        # Ensure discipline/subtopics lists stay populated (repair if cleared externally)
        try:
            dlw = getattr(self.win, 'disciplinesList', None)
            if dlw is not None and dlw.count() == 0 and self._cached_disciplines:
                for s in self._cached_disciplines:
                    try:
                        dlw.addItem(s)
                    except Exception:
                        pass
            slw = getattr(self.win, 'subtopicsList', None)
            if slw is not None and slw.count() == 0 and self._cached_subtopics:
                # try to repopulate for currently selected discipline
                cur = None
                try:
                    cur_item = dlw.currentItem() if dlw is not None else None
                    cur = cur_item.text() if cur_item is not None else None
                except Exception:
                    cur = None
                if not cur and self._cached_disciplines:
                    cur = self._cached_disciplines[0]
                if cur and cur in self._cached_subtopics:
                    for s in self._cached_subtopics.get(cur, []):
                        try:
                            slw.addItem(s)
                        except Exception:
                            pass
        except Exception:
            pass

    def open_xml(self):
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(self.win, 'Open XML', str(self.xml_path.parent), 'XML Files (*.xml);;All Files (*)')
        if not fn:
            return
        self.load_xml_file(Path(fn))

    def on_load_program_clicked(self):
        """Handler for loadProgram button: delegate to the common open dialog.

        This simply calls open_xml() to reuse the same behavior and path
        selection logic used elsewhere in the UI.
        """
        try:
            self.open_xml()
        except Exception:
            # fallback: ensure nothing crashes if dialog fails
            return

        # After loading XML, start the clicker program
        try:
            self.start_program()
            self._log_console(f"Program started: {self.current_xml_path}")
        except Exception as e:
            self._log_console(f"Failed to start program: {e}")

    def save_xml(self):
        # save contents of xmlEditor to current file
        try:
            txt = self.win.xmlEditor.toPlainText()
        except Exception:
            txt = ''
        if not txt.strip():
            return
        fn, _ = QtWidgets.QFileDialog.getSaveFileName(self.win, 'Save XML', str(self.current_xml_path), 'XML Files (*.xml);;All Files (*)')
        if not fn:
            return
        Path(fn).write_text(txt, encoding='utf-8')
        # reload tree from saved file
        self.load_xml_file(Path(fn))

    def load_xml_file(self, path: Path):
        self.current_xml_path = Path(path)
        try:
            txt = self.current_xml_path.read_text(encoding='utf-8')
        except Exception:
            txt = ''
        # update xmlEditor: try setPlainText, fall back to setHtml
        try:
            ed = getattr(self.win, 'xmlEditor', None)
            if ed is not None:
                try:
                    ed.setPlainText(txt)
                except Exception:
                    try:
                        ed.setHtml('<pre>%s</pre>' % (txt,))
                    except Exception:
                        pass
        except Exception:
            pass
        # parse and populate tree widget
        try:
            from lxml import etree as ET
        except Exception:
            import xml.etree.ElementTree as ET
        try:
            self.parsed_tree = ET.fromstring(txt.encode('utf-8'))
        except Exception:
            self.parsed_tree = None
        self.populate_tree()
        # detect foreach list for clicker program (for current/next display)
        try:
            self._foreach_list_name = None
            if self.parsed_tree is not None:
                for n in self.parsed_tree.findall('.//foreach'):
                    ln = n.get('list')
                    if ln:
                        self._foreach_list_name = ln
                        break
        except Exception:
            self._foreach_list_name = None
        # initialize CuriosityNode controls if present in XML
        try:
            has_cur = False
            if self.parsed_tree is not None:
                for n in self.parsed_tree.findall('.//*'):
                    try:
                        tag = (n.tag or '').lower()
                        if tag == 'curiositynode':
                            has_cur = True; break
                        # also accept extnode/module=curiosity_drive_node
                        if tag == 'extnode' and ( (n.get('module') or '').strip() == 'curiosity_drive_node' ):
                            has_cur = True
                            try:
                                ov = n.get('output_var')
                                if ov:
                                    self._curiosity_output_var = ov
                            except Exception:
                                pass
                            break
                    except Exception:
                        continue
            if has_cur:
                self._init_curiosity_tab()
            # detect llmcall presence as well and set tab visibility
            has_llm = False
            try:
                if self.parsed_tree is not None:
                    for n in self.parsed_tree.findall('.//*'):
                        try:
                            if (n.tag or '').lower() == 'llmcall':
                                has_llm = True; break
                        except Exception:
                            continue
            except Exception:
                has_llm = False
            # Do not toggle tab visibility here; showing/hiding tabs from
            # XML caused overlapping-tab redraw glitches. Keep tabs static.
            # schedule re-init after a short delay in case other UI actions clear widgets
            try:
                QtCore.QTimer.singleShot(700, lambda: self._init_curiosity_tab() if has_cur else None)
            except Exception:
                pass
        except Exception:
            pass

    def _init_curiosity_tab(self):
        """Populate disciplinesList and subtopicsList from curiosity_drive_node module."""
        # ensure repo root is on sys.path so curiosity_drive_node can be imported
        try:
            repo_root = Path(__file__).resolve().parents[2]
            rp = str(repo_root)
            import sys
            if rp not in sys.path:
                sys.path.insert(0, rp)
        except Exception:
            pass
        try:
            import curiosity_drive_node as cdn
        except Exception:
            cdn = None
        if cdn is None:
            return
        # Populate disciplinesList
        try:
            dlw = getattr(self.win, 'disciplinesList', None)
            if dlw is not None:
                dlw.clear()
                self._cached_disciplines = []
                for d in getattr(cdn, 'disciplines', []):
                    try:
                        s = str(d)
                    except Exception:
                        s = repr(d)
                    dlw.addItem(s)
                    self._cached_disciplines.append(s)
        except Exception:
            pass
        # Populate subtopicsList (empty by default or for first discipline)
        try:
            slw = getattr(self.win, 'subtopicsList', None)
            if slw is not None:
                slw.clear()
                # if there is at least one discipline, show its subtopics
                first = None
                try:
                    first = cdn.disciplines[0] if getattr(cdn, 'disciplines', None) else None
                except Exception:
                    first = None
                if first and getattr(cdn, 'subtopics', None):
                    items = cdn.subtopics.get(first, [])
                    self._cached_subtopics = {}
                    for k,v in getattr(cdn, 'subtopics', {}).items():
                        try:
                            self._cached_subtopics[str(k)] = [str(x) for x in v]
                        except Exception:
                            self._cached_subtopics[str(k)] = [repr(x) for x in v]
                    for it in self._cached_subtopics.get(str(first), []):
                        slw.addItem(it)
        except Exception:
            pass
        # connect selection change: when discipline selected -> populate subtopics
        try:
            if dlw is not None and slw is not None:
                def _on_discipline_changed(current, previous=None):
                    try:
                        txt = current.text() if current is not None else None
                    except Exception:
                        try:
                            txt = str(current)
                        except Exception:
                            txt = None
                    slw.clear()
                    if txt and getattr(cdn, 'subtopics', None):
                        items = cdn.subtopics.get(txt, [])
                        for it in items:
                            try:
                                slw.addItem(str(it))
                            except Exception:
                                slw.addItem(repr(it))
                try:
                    dlw.currentItemChanged.connect(_on_discipline_changed)
                except Exception:
                    try:
                        dlw.itemSelectionChanged.connect(lambda: _on_discipline_changed(dlw.currentItem()))
                    except Exception:
                        pass
        except Exception:
            pass

    def _init_curiosity_catalyst(self):
        # find widgets
        try:
            tab = getattr(self.win, 'CuriosityCatalystTab', None)
            if tab is None:
                return
        except Exception:
            return
        # buttons and lists
        self.cc_widgets = {}
        # support multiple possible names used in .ui files
        self.cc_widgets['listDisciplines'] = getattr(self.win, 'listDisciplines', None) or getattr(self.win, 'disciplinesList', None) or getattr(self.win, 'disciplines_list', None)
        self.cc_widgets['listRarity'] = getattr(self.win, 'listRarity', None)
        self.cc_widgets['listNovelty'] = getattr(self.win, 'listNovelty', None)
        self.cc_widgets['listAudience'] = getattr(self.win, 'listAudience', None)
        self.cc_widgets['checkRandomDisciplines'] = getattr(self.win, 'checkRandomDisciplines', None) or getattr(self.win, 'genRandomDiscpCheckbox', None)
        self.cc_widgets['btnGenerate'] = getattr(self.win, 'btnGenerate', None)
        self.cc_widgets['btnNext'] = getattr(self.win, 'btnNext', None)
        self.cc_widgets['btnPrev'] = getattr(self.win, 'btnPrev', None)
        self.cc_widgets['editTerm'] = getattr(self.win, 'editTerm', None)
        self.cc_widgets['editConcept'] = getattr(self.win, 'editConcept', None)
        self.cc_widgets['editGloss'] = getattr(self.win, 'editGloss', None)
        self.cc_widgets['editHook'] = getattr(self.win, 'editHook', None)
        self.cc_widgets['editTask'] = getattr(self.win, 'editTask', None)
        self.cc_widgets['textRaw'] = getattr(self.win, 'textRaw', None)
        # label in UI is named 'listIndex' (showing index like '1 / 12')
        self.cc_widgets['labelIndex'] = getattr(self.win, 'labelIndex', None) or getattr(self.win, 'listIndex', None)
        self.cc_widgets['spinCount'] = getattr(self.win, 'spinCount', None)

        # initialize state
        self._curiosity_items = []
        self._curiosity_index = 0

        # populate disciplines from settings file if available
        try:
            list_widget = self.cc_widgets.get('listDisciplines')
            if list_widget is not None and hasattr(list_widget, 'clear') and hasattr(list_widget, 'addItem'):
                settings_path = Path(__file__).resolve().parents[2] / 'settings' / 'curiosity_catalys_settings.xml'
                if settings_path.exists():
                    try:
                        from lxml import etree as ET
                    except Exception:
                        import xml.etree.ElementTree as ET
                    try:
                        tree = ET.parse(str(settings_path))
                        root = tree.getroot()
                        disc = []
                        for it in root.findall('.//disciplines/item'):
                            txt = (it.text or '').strip()
                            if txt:
                                disc.append(txt)
                        list_widget.clear()
                        for d in disc:
                            try:
                                list_widget.addItem(d)
                            except Exception:
                                pass
                    except Exception as e:
                        self._log_console(f'Failed to parse settings disciplines: {e}')
                        logger.exception('Failed to parse settings disciplines')

                else:
                    self._log_console(f'Settings file not found: {settings_path}')
        except Exception:
            # guard against any error while populating disciplines
            self._log_console('Unexpected error while populating disciplines from settings')
        # connect buttons
        try:
            if self.cc_widgets['btnGenerate']:
                self.cc_widgets['btnGenerate'].clicked.connect(self.on_generate_curiosity)
        except Exception:
            pass
        try:
            if self.cc_widgets['btnNext']:
                self.cc_widgets['btnNext'].clicked.connect(self.on_next_curiosity)
        except Exception:
            pass
        try:
            if self.cc_widgets['btnPrev']:
                self.cc_widgets['btnPrev'].clicked.connect(self.on_prev_curiosity)
        except Exception:
            pass

        # Increase font size of edit fields for better readability (at least 14pt)
        try:
            for k in ('editTerm','editConcept','editGloss','editHook','editTask'):
                wdg = self.cc_widgets.get(k)
                if wdg is not None:
                    try:
                        # apply stylesheet to enforce larger font
                        wdg.setStyleSheet('font-size:14pt;')
                    except Exception:
                        try:
                            f = wdg.font()
                            f.setPointSize(14)
                            wdg.setFont(f)
                        except Exception:
                            pass
        except Exception:
            pass

    def populate_tree(self):
        tw = self.win.treeWidget
        tw.clear()
        if not getattr(self, 'parsed_tree', None):
            return
        def add_item(parent, node):
            if hasattr(node, 'tag'):
                try:
                    text = str(node.tag)
                except Exception:
                    try:
                        text = repr(node.tag)
                    except Exception:
                        text = '<tag>'
            else:
                text = str(node)
            it = QtWidgets.QTreeWidgetItem([text])
            parent.addChild(it)
            for ch in list(node):
                add_item(it, ch)

        root = self.parsed_tree
        try:
            root_text = str(root.tag)
        except Exception:
            try:
                root_text = repr(root.tag)
            except Exception:
                root_text = '<root>'
        root_item = QtWidgets.QTreeWidgetItem([root_text])
        tw.addTopLevelItem(root_item)
        for ch in list(root):
            add_item(root_item, ch)
        tw.expandAll()

    def on_perceive(self):
        """Show perception window and dump detected rects+texts to PerceiveNode tab console."""
        try:
            # import the window class from cv.gui
            from cv.gui import PerceiveWindow
        except Exception:
            PerceiveWindow = None
        if PerceiveWindow is None:
            # Try headless fallback: call perceive_node.PerceiveNode.perceive() if available
            try:
                import perceive_node
                pn = perceive_node.PerceiveNode()
                res = pn.perceive()
                items = res.get('rects') if isinstance(res, dict) else None
                if not items:
                    msg = 'PerceiveNode returned no rects (or perceive_node not available)'
                else:
                    # filter out zero-confidence results
                    filtered = []
                    for i, it in enumerate(items):
                        try:
                            conf = float(it.get('conf') or 0)
                        except Exception:
                            try:
                                conf = float(str(it.get('conf') or '0').strip())
                            except Exception:
                                conf = 0.0
                        if conf != 0.0:
                            filtered.append((i, it, conf))
                    if not filtered:
                        msg = 'No OCR results with conf != 0'
                    else:
                        lines = []
                        for i, it, conf in filtered:
                            lines.append(f"{i}: {it.get('x')},{it.get('y')},{it.get('w')},{it.get('h')} -> {it.get('text')} (conf={conf})")
                        msg = "\n".join(lines)
            except Exception as e:
                msg = f'PerceiveWindow not available and perceive_node fallback failed: {e}'
            try:
                self.win.consoleText.setPlainText(msg)
            except Exception:
                pass
            return

    def on_perceive_full(self):
        """Run OCR on full screenshot using easyocr if available and print text+bboxes."""
        # Ensure a fresh screenshot is taken on each click (best-effort).
        # Prefer cv.preprocess.take_screenshot if available (it saves screenshot.png),
        # otherwise try pyautogui directly; if both fail, fall back to an existing screenshot.png.
        import os
        fn = os.path.join(os.getcwd(), 'screenshot.png')
        screenshot_taken = False
        try:
            try:
                from cv.preprocess import take_screenshot
                try:
                    take_screenshot()
                    screenshot_taken = True
                except Exception:
                    screenshot_taken = False
            except Exception:
                # fallback: pyautogui
                try:
                    import pyautogui
                    img = pyautogui.screenshot()
                    img.save(fn)
                    screenshot_taken = True
                except Exception:
                    screenshot_taken = False
        except Exception:
            screenshot_taken = False

        if not os.path.exists(fn):
            try:
                self.win.consoleText.setPlainText('screenshot.png not found and could not be captured')
            except Exception:
                pass
            return
        layout_path = os.path.join(os.getcwd(), 'layout_result.json')
        # Run ready_layout_infer to produce layout_result.json (run OCR there too)
        try:
            import ready_layout_infer
            out_json = os.path.join(os.getcwd(), 'layout_result.json')
            # call main to produce layout_result.json; pass --run-ocr to ensure tokens
            try:
                ready_layout_infer.main(['--image', fn, '--run-ocr', '--out', out_json])
            except SystemExit:
                # ready_layout_infer calls sys.exit; ignore
                pass
        except Exception as e:
            try:
                self.win.consoleText.setPlainText(f'ready_layout_infer failed: {e}')
            except Exception:
                pass
            return

        # Now load layout_result.json and build prompt from its lines
        layout_path = os.path.join(os.getcwd(), 'layout_result.json')
        if not os.path.exists(layout_path):
            try:
                self.win.consoleText.setPlainText('layout_result.json not found after ready_layout_infer')
            except Exception:
                pass
            return
        try:
            with open(layout_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            try:
                self.win.consoleText.setPlainText(f'Failed to read layout_result.json: {e}')
            except Exception:
                pass
            return

        lines_from_json = data.get('lines', [])
        # build prompt from lines
        intent = ''
        try:
            if getattr(self.win, 'userIntent', None) is not None:
                intent = self.win.userIntent.toPlainText().strip()
            elif getattr(self.win, 'perceiveLlmPromt', None) is not None:
                intent = self.win.perceiveLlmPromt.toPlainText().strip()
        except Exception:
            intent = ''
        if not intent:
            intent = 'open search menu'
        parts = []
        for L in lines_from_json:
            lid = L.get('line_id')
            txt = L.get('text') or ''
            ctx = ''
            try:
                raw = L.get('raw_texts') or []
                ctx = ' | '.join([r.strip() for r in raw if r])
            except Exception:
                ctx = ''
            parts.append(f'[ID={lid}] text="{txt}" context_hint="{ctx}"')
        # Improve prompt to encourage providing a meaningful rare_term where applicable.
        prompt = (
            f"You are a helper that selects the best match for the user's intent.\n"
            f"Intent: {intent}\nCandidates:\n" + '\n'.join(parts) +
            "\n\nWhen producing the JSON, follow these rules exactly:\n"
            "- For the field 'rare_term' prefer a concise technical or scientific word or short phrase (1-3 words) that is relevant to the concept.\n"
            "- Use null for 'rare_term' ONLY if there truly is no meaningful technical term for that item.\n"
            "- Keep 'kid_gloss' short and simple (<=12 words).\n"
            "- 'yt_query' should be 2-6 words suitable for a YouTube search.\n"
            "- Do NOT include any explanatory text outside the returned JSON.\n\n"
            "Return ONLY a valid JSON object with this exact structure (no markdown, no comments, no extra keys):\n"
            "{\n  \"meta\": {\n    \"audience\": \"{intent}\",\n    \"rarity\": \"{rarity}\",\n    \"novelty\": \"{novelty}\",\n    \"discipline_pool\": {disciplines},\n    \"picked_discipline\": \"\",\n    \"n\": {n},\n    \"timestamp\": \"\"\n  },\n  \"items\": [\n    {\n      \"concept\": \"string\",\n      \"rare_term\": \"string or null\",\n      \"kid_gloss\": \"<= 12 words\",\n      \"hook_question\": \"open question\",\n      \"mini_task\": \"small at-home activity\",\n      \"yt_query\": \"2-6 words\"\n    }\n  ]\n}"
        )

        try:
            from llm.ollama_client import OllamaClient
            client = OllamaClient()
            llm_out = client.generate_text(prompt, model='llama3.2:latest')
            try:
                cur = self.win.consoleText.toPlainText()
                self.win.consoleText.setPlainText(cur + '\n\n==== LLM PROMPT ====\n' + prompt + '\n\n==== LLM OUTPUT (ollama) ====\n' + llm_out)
            except Exception:
                pass
        except Exception as e:
            try:
                cur = self.win.consoleText.toPlainText()
                self.win.consoleText.setPlainText(cur + f'\n\nLLM call failed: {e}')
            except Exception:
                pass
        return
        

    def on_regenerate_curiosity(self):
        # best-effort: call curiosity_drive_node.run_node in background and show results
        try:
            import curiosity_drive_node as cdn
        except Exception:
            cdn = None
        def worker():
            if cdn is None:
                out = 'curiosity module not available'
                items = []
            else:
                # choose provider based on UI selection if available
                provider = None
                try:
                    rb_ollama = getattr(self.win, 'radioButton', None)
                    rb_openai = getattr(self.win, 'radioButton_2', None)
                    if rb_ollama is not None and rb_ollama.isChecked():
                        provider = 'ollama'
                    elif rb_openai is not None and rb_openai.isChecked():
                        provider = 'openai'
                except Exception:
                    provider = None

                llm_client = None
                if provider == 'openai':
                    try:
                        from llm.openai_client_compat import LLMClientCompat as _LLM
                        llm_client = _LLM()
                    except Exception:
                        try:
                            from llm.openai_client import LLMClient as _LLM
                            llm_client = _LLM()
                        except Exception:
                            llm_client = None
                elif provider == 'ollama':
                    try:
                        from llm.ollama_client import OllamaClient as _LLM
                        llm_client = _LLM()
                    except Exception:
                        llm_client = None
                else:
                    # auto-detect (fallback)
                    try:
                        from llm.openai_client_compat import LLMClientCompat as _LLM
                        llm_client = _LLM()
                    except Exception:
                        try:
                            from llm.openai_client import LLMClient as _LLM
                            llm_client = _LLM()
                        except Exception:
                            try:
                                from llm.ollama_client import OllamaClient as _LLM
                                llm_client = _LLM()
                            except Exception:
                                llm_client = None

                try:
                    txt = cdn.run_node(llm=llm_client)
                except TypeError:
                    # fallback if run_node doesn't accept llm param
                    txt = cdn.run_node()
                out = txt
                items = [s for s in txt.splitlines() if s.strip()]
            def ui_update():
                try:
                    self.win.raw_llm_output_textarea.setPlainText(out)
                except Exception:
                    try:
                        self.win.raw_llm_output_textarea.setHtml('<pre>%s</pre>' % out)
                    except Exception:
                        pass
                try:
                    self.win.termsList.clear()
                    for it in items:
                        self.win.termsList.addItem(it)
                except Exception:
                    pass
                # request program restart
                if self.prog:
                    self.prog.request_restart()
            QtCore.QTimer.singleShot(0, ui_update)
        threading.Thread(target=worker, daemon=True).start()

    def on_regenerate_llmcall(self):
        # Find first llmcall node in parsed xml and try to invoke engine handler
        if not getattr(self, 'parsed_tree', None):
            return
        node = None
        for n in self.parsed_tree.findall('.//'):
            try:
                if n.tag.lower() == 'llmcall':
                    node = n; break
            except Exception:
                continue
        if node is None:
            return
        # run handle_llmcall in background using a temporary XMLProgram instance
        def worker():
            prog = XMLProgram(self.current_xml_path)
            try:
                prog.handle_llmcall(node)
                out = prog.variables.get(node.get('output_var') or '','')
                if isinstance(out, list):
                    items = out
                    out_text = '\n'.join(items)
                else:
                    out_text = str(out)
                    items = [l for l in out_text.splitlines() if l.strip()]
            except Exception as e:
                out_text = f'LLM call failed: {e}'
                items = []
            def ui_update():
                try:
                    self.win.raw_llm_output_textarea_2.setPlainText(out_text)
                except Exception:
                    pass
                try:
                    self.win.listWidget.clear()
                    for it in items:
                        self.win.listWidget.addItem(str(it))
                except Exception:
                    pass
                if self.prog:
                    self.prog.request_restart()
            QtCore.QTimer.singleShot(0, ui_update)
        threading.Thread(target=worker, daemon=True).start()

    # --- Curiosity Catalyst handlers ---
    def on_generate_curiosity(self):
        w = self.cc_widgets
        # gather selections
        disciplines = []
        try:
            lw = w.get('listDisciplines')
            if lw is not None:
                for it in lw.selectedItems(): disciplines.append(it.text())
                if not disciplines:
                    # take all
                    # if list empty, try reloading from settings just-in-time
                    if lw.count() == 0:
                        try:
                            settings_path = Path(__file__).resolve().parents[2] / 'settings' / 'curiosity_catalys_settings.xml'
                            if settings_path.exists():
                                try:
                                    try:
                                        from lxml import etree as ET
                                    except Exception:
                                        import xml.etree.ElementTree as ET
                                    tree = ET.parse(str(settings_path))
                                    root = tree.getroot()
                                    for it in root.findall('.//disciplines/item'):
                                        txt = (it.text or '').strip()
                                        if txt:
                                            lw.addItem(txt)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                    for i in range(lw.count()): disciplines.append(lw.item(i).text())
        except Exception:
            disciplines = []
        rarity = 'light'
        try:
            lr = w.get('listRarity')
            if lr is not None and lr.currentItem(): rarity = lr.currentItem().text()
        except Exception:
            pass
        novelty = 'low'
        try:
            ln = w.get('listNovelty')
            if ln is not None and ln.currentItem(): novelty = ln.currentItem().text()
        except Exception:
            pass
        audience = 'kids'
        try:
            la = w.get('listAudience')
            if la is not None and la.currentItem(): audience = la.currentItem().text()
        except Exception:
            pass
        pick_random = False
        try:
            cb = w.get('checkRandomDisciplines')
            if cb is not None: pick_random = bool(cb.isChecked())
        except Exception:
            pass
        n = 12
        try:
            sp = w.get('spinCount')
            if sp is not None: n = int(sp.value())
        except Exception:
            n = 12

        # Read prompt template and llm settings from settings XML (reload each time)
        settings_path = Path(__file__).resolve().parents[2] / 'settings' / 'curiosity_catalys_settings.xml'
        prompt_template = None
        provider_setting = None
        model_setting = None
        if settings_path.exists():
            try:
                try:
                    from lxml import etree as ET
                except Exception:
                    import xml.etree.ElementTree as ET
                tree = ET.parse(str(settings_path))
                root = tree.getroot()
                pt_elem = root.find('.//prompt_template')
                if pt_elem is not None:
                    prompt_template = ''.join(pt_elem.itertext()).strip()
                # llm settings
                prov = root.find('.//llm/provider')
                if prov is not None:
                    provider_setting = (prov.get('value') or (prov.text or '')).strip()
                # also check top-level attributes and other nodes
                if not provider_setting:
                    provider_setting = (root.get('provider') or '').strip()
                # model: try several common places
                mnode = root.find('.//llm/model')
                if mnode is not None:
                    model_setting = (mnode.get('value') or (mnode.text or '')).strip()
                if not model_setting:
                    model_setting = (root.get('model') or '').strip()
                # temperature (optional)
                tnode = root.find('.//llm/temperature') or root.find('.//temperature')
                temperature_setting = None
                if tnode is not None:
                    temperature_setting = (tnode.get('value') or (tnode.text or '')).strip()
                try:
                    temperature = float(temperature_setting) if temperature_setting else None
                except Exception:
                    temperature = None
                # log loaded settings for debug
                self._log_console(f'Loaded settings: provider={provider_setting} model={model_setting} temperature={temperature} (from {settings_path})')
                # log loaded settings for debug
                self._log_console(f'Loaded settings: provider={provider_setting} model={model_setting} (from {settings_path})')
            except Exception as e:
                prompt_template = None
                self._log_console(f'Failed to load settings file for prompt/template: {e}')
                logger.exception('Failed loading settings for prompt_template')

        if not prompt_template:
            # fallback inline template
            prompt_template = (
                "You are a helper that selects the best match for the user's intent.\n"
                "Intent: {intent}\nCandidates:\n{candidates}\n\n"
                "Return ONLY a valid JSON object with this exact structure (no markdown, no comments, no extra keys):\n"
                "{\n  \"meta\": {\n    \"audience\": \"{intent}\",\n    \"rarity\": \"{rarity}\",\n    \"novelty\": \"{novelty}\",\n    \"discipline_pool\": {disciplines},\n    \"picked_discipline\": \"\",\n    \"n\": {n},\n    \"timestamp\": \"\"\n  },\n  \"items\": [ ... ]\n}"
            )

        # If random pool requested, select a small random set of disciplines (pool size 5)
        try:
            if pick_random:
                all_disc = []
                lw = self.cc_widgets.get('listDisciplines')
                if lw is not None and hasattr(lw, 'count'):
                    for ii in range(lw.count()):
                        try:
                            all_disc.append(lw.item(ii).text())
                        except Exception:
                            pass
                if all_disc:
                    import random
                    # ensure system-based randomness even if some other code seeded RNG
                    try:
                        random.seed(None)
                    except Exception:
                        pass
                    pool_size = min(5, len(all_disc))
                    random.shuffle(all_disc)
                    disciplines = list(all_disc[:pool_size])
                    self._log_console(f'Random discipline pool selected: {disciplines}')
        except Exception:
            pass

        # assemble candidates string
        parts = []
        for i, s in enumerate([f'[ID={i}] text="{d}"' for i,d in enumerate(disciplines)], start=0):
            parts.append(s)
        candidates_block = '\n'.join(parts)
        # format template
        def _safe_format(tpl: str, mapping: dict) -> str:
            # Protect literal braces used for JSON structure: replace placeholders
            # with temporary tokens, escape all braces, then restore placeholders
            tmp_map = {}
            for k in mapping.keys():
                token = f'<<<{k}>>>'
                tpl = tpl.replace('{' + k + '}', token)
                tmp_map[token] = '{' + k + '}'
            # escape remaining braces
            tpl = tpl.replace('{', '{{').replace('}', '}}')
            # restore placeholder braces
            for token, ph in tmp_map.items():
                tpl = tpl.replace(token, ph)
            try:
                return tpl.format(**mapping)
            except Exception:
                return tpl

        try:
            mapping = {
                'intent': audience,
                'disciplines': json.dumps(disciplines, ensure_ascii=False),
                'n': n,
                'rarity': rarity,
                'novelty': novelty,
                'candidates': candidates_block,
                'lang': 'English',
                'yt_lang': 'English'
            }
            prompt = _safe_format(prompt_template, mapping)
        except Exception:
            prompt = prompt_template

        # Call LLM according to settings provider/model if available
        llm_text = None
        try:
            prov = (provider_setting or 'ollama').strip().lower()
            model = model_setting or 'llama3.2:latest'
            self._log_console(f'LLM call using provider={prov} model={model}')
            # show the exact prompt sent to the model for debugging
            try:
                self._log_console('=== PROMPT TO LLM ===\n' + prompt)
            except Exception:
                pass
            if prov == 'ollama':
                from llm.ollama_client import OllamaClient
                client = OllamaClient()
                self._log_console(f'Ollama client ready (model={getattr(client, "model", model)})')
                llm_text = client.generate_text(prompt, model=model, temperature=temperature)
            elif prov == 'openai':
                from llm.openai_client import LLMClient
                client = LLMClient()
                self._log_console(f'OpenAI client ready (model={getattr(client, "model", model)})')
                llm_text = client.generate_text(prompt, model=model, temperature=temperature)
            else:
                # try openai by default if unknown
                from llm.openai_client import LLMClient
                client = LLMClient()
                self._log_console(f'OpenAI client ready (model={getattr(client, "model", model)})')
                llm_text = client.generate_text(prompt, model=model)
        except Exception:
            # fallback try the other client
            try:
                from llm.openai_client import LLMClient
                client = LLMClient()
                llm_text = client.generate_text(prompt, model=model, temperature=temperature)
            except Exception:
                try:
                    from llm.ollama_client import OllamaClient
                    client = OllamaClient()
                    llm_text = client.generate_text(prompt, model='llama3.2:latest', temperature=temperature)
                except Exception:
                    llm_text = None
                    self._log_console('LLM call failed for all providers (no credentials or service)')

        # Fallback: generate deterministic JSON
        if not llm_text or not str(llm_text).strip():
            llm_text = self._curiosity_fallback_json(disciplines, audience, rarity, novelty, n)

        # Try to parse JSON out of the response
        parsed = None
        txt = str(llm_text).strip()
        # strip code fences
        if txt.startswith('```'):
            txt = '\n'.join(txt.splitlines()[1:])
            if txt.endswith('```'):
                txt = '\n'.join(txt.splitlines()[:-1])

        # try json.loads, then try to sanitize common issues, then ast.literal_eval
        try:
            parsed = json.loads(txt)
        except Exception:
            # attempt to find JSON substring first
            import re, ast
            m = re.search(r'\{\s*"meta"[\s\S]*\}\s*\}', txt)
            candidate = m.group(0) if m else txt

            def _fix_single_quoted_array(s: str) -> str:
                # replace [ 'a', 'b' ] -> ["a","b"]
                def repl(m0):
                    inner = m0.group(0)
                    # strip [ and ]
                    body = inner[1:-1]
                    parts = [p.strip().strip("'\"") for p in body.split(',') if p.strip()]
                    return '[' + ','.join('"%s"' % p.replace('"','\\"') for p in parts) + ']'
                return re.sub(r"\[\s*('([^']*)'\s*(,\s*'[^']*'\s*)*)\]", repl, s)

            try:
                cand2 = _fix_single_quoted_array(candidate)
                parsed = json.loads(cand2)
            except Exception:
                # try ast.literal_eval on original candidate (handles python-style quotes)
                try:
                    parsed_py = ast.literal_eval(candidate)
                    # convert to normal JSON-compatible dict by re-serializing
                    parsed = json.loads(json.dumps(parsed_py))
                except Exception:
                    parsed = None

        if not parsed:
            try:
                self.cc_widgets['textRaw'].setPlainText('Failed to parse LLM JSON.\n' + str(llm_text))
            except Exception:
                pass
            return

        # Save JSON to output
        try:
            os.makedirs('output', exist_ok=True)
            ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            outp = os.path.abspath(os.path.join('output', f'curiosity_hooks_{ts}.json'))
            with open(outp, 'w', encoding='utf-8') as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
            try:
                self.cc_widgets['textRaw'].setPlainText(f'Saved: {outp}\n\n' + str(llm_text))
            except Exception:
                pass
        except Exception:
            outp = None

        # Populate first item
        items = parsed.get('items', []) if isinstance(parsed, dict) else []
        self._curiosity_items = items
        self._curiosity_index = 0
        if items:
            self._show_curiosity_item(0)

    def _show_curiosity_item(self, idx: int):
        if not self._curiosity_items:
            return
        if idx < 0 or idx >= len(self._curiosity_items):
            return
        item = self._curiosity_items[idx]
        w = self.cc_widgets
        try:
            # many of these widgets are QTextBrowser/QTextEdit; prefer setPlainText
            if w['editTerm']:
                try: w['editTerm'].setPlainText(item.get('rare_term') or '')
                except Exception: w['editTerm'].setText(item.get('rare_term') or '')
            if w['editConcept']:
                try: w['editConcept'].setPlainText(item.get('concept') or '')
                except Exception: w['editConcept'].setText(item.get('concept') or '')
            if w['editGloss']:
                try: w['editGloss'].setPlainText(item.get('kid_gloss') or '')
                except Exception: w['editGloss'].setText(item.get('kid_gloss') or '')
            if w['editHook']:
                try: w['editHook'].setPlainText(item.get('hook_question') or '')
                except Exception: w['editHook'].setText(item.get('hook_question') or '')
            if w['editTask']:
                try: w['editTask'].setPlainText(item.get('mini_task') or '')
                except Exception: w['editTask'].setText(item.get('mini_task') or '')
            if w['labelIndex']:
                # paginator format: current\total
                total = len(self._curiosity_items) if self._curiosity_items else 0
                w['labelIndex'].setText(f"{idx+1}\\{total}")
        except Exception:
            pass

    def on_next_curiosity(self):
        if not self._curiosity_items: return
        self._curiosity_index = min(len(self._curiosity_items)-1, self._curiosity_index+1)
        self._show_curiosity_item(self._curiosity_index)

    def on_prev_curiosity(self):
        if not self._curiosity_items: return
        self._curiosity_index = max(0, self._curiosity_index-1)
        self._show_curiosity_item(self._curiosity_index)

    def _curiosity_fallback_json(self, disciplines, audience, rarity, novelty, n):
        # deterministic simple filler
        import random
        if not disciplines: disciplines = ['General Science']
        picked = random.choice(disciplines)
        meta = {"audience": audience, "rarity": rarity, "novelty": novelty, "discipline_pool": disciplines, "picked_discipline": picked, "n": n, "timestamp": datetime.datetime.now().isoformat()}
        items = []
        for i in range(n):
            items.append({
                'concept': f'{picked} concept {i+1}',
                'rare_term': None,
                'kid_gloss': f'A short explanation for item {i+1}',
                'hook_question': f'What if {picked} {i+1}?',
                'mini_task': f'Try a small experiment {i+1}',
                'yt_query': f'{picked} intro'
            })
        return {'meta': meta, 'items': items}

    def run(self):
        # start program thread and show UI
        self.start_program()
        self.win.show()
        return self.app.exec_()

def run_ui(xml_path: str):
    mw = MainWindowWrapper(Path(xml_path))
    return mw.run()

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('xml_path')
    args = ap.parse_args()
    run_ui(args.xml_path)
