"""Note cue: the handwritten note becomes readable, read with Apple Vision OCR (macOS, pyobjc).

``ocr_words`` runs ``VNRecognizeTextRequest`` at the accurate recognition level (revision 3 reads
handwriting as well as print) with language correction on, and returns words with pixel boxes in a
top-left origin. ``detect`` reads every ``every``-th analysis frame (inside an optional note ``box``)
and fires when the same text is read ``min_reads`` samples in a row; ``t`` is that run's first sample.

**The box (hub call 132, Aaron, 9 Nov).** On a take the note is read inside its own track's box:
``box_from_track`` gives the note track's bounding box in its last tracked frame, padded by ``BOX_PAD`` px
and clipped to the frame. Read on the whole frame, OCR took the ink creature's legs for letters
("LARR JUMP" on t05c).

Sub-plan C's ``seam/ocr.py`` (character error rate on the note box) is a different module.
"""
from __future__ import annotations

import cv2
import numpy as np

from .sheet import make_event

EVERY = 3       # OCR every 3rd 15 fps frame (5 reads a second): the note lies still once set down
MIN_READS = 3   # the same text read 3 samples running (0.6 s) before the note counts as readable
BOX_PAD = 10    # px around the note track's box (call 132)


def box_from_track(track, pad: int = BOX_PAD) -> tuple[int, int, int, int]:
    """(x, y, w, h): the note track's bounding box in its last non-empty frame, padded and clipped."""
    track = np.asarray(track, bool)
    nonempty = [i for i in range(len(track)) if track[i].any()]
    if not nonempty:
        raise ValueError("note: the note's track is empty in every frame")
    ys, xs = np.nonzero(track[nonempty[-1]])
    h, w = track.shape[1:]
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1, y1 = min(w, int(xs.max()) + 1 + pad), min(h, int(ys.max()) + 1 + pad)
    return x0, y0, x1 - x0, y1 - y0


def ocr_words(rgb: np.ndarray, accurate: bool = True, language_correction: bool = True) -> list[dict]:
    """[{text, confidence, box: [x, y, w, h] in pixels, top-left origin}] in reading order."""
    try:
        import objc
        import Vision
        from Foundation import NSData
    except ImportError as e:
        raise ImportError("Apple Vision OCR needs macOS + pyobjc-framework-Vision (see pyproject.toml)") from e

    h, w = rgb.shape[:2]
    ok, png = cv2.imencode(".png", cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2BGR))
    if not ok:
        raise ValueError("could not encode the frame as PNG")
    out = []
    with objc.autorelease_pool():
        data = NSData.dataWithBytes_length_(png.tobytes(), len(png))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate if accurate
                                 else Vision.VNRequestTextRecognitionLevelFast)
        req.setUsesLanguageCorrection_(language_correction)
        res = handler.performRequests_error_([req], None)
        success = res[0] if isinstance(res, tuple) else res
        if not success:
            raise RuntimeError(f"Vision text recognition failed: {res}")
        for obs in req.results() or []:
            cands = obs.topCandidates_(1)
            if not cands:
                continue
            c = cands[0]
            bb = obs.boundingBox()
            bx, by, bw, bh = bb.origin.x, bb.origin.y, bb.size.width, bb.size.height
            out.append({"text": str(c.string()), "confidence": round(float(c.confidence()), 3),
                        "box": [round(bx * w, 1), round((1 - by - bh) * h, 1), round(bw * w, 1), round(bh * h, 1)]})
    out.sort(key=lambda d: (d["box"][1], d["box"][0]))
    return out


def read_text(words: list[dict]) -> str | None:
    s = " ".join(w["text"] for w in words).strip().upper()
    return s or None


def stable_word(reads: list[str | None], min_reads: int = MIN_READS):
    """(index, text) of the first run of ``min_reads`` identical non-null reads, else None."""
    run_start, run_len = 0, 0
    for i, r in enumerate(reads):
        if r is not None and i > 0 and r == reads[i - 1] and run_len > 0:
            run_len += 1
        elif r is not None:
            run_start, run_len = i, 1
        else:
            run_len = 0
        if run_len >= min_reads:
            return run_start, reads[run_start]
    return None


def detect(frames, fps: float, *, box=None, every: int = EVERY, min_reads: int = MIN_READS) -> list[dict]:
    idx = list(range(0, len(frames), every))
    reads = []
    for i in idx:
        f = frames[i]
        if box is not None:
            x, y, bw, bh = box
            f = f[y:y + bh, x:x + bw]
        reads.append(read_text(ocr_words(f)))
    hit = stable_word(reads, min_reads)
    if hit is None:
        return []
    k, word = hit
    first = idx[k]
    return [make_event(t=first / fps, t_end=None, cue="note", what=f'a note reading "{word}" is set down',
                       source="detector:note",
                       evidence={"word": word, "first_frame": first, "every": every, "min_reads": min_reads,
                                 "reads": [[i, r] for i, r in zip(idx, reads)],
                                 "box": list(box) if box is not None else None})]
