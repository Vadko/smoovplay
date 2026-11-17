"""How the video window shows its frames (GLWindowSink._choose_presentation). With Windows' HDR on, an SDR picture
goes through DXGI and fullscreen is a borderless window, so the display stays in HDR: OpenGL's own fullscreen
switches it to SDR while the window is in front. Stand-ins for the window and DXGI: no window opens."""
from types import SimpleNamespace

from framegen import dxgi_present, io


def _window(monkeypatch, hdr_on, present="gl", fullscreen=True, overlay=None, dxgi_works=True, hdr10_works=True):
    w = io.GLWindowSink.__new__(io.GLWindowSink)  # no GL, no window
    w.settings = SimpleNamespace(present=present, fullscreen=fullscreen)
    w.overlay_of, w.dx, w.hdr10, w.keep_hdr, w.fs_style = overlay, None, False, False, "none"
    w._borderless = False
    opened = []

    def open_dxgi(width, height, hdr=False, peak=1000.0, keep_hdr=False):
        opened.append({"hdr": hdr, "keep_hdr": keep_hdr})
        w.dx = SimpleNamespace(hdr=hdr) if dxgi_works and (hdr10_works or not hdr) else None
    monkeypatch.setattr(w, "_open_dxgi", open_dxgi)
    monkeypatch.setattr(io, "windows_hdr_on", lambda: hdr_on)
    monkeypatch.setattr(io, "KEEP_HDR", True)
    monkeypatch.setattr(io, "FULLSCREEN_STYLE", "none")
    return w, opened


def test_windows_hdr_on_sends_sdr_through_dxgi_with_borderless_fullscreen(monkeypatch):
    for present in ("gl", "dxgi"):
        for fullscreen in (True, False):
            w, opened = _window(monkeypatch, hdr_on=True, present=present, fullscreen=fullscreen)
            w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
            assert opened == [{"hdr": False, "keep_hdr": True}]
            assert (w.keep_hdr, w.hdr10, w.fs_style) == (True, False, "borderless")


def test_without_windows_hdr_nothing_changes(monkeypatch, capsys):
    w, opened = _window(monkeypatch, hdr_on=False)  # Standard: OpenGL's own
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert (opened, w.dx, w.keep_hdr, w.fs_style) == ([], None, False, "none")
    w, opened = _window(monkeypatch, hdr_on=False, present="dxgi", fullscreen=False)  # Low delay in a window
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert opened == [{"hdr": False, "keep_hdr": False}] and (w.keep_hdr, w.fs_style) == (False, "none")
    w, opened = _window(monkeypatch, hdr_on=False, present="dxgi", fullscreen=True)  # fullscreen: Standard
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert opened == [] and "fullscreen: standard presentation" in capsys.readouterr().out


def test_turned_off_and_window_capture_keep_opengl(monkeypatch):
    w, opened = _window(monkeypatch, hdr_on=True)
    monkeypatch.setattr(io, "KEEP_HDR", False)  # FRAMEGEN_KEEP_HDR=0
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert (opened, w.dx, w.keep_hdr) == ([], None, False)
    w, opened = _window(monkeypatch, hdr_on=True, overlay=lambda: None)  # window capture's overlay
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert (opened, w.dx, w.keep_hdr) == ([], None, False)


def test_without_dxgi_it_falls_back_to_opengl_once(monkeypatch):
    w, opened = _window(monkeypatch, hdr_on=True, present="dxgi", fullscreen=False, dxgi_works=False)
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert len(opened) == 1  # Low delay would fail the same way: not tried again
    assert (w.dx, w.keep_hdr, w.fs_style) == (None, False, "none")


def test_hdr_output_is_unchanged(monkeypatch):
    w, opened = _window(monkeypatch, hdr_on=True)
    w._choose_presentation(1920, 1080, hdr=True, hdr_peak=800.0)
    assert opened == [{"hdr": True, "keep_hdr": False}]
    assert (w.hdr10, w.keep_hdr, w.fs_style) == (True, False, "borderless")


def test_hdr_output_failing_still_keeps_windows_hdr_on(monkeypatch):
    # the 10-bit HDR10 swap chain can't be made: the 8-bit one, so fullscreen still doesn't switch the display to SDR
    w, opened = _window(monkeypatch, hdr_on=True, hdr10_works=False)
    w._choose_presentation(1920, 1080, hdr=True, hdr_peak=800.0)
    assert opened == [{"hdr": True, "keep_hdr": False}, {"hdr": False, "keep_hdr": True}]
    assert (w.hdr10, w.keep_hdr, w.fs_style) == (False, True, "borderless")
    w, opened = _window(monkeypatch, hdr_on=False, present="dxgi", fullscreen=False, hdr10_works=False)
    w._choose_presentation(1920, 1080, hdr=True, hdr_peak=800.0)  # without Windows' HDR: Low delay, as before
    assert opened == [{"hdr": True, "keep_hdr": False}, {"hdr": False, "keep_hdr": False}] and not w.keep_hdr


def test_a_window_on_dxgi_for_hdr_alone_never_tears(monkeypatch):
    w, _ = _window(monkeypatch, hdr_on=True, present="gl")
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert not w._may_tear()  # a window, Standard picked: as the compositor, no tear lines
    w._borderless = True
    assert w._may_tear()  # fullscreen: VSync off tears, as OpenGL's fullscreen did
    w._borderless, w.settings.present = False, "dxgi"
    assert w._may_tear()  # Low delay picked on purpose
    w, _ = _window(monkeypatch, hdr_on=False, present="dxgi", fullscreen=False)
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    assert w._may_tear()


def test_present_row_says_why_it_cant_change(monkeypatch):
    w, _ = _window(monkeypatch, hdr_on=True)
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    w.unavailable = {"present": "HDR output always uses the low-delay presentation."}  # run.py's, before a fallback
    w.note_presentation()
    assert w.unavailable["present"] == io.KEEP_HDR_REASON
    w, _ = _window(monkeypatch, hdr_on=False)
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    w.unavailable = {}
    w.note_presentation()
    assert w.unavailable == {}


def test_fullscreen_after_windows_hdr_was_turned_on_says_so(monkeypatch):
    w, _ = _window(monkeypatch, hdr_on=False, fullscreen=False)
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)  # OpenGL's own: HDR was off then
    toasts, went = [], []
    w.glfw, w.menu = SimpleNamespace(), SimpleNamespace(open=True)
    w.toast = lambda text, seconds=2.0: toasts.append(text)
    monkeypatch.setattr(w, "_set_fullscreen", went.append)
    monkeypatch.setattr(io, "windows_hdr_on", lambda: True)  # Win+Alt+B during play
    w.settings.fullscreen = True
    w._apply("fullscreen")
    assert went == [True] and toasts and "switches the display to SDR until you press Play again" in toasts[0]


def test_fullscreen_key_goes_borderless(monkeypatch):
    w, _ = _window(monkeypatch, hdr_on=True)
    w._choose_presentation(1920, 1080, hdr=False, hdr_peak=1000.0)
    w.glfw, w.win, went = SimpleNamespace(), object(), []
    monkeypatch.setattr(w, "_set_borderless", went.append)
    w._set_fullscreen(True)  # F, or fullscreen on when the window opens
    w._set_fullscreen(False)
    assert went == [True, False]  # never GLFW's fullscreen, which would switch the display to SDR


def test_windows_hdr_on_reads_the_main_display(monkeypatch):
    monkeypatch.setattr(io.sys, "platform", "win32")
    monkeypatch.setattr(dxgi_present, "display_hdr", lambda hwnd=None: {"hdr": True})
    assert io.windows_hdr_on()
    monkeypatch.setattr(dxgi_present, "display_hdr", lambda hwnd=None: {"hdr": False})
    assert not io.windows_hdr_on()
    monkeypatch.setattr(dxgi_present, "display_hdr", lambda hwnd=None: None)  # not found
    assert not io.windows_hdr_on()

    def broken(hwnd=None):
        raise OSError("no DXGI")
    monkeypatch.setattr(dxgi_present, "display_hdr", broken)
    assert not io.windows_hdr_on()
    monkeypatch.setattr(io.sys, "platform", "linux")
    monkeypatch.setattr(dxgi_present, "display_hdr", lambda hwnd=None: {"hdr": True})
    assert not io.windows_hdr_on()
