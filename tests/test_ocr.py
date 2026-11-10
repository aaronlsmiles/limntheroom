import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from seam import ocr

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision")


def word_image(text="HELLO", size=(1280, 720), font_px=140):
    img = Image.new("RGB", size, (240, 238, 232))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_px)
    except OSError:
        font = ImageFont.load_default(font_px)
    d.text((360, 280), text, fill=(20, 20, 20), font=font)
    return np.asarray(img)


def test_reads_a_rendered_word():
    assert ocr.normalise(ocr.recognise(word_image())) == "HELLO"


def test_box_crop():
    img = word_image()
    assert ocr.normalise(ocr.recognise(img, box=(300, 220, 1000, 500))) == "HELLO"
    assert ocr.recognise(img, box=(0, 0, 200, 200)) == ""


def test_cer():
    assert ocr.cer("HELLO", "HELLO") == 0.0
    assert ocr.cer("HELLO", "HELP") == pytest.approx(0.4)
    assert ocr.cer("hello  world", "HELLO WORLD") == 0.0
    assert ocr.cer("", "X") is None
    assert ocr.cer("AB", "") == 1.0
    assert ocr.levenshtein("kitten", "sitting") == 3


def test_cer_series_every_third():
    img = word_image()
    frames = [img] * 7
    box = (300, 220, 1000, 500)
    s = ocr.cer_series(frames, frames, [box] * 7, valid=[True] * 6 + [False], every=3)
    assert s[0] == 0.0 and s[3] == 0.0 and s[1] is None and s[6] is None
