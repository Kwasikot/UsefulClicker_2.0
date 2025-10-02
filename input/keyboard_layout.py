import sys
import time


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _get_foreground_langid_windows() -> int | None:
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        GetForegroundWindow = user32.GetForegroundWindow
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        GetKeyboardLayout = user32.GetKeyboardLayout
        AttachThreadInput = user32.AttachThreadInput
        GetCurrentThreadId = ctypes.windll.kernel32.GetCurrentThreadId

        hwnd = GetForegroundWindow()
        if not hwnd:
            return None

        pid = wintypes.DWORD()
        thread_id = GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not thread_id:
            return None

        # Try to get the layout of the foreground thread
        hkl = GetKeyboardLayout(thread_id)
        langid = hkl & 0xFFFF
        return langid
    except Exception:
        return None


def _primary_langid(langid: int) -> int:
    # PRIMARYLANGID macro: low 10 bits
    return langid & 0x03FF


def _is_russian_langid(langid: int) -> bool:
    # Russian primary LANGID is 0x19
    return _primary_langid(langid) == 0x19


def _is_english_langid(langid: int) -> bool:
    # English primary LANGID is 0x09
    return _primary_langid(langid) == 0x09


def ensure_english_layout(max_attempts: int = 6, delay: float = 0.15) -> None:
    """Ensure the active keyboard layout is English on Windows.

    - If current layout is Russian, toggles layouts via Win+Space until English.
    - On non-Windows platforms, no-op.
    - Best-effort; suppresses errors to avoid breaking the CLI.
    """
    if not _is_windows():
        return

    try:
        import pyautogui
    except Exception:
        # If pyautogui is unavailable, we can't synthesize the switch; give up silently
        return

    try:
        langid = _get_foreground_langid_windows()
        if langid is not None and _is_english_langid(langid):
            return
        # If Russian (or unknown but not English), attempt to cycle layouts
        attempts = 0
        while attempts < max_attempts:
            langid = _get_foreground_langid_windows()
            if langid is not None and _is_english_langid(langid):
                break
            # Press Win+Space to cycle input method
            try:
                pyautogui.hotkey('win', 'space')
            except Exception:
                # As a fallback, try Alt+Shift (older configs)
                try:
                    pyautogui.hotkey('alt', 'shift')
                except Exception:
                    pass
            time.sleep(delay)
            attempts += 1
    except Exception:
        # Never fail the app due to layout switching
        return

