
# -*- coding: utf-8 -*-
# Safe Windows hotkey bridge with robust logging and exception safety.
import threading, time, sys

LOG_PREFIX = "[hotkeys_win]"

try:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
except Exception as e:
    user32 = None
    print(f"{LOG_PREFIX} user32 unavailable: {e}", file=sys.stderr)

MOD_CONTROL  = 0x0002
WM_HOTKEY    = 0x0312
VK_SPACE     = 0x20
VK_N         = 0x4E

SKIP_EVENT = threading.Event()
PAUSE_TOGGLE_EVENT = threading.Event()
# Event for exit hotkey (Esc or Ctrl+Q)
EXIT_EVENT = threading.Event()

_started = False

def _msg_loop():
    print(f"{LOG_PREFIX} msg loop thread starting...", file=sys.stderr)
    if user32 is None:
        print(f"{LOG_PREFIX} user32 is None; exiting thread", file=sys.stderr)
        return
    try:
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL, VK_SPACE):
            print(f"{LOG_PREFIX} RegisterHotKey Ctrl+Space failed (id=1)", file=sys.stderr)
        else:
            print(f"{LOG_PREFIX} Registered Ctrl+Space (id=1)", file=sys.stderr)
        if not user32.RegisterHotKey(None, 2, MOD_CONTROL, VK_N):
            print(f"{LOG_PREFIX} RegisterHotKey Ctrl+N failed (id=2)", file=sys.stderr)
        else:
            print(f"{LOG_PREFIX} Registered Ctrl+N (id=2)", file=sys.stderr)
        # Register Escape key (no modifiers) for exit
        VK_ESCAPE = 0x1B
        if not user32.RegisterHotKey(None, 3, 0, VK_ESCAPE):
            print(f"{LOG_PREFIX} RegisterHotKey Escape failed (id=3)", file=sys.stderr)
        else:
            print(f"{LOG_PREFIX} Registered Escape (id=3)", file=sys.stderr)
        # Register Ctrl+Q for exit
        VK_Q = 0x51
        if not user32.RegisterHotKey(None, 4, MOD_CONTROL, VK_Q):
            print(f"{LOG_PREFIX} RegisterHotKey Ctrl+Q failed (id=4)", file=sys.stderr)
        else:
            print(f"{LOG_PREFIX} Registered Ctrl+Q (id=4)", file=sys.stderr)
    except Exception as e:
        print(f"{LOG_PREFIX} RegisterHotKey error: {e}", file=sys.stderr)

    try:
        MSG = wintypes.MSG
    except Exception as e:
        print(f"{LOG_PREFIX} MSG type unavailable: {e}", file=sys.stderr)
        return

    msg = MSG()
    while True:
        try:
            res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if res == 0 or res == -1:
                time.sleep(0.05)
                continue
            if msg.message == WM_HOTKEY:
                hotkey_id = msg.wParam
                if hotkey_id == 1:
                    PAUSE_TOGGLE_EVENT.set()
                elif hotkey_id == 2:
                    SKIP_EVENT.set()
                elif hotkey_id in (3, 4):
                    EXIT_EVENT.set()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as e:
            print(f"{LOG_PREFIX} loop error: {e}", file=sys.stderr)
            time.sleep(0.05)

def start_hotkeys():
    global _started
    if _started:
        print(f"{LOG_PREFIX} already started", file=sys.stderr)
        return
    try:
        t = threading.Thread(target=_msg_loop, daemon=True)
        t.start()
        _started = True
        print(f"{LOG_PREFIX} start_hotkeys started thread", file=sys.stderr)
    except Exception as e:
        print(f"{LOG_PREFIX} start_hotkeys error: {e}", file=sys.stderr)
