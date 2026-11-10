"""The note's invariant (R0.3): Apple Vision OCR and the character error rate.

VNRecognizeTextRequest at the accurate level (which reads handwriting), language correction
off (it would turn a misread into a dictionary word), on the note box every 3rd analysis frame.
Lines are sorted top to bottom, then left to right, and joined by a space.
CER = Levenshtein(take text, render text) / len(take text), both upper-cased with whitespace
collapsed; None when the take text is empty (nothing to keep).
"""
import io
import re

import numpy as np

EVERY = 3


def _cgimage_data(rgb):
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgb)).save(buf, format="PNG")
    return buf.getvalue()


def recognise(rgb, box=None):
    """Text in the image (or in box = (x0, y0, x1, y1)), or "" if none."""
    import Vision
    from Foundation import NSData
    img = np.asarray(rgb)
    if box is not None:
        x0, y0, x1, y1 = (int(v) for v in box)
        img = img[max(y0, 0):y1, max(x0, 0):x1]
    if img.size == 0:
        return ""
    data = _cgimage_data(img)
    ns = NSData.dataWithBytes_length_(data, len(data))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(ns, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    ok, err = handler.performRequests_error_([req], None)
    if not ok:
        raise RuntimeError(f"Vision OCR failed: {err}")
    items = []
    for obs in req.results() or []:
        cand = obs.topCandidates_(1)
        if not cand:
            continue
        bb = obs.boundingBox()                     # normalised, origin bottom-left
        items.append((-(bb.origin.y + bb.size.height), bb.origin.x, str(cand[0].string())))
    items.sort(key=lambda r: (round(r[0], 3), r[1]))
    return " ".join(s for _, _, s in items)


def normalise(s):
    return re.sub(r"\s+", " ", s or "").strip().upper()


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref, hyp):
    r, h = normalise(ref), normalise(hyp)
    if not r:
        return None
    return levenshtein(r, h) / len(r)


def cer_series(take, render, boxes, valid, every=EVERY):
    out = []
    for i, (tf, rf, box, ok) in enumerate(zip(take, render, boxes, valid)):
        if not ok or i % every or box is None:
            out.append(None)
            continue
        out.append(cer(recognise(tf, box), recognise(rf, box)))
    return out
