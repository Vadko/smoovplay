"""RTX VSR (framegen/rtxvsr.py): which way it runs, NVIDIA's quality levels, and the packed 10-bit frames NVIDIA's
package takes. The upscaling itself needs an RTX card and NVIDIA's package: checked by hand, not here."""
import torch

from framegen import rtxvsr
from framegen.rtxvsr import CLEAN, VfxVsr, pack_rgba10


def _fields(packed):
    p = packed.to(torch.int64) & 0xFFFFFFFF
    return p & 1023, (p >> 10) & 1023, (p >> 20) & 1023, p >> 30


def test_8_bit_frames_pack_into_10_bits_as_gl_reads_them():
    # RGB10_A2 read as GL_UNSIGNED_INT_2_10_10_10_REV: red in the low bits, as NVIDIA packs it
    rgba = torch.zeros((2, 3, 4), dtype=torch.uint8)
    rgba[0, 0, :3] = torch.tensor([255, 0, 0])
    rgba[0, 1, :3] = torch.tensor([0, 255, 0])
    rgba[0, 2, :3] = torch.tensor([0, 0, 255])
    rgba[1, 0, :3] = torch.tensor([1, 128, 254])
    out = torch.empty((2, 3), dtype=torch.int32)
    r, g, b, a = _fields(pack_rgba10(rgba, out))
    assert r[0].tolist() == [1023, 0, 0] and g[0].tolist() == [0, 1023, 0] and b[0].tolist() == [0, 0, 1023]
    assert (r[1, 0], g[1, 0], b[1, 0]) == (4, 514, 1019)  # v * 1023 / 255, exactly
    assert (a == 3).all()  # opaque


def test_every_8_bit_value_comes_back_from_10_bits():
    v = torch.arange(256, dtype=torch.uint8)
    rgba = torch.stack([v, v.flip(0), v, v], -1).reshape(16, 16, 4)
    r, g, _, _ = _fields(pack_rgba10(rgba, torch.empty((16, 16), dtype=torch.int32)))
    assert torch.equal((r.float() * 255 / 1023).round().to(torch.uint8).flatten(), v)  # as GL reads it, 8 bits back
    assert torch.equal((g.float() * 255 / 1023).round().to(torch.uint8).flatten(), v.flip(0))


def test_float_frames_round_to_10_bits():
    rgba = torch.tensor([[[0.0, 0.5, 1.0, 1.0], [1.2, -0.1, 0.25, 1.0]]], dtype=torch.float16)
    r, g, b, _ = _fields(pack_rgba10(rgba, torch.empty((1, 2), dtype=torch.int32)))
    assert r[0].tolist() == [0, 1023] and g[0].tolist() == [512, 0] and b[0].tolist() == [1023, 256]


def test_quality_levels_and_the_models_for_clean_video():
    assert [VfxVsr.level(q, False) for q in (1, 2, 3, 4)] == [1, 2, 3, 4]  # NVIDIA's LOW..ULTRA
    assert [VfxVsr.level(q, True) for q in (1, 2, 3, 4)] == [16, 17, 18, 19]  # HIGHBITRATE_LOW..ULTRA
    assert CLEAN == 15 and VfxVsr.level(0, False) == 1 and VfxVsr.level(9, True) == 19


def test_nvidias_package_first_the_sdk_for_developers(monkeypatch):
    monkeypatch.delenv("FRAMEGEN_VSR", raising=False)
    monkeypatch.setattr(rtxvsr, "vfx_reason", lambda: None)
    monkeypatch.setattr(rtxvsr, "sdk_reason", lambda: None)
    assert rtxvsr.backend() == ("vfx", None)
    monkeypatch.setenv("FRAMEGEN_VSR", "sdk")
    assert rtxvsr.backend() == ("sdk", None)
    monkeypatch.setattr(rtxvsr, "sdk_reason", lambda: "NV_RTX_VIDEO_SDK isn't set")
    assert rtxvsr.backend() == ("vfx", None)  # (only one there: that one)
    monkeypatch.setattr(rtxvsr, "vfx_reason", lambda: "it comes with NVIDIA VFG's download")
    name, why = rtxvsr.backend()
    assert name is None and why == "it comes with NVIDIA VFG's download"  # what people see is the package's reason
    assert rtxvsr.unavailable_reason() == why


def test_a_broken_package_check_never_stops_the_window(monkeypatch):
    monkeypatch.delenv("FRAMEGEN_VSR", raising=False)

    def broken():
        raise OSError("bad install")

    monkeypatch.setattr(rtxvsr, "vfx_reason", broken)
    monkeypatch.setattr(rtxvsr, "sdk_reason", lambda: "NV_RTX_VIDEO_SDK isn't set")
    name, why = rtxvsr.backend()
    assert name is None and "couldn't be checked" in why


def test_only_the_sdk_way_may_log_its_timings():
    assert VfxVsr.private and not rtxvsr.RtxVsr.private  # NVIDIA's package's licence: no published benchmarks
    assert VfxVsr.out_format == "rgb10a2" and rtxvsr.RtxVsr.out_format == "rgba8"
