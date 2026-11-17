"""chiaki-ng's PS5 codec kept in step with SmoovPlay's HDR setting (framegen/chiaki_settings.py). The registry tests use
a key of their own under HKEY_CURRENT_USER\\Software, deleted afterwards; chiaki-ng's own settings aren't touched."""
import sys
import uuid

import pytest

from framegen import chiaki_settings as cs
from framegen.chiaki_settings import HDR, PLAIN, wanted


def test_auto_follows_the_display():
    assert wanted("auto", None, hdr_display=True, nvidia=True) == HDR  # not set yet: chiaki-ng's default, H.265
    assert wanted("auto", "h265", hdr_display=True, nvidia=True) == HDR
    assert wanted("auto", "h264", hdr_display=True, nvidia=True) == HDR  # HDR needs H.265
    assert wanted("auto", HDR, hdr_display=True, nvidia=True) is None  # already
    assert wanted("auto", HDR, hdr_display=False, nvidia=True) == PLAIN  # no HDR display: the PS5 sends SDR itself
    assert wanted("auto", "h265", hdr_display=False, nvidia=True) is None
    assert wanted("auto", "h264", hdr_display=False, nvidia=True) is None  # the player's choice, left alone


def test_on_asks_for_hdr_and_off_leaves_it_alone():
    for on in ("sdr", "hdr10"):
        assert wanted(on, "h265", hdr_display=False, nvidia=True) == HDR
        assert wanted(on, HDR, hdr_display=False, nvidia=True) is None
    for current in (None, "h264", "h265", HDR):
        assert wanted("off", current, hdr_display=True, nvidia=True) is None


def test_without_an_nvidia_card_no_hdr():
    # SmoovPlay's HDR needs CUDA: an HDR stream would only look washed out
    assert wanted("auto", "h265", hdr_display=True, nvidia=False) is None
    assert wanted("auto", HDR, hdr_display=True, nvidia=False) == PLAIN
    assert wanted("hdr10", "h265", hdr_display=True, nvidia=False) is None


@pytest.fixture
def key():
    if sys.platform != "win32":
        pytest.skip("Windows registry")
    import winreg
    path = rf"Software\SmoovPlayTest-{uuid.uuid4().hex[:8]}\settings"
    yield path
    for p in (path, path.rsplit("\\", 1)[0]):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, p)
        except OSError:
            pass


def _read(path):
    import winreg
    out = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
        for name in cs.NAMES:
            try:
                out[name] = winreg.QueryValueEx(k, name)
            except FileNotFoundError:
                out[name] = None
    return out


def test_match_codec_writes_both_codecs_as_text(key, monkeypatch, capsys):
    import winreg
    monkeypatch.delenv("FRAMEGEN_CHIAKI_CODEC", raising=False)
    monkeypatch.setattr(cs, "_hdr_display", lambda: True)
    assert cs.match_codec("auto", nvidia=True, key=key) == HDR
    assert _read(key) == {n: (HDR, winreg.REG_SZ) for n in cs.NAMES}
    out = capsys.readouterr().out
    assert "set to H.265 HDR (was H.265), as this display has Windows' HDR on" in out
    assert cs.match_codec("auto", nvidia=True, key=key) is None  # already: nothing said
    assert capsys.readouterr().out == ""
    monkeypatch.setattr(cs, "_hdr_display", lambda: False)
    assert cs.match_codec("auto", nvidia=True, key=key) == PLAIN
    assert _read(key) == {n: (PLAIN, winreg.REG_SZ) for n in cs.NAMES}
    assert "doesn't have Windows' HDR on" in capsys.readouterr().out


def test_match_codec_off_and_opt_out_touch_nothing(key, monkeypatch):
    monkeypatch.setattr(cs, "_hdr_display", lambda: True)
    assert cs.match_codec("off", nvidia=True, key=key) is None
    monkeypatch.setenv("FRAMEGEN_CHIAKI_CODEC", "0")
    assert cs.match_codec("auto", nvidia=True, key=key) is None
    import winreg
    with pytest.raises(FileNotFoundError):  # the key was never even made
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, key)
