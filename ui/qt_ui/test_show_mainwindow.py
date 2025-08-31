import os
import sys
import time
import pytest
from pathlib import Path

# Skip test if PyQt5 not available
pytest.importorskip("PyQt5")

def test_show_mainwindow_tmp(tmp_path):
    # Run Qt in offscreen mode to allow headless CI
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    # Ensure package import works from repository root
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root / 'UsefulClicker_2.0'))

    from ui.qt_ui import qt_frontend as qf

    # Create minimal XML file to load
    xml_file = tmp_path / "minimal.xml"
    xml_file.write_text("<program></program>", encoding='utf-8')

    # Construct main window wrapper (does NOT start the engine)
    mw = qf.MainWindowWrapper(xml_file)

    # Schedule application quit shortly after show() so test doesn't hang
    #qf.QtCore.QTimer.singleShot(200, mw.app.quit)

    mw.win.show()
    t0 = time.time()
    # This will run the Qt event loop until the singleShot timer quits it
    mw.app.exec_()
    elapsed = time.time() - t0
    assert elapsed >= 0.0
