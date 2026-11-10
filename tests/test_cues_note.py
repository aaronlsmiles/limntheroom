"""seam.cues.note: OCR words with Apple Vision (accurate mode), and the note-readable event."""
import sys

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from seam.cues import note

mac = pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision is macOS only")
WORD = "BELL"   # a neutral fixture word


def _word_image(text=WORD, w=800, h=300):
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 120)
    except OSError:
        font = ImageFont.load_default()
    d.text((120, 80), text, fill="black", font=font)
    return np.array(img)


@mac
def test_ocr_rendered_word():
    words = note.ocr_words(_word_image())
    assert [w["text"].upper() for w in words] == [WORD]
    (w,) = words
    assert w["confidence"] > 0.3
    x, y, bw, bh = w["box"]
    assert 0 <= x < 800 and 0 <= y < 300 and bw > 100 and bh > 40
    assert 60 <= y <= 140                     # top-left origin: the text sits in the upper half


@mac
def test_ocr_blank():
    assert note.ocr_words(np.full((200, 300, 3), 255, np.uint8)) == []


def test_stable_word():
    assert note.stable_word([None, None, WORD, WORD, WORD, WORD], min_reads=3) == (2, WORD)
    assert note.stable_word([None, WORD, "BEL", WORD, None], min_reads=3) is None
    assert note.stable_word([], min_reads=3) is None


def test_read_text_joins_and_uppercases():
    assert note.read_text([{"text": "bell", "confidence": 0.9, "box": [0, 0, 1, 1]}]) == WORD
    assert note.read_text([]) is None


@mac
def test_detect_on_frames():
    blank = np.full((300, 800, 3), 255, np.uint8)
    frames = np.stack([blank] * 6 + [_word_image()] * 9)
    (e,) = note.detect(frames, fps=15, every=3, min_reads=2)
    assert e["cue"] == "note" and e["source"] == "detector:note"
    assert e["what"] == f'a note reading "{WORD}" is set down'
    assert e["evidence"]["word"] == WORD
    assert e["evidence"]["first_frame"] == 6
    assert e["t"] == round(6 / 15, 3)


@mac
def test_detect_box_crop():
    frames = np.stack([_word_image()] * 3)
    (e,) = note.detect(frames, fps=15, every=1, min_reads=2, box=(100, 60, 500, 180))
    assert e["evidence"]["word"] == WORD and e["evidence"]["box"] == [100, 60, 500, 180]


@mac
@pytest.mark.parametrize("font_path", ["/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
                                       "/System/Library/Fonts/MarkerFelt.ttc"])
def test_ocr_handwriting_style_font(font_path):
    """A proxy for block capitals written by hand: script-style system fonts, slightly rotated."""
    try:
        font = ImageFont.truetype(font_path, 130)
    except OSError:
        pytest.skip(f"{font_path} not installed")
    img = Image.new("RGB", (800, 320), "white")
    ImageDraw.Draw(img).text((110, 70), WORD, fill=(20, 20, 30), font=font)
    img = img.rotate(4, fillcolor="white")
    assert note.read_text(note.ocr_words(np.array(img))) == WORD


def test_thresholds_are_named_constants():
    import inspect
    assert (note.EVERY, note.MIN_READS) == (3, 3)
    p = inspect.signature(note.detect).parameters
    assert p["every"].default == note.EVERY and p["min_reads"].default == note.MIN_READS


def test_missing_vision_is_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "Vision", None)       # import Vision -> ImportError
    with pytest.raises(ImportError, match="pyobjc-framework-Vision"):
        note.ocr_words(np.full((20, 20, 3), 255, np.uint8))


# --- call 132 (Aaron, 9 Nov): the take's note is read inside its own track's box -------------------------

def test_box_from_track_is_the_last_frame_padded_and_clipped():
    t = np.zeros((5, 100, 200), bool)
    t[1:3, 20:40, 50:90] = True          # tracked in frames 1-2
    t[3, 22:42, 52:92] = True            # moved a little by the last tracked frame, which sets the box
    assert note.box_from_track(t) == (52 - 10, 22 - 10, 92 - 52 + 20, 42 - 22 + 20)
    edge = np.zeros((2, 100, 200), bool)
    edge[1, 0:30, 180:200] = True        # at the frame's corner: the pad is clipped
    assert note.box_from_track(edge) == (170, 0, 30, 40)
    assert note.BOX_PAD == 10


def test_box_from_an_empty_track_is_an_error():
    with pytest.raises(ValueError):
        note.box_from_track(np.zeros((3, 10, 10), bool))


def _two_words(w=800, h=300):
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 100)
    d.text((20, 90), "LARR", fill="black", font=font)     # what OCR made of the ink creature's legs
    d.text((440, 90), WORD, fill="black", font=font)      # the note
    return np.array(img)


@mac
def test_the_note_box_keeps_other_marks_out_of_the_word():
    frames = np.stack([_two_words()] * 3)
    (whole,) = note.detect(frames, fps=15, every=1, min_reads=2)
    assert whole["evidence"]["word"] == f"LARR {WORD}"
    track = np.zeros((3, 300, 800), bool)
    track[:, 80:220, 430:760] = True
    (boxed,) = note.detect(frames, fps=15, every=1, min_reads=2, box=note.box_from_track(track))
    assert boxed["evidence"]["word"] == WORD
