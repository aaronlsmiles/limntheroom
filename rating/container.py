"""Does an MP4 carry provenance or metadata? Used on every rating copy (rating/prepare.py)."""
from __future__ import annotations

import struct
from pathlib import Path

C2PA_UUID = bytes.fromhex("d8fec3d61b0e483c92975828877ec481")
BOX_CONTAINERS = {b"moov", b"trak", b"mdia", b"minf", b"stbl", b"edts", b"dinf"}
FORBIDDEN_BOXES = {b"uuid", b"jumb", b"jumd", b"c2pa", b"cbor", b"XMP_", b"xml ", b"bxml"}
LONG_MARKERS = [C2PA_UUID, b"urn:c2pa", b"c2pa.", b"contentauth", b"jumbf", b"Content Credentials",
                b"<?xpacket", b"http://ns.adobe.com"]


def _boxes(data: bytes, start: int, end: int, path=()):
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        hdr = 8
        if size == 1:
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            hdr = 16
        elif size == 0:
            size = end - pos
        if size < hdr or pos + size > end:
            yield path, kind, pos, pos + size, True      # malformed: reported by the caller
            return
        yield path, kind, pos, pos + size, False
        if kind in BOX_CONTAINERS:
            yield from _boxes(data, pos + hdr, pos + size, path + (kind,))
        pos += size


def scan_container(path, banned=()) -> list[str]:
    """Problems found in an MP4's structure and header bytes (empty list = clean).

    The media data (`mdat`) is searched only for the long unambiguous provenance markers: short
    byte strings turn up by chance in compressed video."""
    data = Path(path).read_bytes()
    problems = []
    mdat = []
    for pth, kind, s, e, bad in _boxes(data, 0, len(data)):
        name = kind.decode("latin1")
        if bad:
            problems.append(f"malformed box {name!r} at byte {s}")
            continue
        if kind == b"mdat":
            mdat.append((s, e))
        if kind in FORBIDDEN_BOXES:
            problems.append(f"{name!r} box at byte {s} (provenance or metadata)")
        if kind == b"meta" and not pth:
            problems.append(f"top-level 'meta' box at byte {s}")
        if kind == b"udta":
            # ffmpeg leaves an empty meta/hdlr/ilst scaffold; anything else is metadata
            inner = [(k, ee - ss) for _p, k, ss, ee, _b in _boxes(data, s + 8, e) if not _b]
            if inner != [(b"meta", e - s - 8)]:
                problems.append("'udta' box holds more than the empty scaffold")
            else:
                kids = [(k, ee - ss) for _p, k, ss, ee, _b in _boxes(data, s + 8 + 8 + 4, e) if not _b]
                if [k for k, _ in kids] != [b"hdlr", b"ilst"] or dict(kids)[b"ilst"] != 8:
                    problems.append("'udta' box holds metadata items")
    outside = bytearray(data)
    for s, e in mdat:
        outside[s:e] = b"\0" * (e - s)
    header = bytes(outside)
    lower = header.lower()
    for m in LONG_MARKERS:
        if m.lower() in lower:
            problems.append(f"marker {m[:12]!r} in the header bytes")
        if any(m.lower() in data[s:e].lower() for s, e in mdat):
            problems.append(f"marker {m[:12]!r} in the media data")
    text = header.decode("latin1")
    for term in banned:
        if isinstance(term, str):
            if term.lower() in text.lower():
                problems.append("a banned term in the header bytes")
        elif term.search(text):
            problems.append("a banned pattern in the header bytes")
    return sorted(set(problems))
