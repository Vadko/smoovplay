"""How the video window shows its frames (GLWindowSink._choose_presentation). With Windows' HDR on, an SDR picture
goes through DXGI and fullscreen is a borderless window, so the display stays in HDR: OpenGL's own fullscreen
switches it to SDR while the window is in front. Stand-ins for the window and DXGI: no window opens."""
from types import SimpleNamespace

from framegen import dxgi_present, io


def _window(monkeypatch, hdr_on, present="gl", fullscreen=True, overlay=None, dxgi_works=True):
    w = io.GLWindowSink.__new__(io.GLWindowSink)  # no GL, no window
    w.settings = SimpleNamespace(present=present, fullscreen=fullscreen)
    w.overlay_of, w.dx, w.hdr10, w.keep_hdr, w.fs_style = overlay, None, False, False, "none"
    opened = []

    def open_dxgi(width, height, hdr=False, peak=1000.0, keep_hdr=False):
        opened.append({"hdr": hdr, "keep_hdr": keep_hdr})
        w.dx = SimpleNamespace(hdr=hdr) if dxgi_works else None
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
