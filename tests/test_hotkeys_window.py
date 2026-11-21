"""App window mode's shortcuts for real (framegen/hotkeys.py): a GLFW window whose thread holds system-wide shortcuts
stays answering past Windows' 5 s hang check, and a shortcut pressed still arrives. It shows a small window for about
7 s and presses keys through SendInput, so it only runs when asked: SMOOVPLAY_WINDOW_TESTS=1, with nobody playing.
The stand-in tests are in test_hotkeys.py."""
import ctypes
import os
import sys

import pytest

from framegen import hotkeys
from framegen.hotkeys import Hotkeys, parse

pytestmark = [
    pytest.mark.skipif(sys.platform != "win32", reason="Windows' shortcuts and hang check"),
    pytest.mark.skipif(os.environ.get("SMOOVPLAY_WINDOW_TESTS") != "1",
                       reason="shows a window and presses keys: set SMOOVPLAY_WINDOW_TESTS=1"),
]


def test_a_window_with_shortcuts_is_never_called_hung():
    """For real: a GLFW window, its thread holding system-wide shortcuts (obscure ones, so nothing else is taken),
    polled as the video window does for longer than Windows' 5 s hang check, then a shortcut pressed."""
    import time
    from ctypes import wintypes as wt
    glfw = pytest.importorskip("glfw")
    if not glfw.init():
        pytest.skip("no display")
    picked = {a: f"Ctrl+Alt+Shift+F{13 + i}" for i, a in enumerate(hotkeys.ACTIONS)}
    glfw.window_hint(glfw.VISIBLE, glfw.TRUE)
    glfw.window_hint(glfw.FOCUSED, glfw.FALSE)
    glfw.window_hint(glfw.FOCUS_ON_SHOW, glfw.FALSE)
    win = glfw.create_window(160, 90, "hotkeys test", None, None)
    h = Hotkeys(picked)
    try:
        assert all(h.got.values()), h.taken
        u32 = ctypes.windll.user32
        u32.IsHungAppWindow.argtypes = [wt.HWND]
        hwnd = glfw.get_win32_window(win)
        end, hung = time.perf_counter() + 6.5, False
        while time.perf_counter() < end:
            h.poll()
            glfw.poll_events()
            hung |= bool(u32.IsHungAppWindow(hwnd))
            time.sleep(1 / 60)
        assert not hung

        quit_combo = parse(picked["quit"])  # pressed through SendInput: Ctrl, Alt, Shift, F14, and up again
        vks = [0x11, 0x12, 0x10, quit_combo.vk]

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        class INPUT(ctypes.Structure):
            class _U(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
            _anonymous_ = ("u",)
            _fields_ = [("type", wt.DWORD), ("u", _U)]

        keys = [INPUT(type=1, ki=KEYBDINPUT(wVk=vk)) for vk in vks]
        keys += [INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=2)) for vk in reversed(vks)]  # KEYEVENTF_KEYUP
        u32.SendInput(len(keys), (INPUT * len(keys))(*keys), ctypes.sizeof(INPUT))
        got, end = [], time.perf_counter() + 2
        while time.perf_counter() < end and not got:
            got = h.poll()
            glfw.poll_events()
            time.sleep(0.01)
        assert got == ["quit"]
    finally:
        h.close()
        glfw.destroy_window(win)
