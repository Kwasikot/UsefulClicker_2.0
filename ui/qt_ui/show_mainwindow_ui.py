"""
Standalone script: loads mainwindow.ui and shows it.

Usage:
  python show_mainwindow_ui.py [--offscreen] [--auto-close N]

By default it will try to show the window normally. Use --offscreen to force
QT_QPA_PLATFORM=offscreen (useful in CI). --auto-close closes the window after
N seconds (default 3).
"""
import sys
import os
import argparse
from pathlib import Path

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--offscreen', action='store_true', help='Force offscreen platform')
    ap.add_argument('--auto-close', type=float, default=3.0, help='Automatically close after N seconds (0 = never)')
    args = ap.parse_args(argv)

    if args.offscreen:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    try:
        from PyQt5 import QtWidgets, QtCore
    except Exception as e:
        print('PyQt5 import failed:', e)
        return 2

    # Ensure repo module path so we can import helper
    repo_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo_root))

    try:
        from ui.qt_ui import qt_frontend as qf
    except Exception:
        # Fallback: try to load UI directly via uic with similar workaround
        from PyQt5 import uic
        ui_file = Path(__file__).resolve().parent / 'mainwindow.ui'
        # Workaround for C++-style enum qualifiers
        txt = ui_file.read_text(encoding='utf-8')
        if 'Qt::WindowModality::' in txt:
            txt = txt.replace('Qt::WindowModality::', '')
        import tempfile
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.ui', delete=False, encoding='utf-8')
        tf.write(txt); tf.flush(); tf.close()
        try:
            app = QtWidgets.QApplication([])
            win = uic.loadUi(tf.name)
            # attach loadProgram handler if present
            def _do_load_program_fallback():
                start_dir = Path(__file__).resolve().parents[2] / 'examples'
                start = str(start_dir) if start_dir.exists() else str(Path.cwd())
                fn, _ = QtWidgets.QFileDialog.getOpenFileName(win, 'Load XML program', start, 'XML Files (*.xml);;All Files (*)')
                if not fn:
                    return
                try:
                    txt = Path(fn).read_text(encoding='utf-8')
                except Exception:
                    txt = ''
                ed = getattr(win, 'xmlEditor', None)
                if ed is not None:
                    try:
                        ed.setPlainText(txt)
                    except Exception:
                        try:
                            ed.setHtml('<pre>%s</pre>' % (txt,))
                        except Exception:
                            pass
                # populate tree widget
                try:
                    from lxml import etree as ET
                except Exception:
                    import xml.etree.ElementTree as ET
                try:
                    parsed = ET.fromstring(txt.encode('utf-8'))
                except Exception:
                    parsed = None
                tw = getattr(win, 'treeWidget', None)
                if tw is not None:
                    tw.clear()
                    if parsed is not None:
                        def add_item(parent, node):
                            # coerce tag to string to avoid QTreeWidgetItem type errors
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
                        try:
                            root_text = str(parsed.tag)
                        except Exception:
                            try:
                                root_text = repr(parsed.tag)
                            except Exception:
                                root_text = '<root>'
                        root_item = QtWidgets.QTreeWidgetItem([root_text])
                        tw.addTopLevelItem(root_item)
                        for ch in list(parsed):
                            add_item(root_item, ch)
                        tw.expandAll()
            # if CuriosityNode present, init disciplines/subtopics lists
            try:
                repo_root = Path(__file__).resolve().parents[2]
                rp = str(repo_root)
                import sys
                if rp not in sys.path:
                    sys.path.insert(0, rp)
                import curiosity_drive_node as cdn
            except Exception:
                cdn = None
            if cdn is not None and parsed is not None:
                found = any((n.tag.lower() == 'curiositynode') for n in parsed.findall('.//*'))
                if found:
                    dlw = getattr(win, 'disciplinesList', None)
                    slw = getattr(win, 'subtopicsList', None)
                    if dlw is not None:
                        dlw.clear()
                        for d in getattr(cdn, 'disciplines', []):
                            try:
                                dlw.addItem(str(d))
                            except Exception:
                                dlw.addItem(repr(d))
                    if slw is not None:
                        slw.clear()
                        first = cdn.disciplines[0] if getattr(cdn, 'disciplines', None) else None
                        if first and getattr(cdn, 'subtopics', None):
                            for it in cdn.subtopics.get(first, []):
                                try:
                                    slw.addItem(str(it))
                                except Exception:
                                    slw.addItem(repr(it))
                    # connect selection change
                    try:
                        def _on_discipline_changed(curr, prev=None):
                            try:
                                txt = curr.text() if curr is not None else None
                            except Exception:
                                try:
                                    txt = str(curr)
                                except Exception:
                                    txt = None
                            slw.clear()
                            if txt and getattr(cdn, 'subtopics', None):
                                for it in cdn.subtopics.get(txt, []):
                                    try:
                                        slw.addItem(str(it))
                                    except Exception:
                                        slw.addItem(repr(it))
                        dlw.currentItemChanged.connect(_on_discipline_changed)
                    except Exception:
                        try:
                            dlw.itemSelectionChanged.connect(lambda: _on_discipline_changed(dlw.currentItem()))
                        except Exception:
                            pass
                    # set visibility
                    try:
                        win.CuriosityNodeTab.setVisible(True)
                    except Exception:
                        pass
                    # schedule a re-init to guard against later UI resets
                    try:
                        QtCore.QTimer.singleShot(700, lambda: (
                            dlw.clear() or [dlw.addItem(str(d)) for d in getattr(cdn, 'disciplines', [])] if dlw is not None else None
                        ))
                    except Exception:
                        pass
                    # set visibility of tabs
                    try:
                        win.CuriosityNodeTab.setVisible(True)
                    except Exception:
                        pass
            btn = getattr(win, 'loadProgram', None)
            if btn is not None:
                try:
                    btn.clicked.connect(_do_load_program_fallback)
                except Exception:
                    pass
            win.show()
            if args.auto_close > 0:
                QtCore.QTimer.singleShot(int(args.auto_close*1000), app.quit)
            return app.exec_()
        finally:
            try: os.unlink(tf.name)
            except Exception: pass

    # Create QApplication before loading UI to avoid 'Must construct a QApplication before a QWidget'
    app = QtWidgets.QApplication([])

    # Use helper to load ui (it applies the same enum-workaround)
    ui_file = Path(__file__).resolve().parent / 'mainwindow.ui'
    try:
        win = qf._load_ui_file(ui_file)
    except Exception as e:
        print('Loading UI failed:', e)
        return 3

    # attach a loadProgram handler to the loaded UI (if present)
    def _do_load_program():
        start_dir = Path(__file__).resolve().parents[2] / 'examples'
        start = str(start_dir) if start_dir.exists() else str(Path.cwd())
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(win, 'Load XML program', start, 'XML Files (*.xml);;All Files (*)')
        if not fn:
            return
        try:
            txt = Path(fn).read_text(encoding='utf-8')
        except Exception:
            txt = ''
        ed = getattr(win, 'xmlEditor', None)
        if ed is not None:
            try:
                ed.setPlainText(txt)
            except Exception:
                try:
                    ed.setHtml('<pre>%s</pre>' % (txt,))
                except Exception:
                    pass
        # populate tree widget
        try:
            from lxml import etree as ET
        except Exception:
            import xml.etree.ElementTree as ET
        try:
            parsed = ET.fromstring(txt.encode('utf-8'))
        except Exception:
            parsed = None
        tw = getattr(win, 'treeWidget', None)
        if tw is not None:
            tw.clear()
            if parsed is not None:
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
                try:
                    root_text = str(parsed.tag)
                except Exception:
                    try:
                        root_text = repr(parsed.tag)
                    except Exception:
                        root_text = '<root>'
                root_item = QtWidgets.QTreeWidgetItem([root_text])
                tw.addTopLevelItem(root_item)
                for ch in list(parsed):
                    add_item(root_item, ch)
                tw.expandAll()
        # init curiosity lists
        try:
            import curiosity_drive_node as cdn
        except Exception:
            cdn = None
        if cdn is not None and parsed is not None:
            found = False
            for n in parsed.findall('.//*'):
                try:
                    t = (n.tag or '').lower()
                    if t == 'curiositynode':
                        found = True; break
                    if t == 'extnode' and ( (n.get('module') or '').strip() == 'curiosity_drive_node'):
                        found = True; break
                except Exception:
                    continue
            if found:
                dlw = getattr(win, 'disciplinesList', None)
                slw = getattr(win, 'subtopicsList', None)
                if dlw is not None:
                    dlw.clear()
                    for d in getattr(cdn, 'disciplines', []):
                        dlw.addItem(str(d))
                if slw is not None:
                    slw.clear()
                    first = cdn.disciplines[0] if getattr(cdn, 'disciplines', None) else None
                    if first and getattr(cdn, 'subtopics', None):
                        for it in cdn.subtopics.get(first, []):
                            slw.addItem(str(it))
                    # connect selection change
                    try:
                        def _on_discipline_changed(curr, prev=None):
                            try:
                                txt = curr.text() if curr is not None else None
                            except Exception:
                                try:
                                    txt = str(curr)
                                except Exception:
                                    txt = None
                            slw.clear()
                            if txt and getattr(cdn, 'subtopics', None):
                                for it in cdn.subtopics.get(txt, []):
                                    slw.addItem(str(it))
                        dlw.currentItemChanged.connect(_on_discipline_changed)
                    except Exception:
                        try:
                            dlw.itemSelectionChanged.connect(lambda: _on_discipline_changed(dlw.currentItem()))
                        except Exception:
                            pass
            # also init Curiosity lists when using the other handler (_do_load_program)
    btn = getattr(win, 'loadProgram', None)
    if btn is not None:
        try:
            btn.clicked.connect(_do_load_program)
        except Exception:
            pass

    # If the loaded object is a QMainWindow it may not have a parent; show it.
    win.show()

    if args.auto_close > 0:
        QtCore.QTimer.singleShot(int(args.auto_close*1000), app.quit)

    return app.exec_()

if __name__ == '__main__':
    sys.exit(main())
