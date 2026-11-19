"""The Looks page's preview (framegen/looks_preview.py): the sample pictures, the drawing, and the launcher's link."""
import io
import json

import cv2
import numpy as np
import pytest

from framegen import looks
from framegen.looks_preview import Previewer, samples, serve


@pytest.fixture
def lib(tmp_path):
    return looks.Library(tmp_path / "looks")


def test_the_sample_pictures_ship_credited():
    listed = samples()
    assert len(listed) >= 6
    assert len({s["id"] for s in listed}) == len(listed)
    for s in listed:
        img = cv2.imread(s["path"])
        assert img is not None and img.shape == (720, 1280, 3), s["id"]
        assert s["game"] in s["credit"] and "©" in s["credit"], s["credit"]
        assert s["scene"]
    assert looks.schema()["samples"] == listed  # what the launcher gets


def test_the_preview_draws_the_look_at_the_size_asked(lib):
    pv = Previewer(lib, use_gl=False)
    sid = samples()[0]["id"]
    plain = pv.picture(sid, 320, 180)
    out = pv.render(looks.BUILTIN["noir"], sid, 320, 180)
    assert out.shape == (180, 320, 3)
    assert np.abs(out.astype(int) - plain).mean() > 5  # black & white
    assert np.array_equal(pv.render({"name": "x", "nodes": []}, sid, 320, 180), plain)
    with pytest.raises(ValueError, match="no sample picture"):
        pv.render(looks.BUILTIN["noir"], "nope", 320, 180)


def test_the_launcher_link(lib, tmp_path):
    pv = Previewer(lib, use_gl=False)
    sid = samples()[0]["id"]
    out_file = tmp_path / "preview-0.bmp"
    lines = [json.dumps({"id": 1, "look": looks.BUILTIN["vivid"], "sample": sid, "width": 256, "height": 144,
                         "out": str(out_file)}),
             "not json",
             json.dumps({"id": 3, "look": looks.BUILTIN["vivid"], "sample": "nope", "out": str(out_file)}),
             ""]
    out = io.StringIO()
    assert serve(io.StringIO("\n".join(lines) + "\n"), out, pv) == 0
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert answers[0]["ready"] and answers[0]["gl"] is False and answers[0]["samples"][0]["id"] == sid
    assert answers[1]["id"] == 1 and answers[1]["file"] == str(out_file) and answers[1]["sample"] == sid
    assert cv2.imread(str(out_file)).shape == (144, 256, 3)
    assert answers[2]["id"] is None and "error" in answers[2]
    assert answers[3]["id"] == 3 and "no sample picture" in answers[3]["error"]
    assert len(answers) == 4


def test_the_opengl_preview_matches_the_reference(lib):
    pytest.importorskip("glfw")
    pv = Previewer(lib, use_gl=True)
    if pv.gl is None:
        pytest.skip("no OpenGL here")
    try:
        cpu = Previewer(lib, use_gl=False)
        for name in ("cinematic", "vhs", "dreamy", "assist-deutan"):
            for s in samples()[:3]:
                a = pv.render(looks.BUILTIN[name], s["id"], 400, 224)
                b = cpu.render(looks.BUILTIN[name], s["id"], 400, 224)
                d = np.abs(a.astype(int) - b)
                assert d.max() <= 2 and d.mean() < 0.5, (name, s["id"], d.max(), d.mean())
    finally:
        pv.close()


def test_pictures_are_read_and_written_in_a_folder_with_chinese_letters(tmp_path):
    """OpenCV's imread/imwrite open files by Windows' narrow names and fail on such a folder (issue 24: an install
    folder with Chinese letters); framegen.imagefile has Python open them."""
    from framegen.imagefile import read_image, write_image
    folder = tmp_path / "杂项 é"
    folder.mkdir()
    img = np.zeros((6, 8, 4), np.uint8)
    img[..., 2], img[..., 3] = 200, 128
    assert write_image(folder / "x.png", img)
    back = read_image(folder / "x.png", cv2.IMREAD_UNCHANGED)
    assert back is not None and back.shape == (6, 8, 4) and (back == img).all()
    assert read_image(folder / "x.png").shape == (6, 8, 3)  # colour, as cv2.imread gives by default
    assert read_image(folder / "missing.png") is None
    assert not write_image(folder / "no such folder" / "x.png", img)
