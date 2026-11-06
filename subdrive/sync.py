"""Apply the timing adjustments made on the player (folder `sincronia/`) to a subtitle file.

The player keeps, for each subtitle file, points "at film time T, shift the subtitle by D ms".
Between points the shift changes gradually; before the first and after the last it stays constant.
Applying them writes a new .srt/.sup whose times already include the shift.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

from . import sup_reader

LIMIT = 600000          # +-10 minutes, as on the player
MAX_POINTS = 32
TIME = re.compile(r"(\d\d):([0-5]\d):([0-5]\d),(\d{3})")


class SyncError(ValueError):
    """code: bad_file, order"""
    def __init__(self, code, near=None):
        super().__init__(code); self.code, self.near = code, near


def sync_file_for(subtitle: Path):
    """Where the player saved the points for this subtitle: sincronia/<file name>.txt next to legendas/."""
    for folder in (subtitle.parent.parent / "sincronia", subtitle.parent / "sincronia", subtitle.parent):
        p = folder / (subtitle.name + ".txt")
        if p.is_file():
            return p
    return None


def parse(text: str):
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0] not in ("versao=1", "sincronia=1"):
        raise SyncError("bad_file")
    points = []
    for line in lines[1:]:
        if not line:
            continue
        m = re.fullmatch(r"ponto=(\d{1,8}),(-?\d{1,8})", line)
        if not m:
            raise SyncError("bad_file")
        at, off = int(m[1]), int(m[2])
        if at > 14400000 or abs(off) > LIMIT or (points and at <= points[-1][0]) or len(points) == MAX_POINTS:
            raise SyncError("bad_file")
        points.append((at, off))
    return points


def offset(points, ms):
    """Same rule as the player: interpolated between points, constant outside."""
    if not points:
        return 0
    if ms <= points[0][0]:
        return points[0][1]
    if ms >= points[-1][0]:
        return points[-1][1]
    for (a0, o0), (a1, o1) in zip(points, points[1:]):
        if ms <= a1:
            return int(o0 + (o1 - o0) * (ms - a0) / (a1 - a0))  # truncates toward zero, as Java
    return points[-1][1]


def film_time(points, subtitle_ms):
    """The player shows the subtitle of time T at film time F where F - offset(F) = T."""
    f = subtitle_ms + offset(points, subtitle_ms)
    for _ in range(20):
        g = subtitle_ms + offset(points, f)
        if g == f:
            break
        f = g
    return max(0, f)


def _fmt(ms):
    return "%02d:%02d:%02d,%03d" % (ms // 3600000, ms // 60000 % 60, ms // 1000 % 60, ms % 1000)


def apply_srt(data: bytes, points) -> bytes:
    text = data.decode("utf-8")

    def conv(m):
        h, mi, s, f = map(int, m.groups())
        return _fmt(film_time(points, ((h * 60 + mi) * 60 + s) * 1000 + f))
    out = TIME.sub(conv, text)
    ms = [((int(h) * 60 + int(mi)) * 60 + int(s)) * 1000 + int(f) for h, mi, s, f in TIME.findall(out)]
    for i in range(0, len(ms) - 1, 2):
        if ms[i + 1] <= ms[i] or (i and ms[i] < ms[i - 2]):
            raise SyncError("order", _fmt(ms[i])[:8])
    return out.encode("utf-8")


def apply_sup(data: bytes, points) -> bytes:
    out = bytearray(data); p = 0; last = -1
    while p < len(out):
        if out[p:p + 2] != b"PG" or p + 13 > len(out):
            raise SyncError("bad_subtitle")
        pts, dts = struct.unpack_from(">II", out, p + 2); size = struct.unpack_from(">H", out, p + 11)[0]
        new = film_time(points, pts // 90) * 90
        if new < last:
            raise SyncError("order", _fmt(new // 90)[:8])
        last = new
        struct.pack_into(">II", out, p + 2, new & 0xFFFFFFFF, 0 if dts == 0 else new & 0xFFFFFFFF)
        p += 13 + size
    data = bytes(out)
    sup_reader.parse(data)
    return data
