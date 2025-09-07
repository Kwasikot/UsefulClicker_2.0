
import argparse
from pathlib import Path
from core.xml_engine import XMLProgram

def main():
    ap = argparse.ArgumentParser(description="UsefulClicker — Stage 2")
    ap.add_argument("xml_path", type=str, help="Path to XML scenario")
    ap.add_argument("--debug", action="store_true", help="Show debug window")
    ap.add_argument("--ui", type=str, default=None, help="UI module to use (eg. qt_ui)")
    args = ap.parse_args()
    xml_path = Path(args.xml_path); log_path = xml_path.with_suffix(".usefulclicker.log")
    # If a UI is requested, try to import corresponding ui module and run it.
    if args.ui:
        # Prefer a lightweight 'show_mainwindow_ui' script if present (shows UI without starting engine)
        try:
            mod_ui = __import__(f"ui.{args.ui}.show_mainwindow_ui", fromlist=["main"]) 
            main_ui = getattr(mod_ui, "main")
            # Delegate control to UI main (it will create QApplication and show window)
            # Call with explicit argv disabling auto-close so the window remains visible
            # (show_mainwindow_ui default auto-closes after 3s). Pass --auto-close 0.
            return main_ui(['--auto-close', '0'])
        except Exception:
            # Fallback to full frontend that integrates with engine
            try:
                mod = __import__(f"ui.{args.ui}.qt_frontend", fromlist=["run_ui"]) 
                run_ui = getattr(mod, "run_ui")
                return run_ui(str(xml_path))
            except Exception as e:
                print(f"Failed to start UI '{args.ui}': {e}")
    prog = XMLProgram(xml_path, debug=args.debug, log_path=log_path)
    # Ensure program starts paused when run from console so user can inspect state
    try:
        prog.paused = True
        print('[main] XMLProgram started in PAUSED mode. Use hotkeys or UI to resume.')
    except Exception:
        pass
    prog.run()
if __name__ == "__main__":
    main()
