"""SRT -> PGS (.sup) for the player: 1920x1080, one image per subtitle line, drawn on the computer.

The look is fixed in the file: font, size, colour and outline. Letters are drawn 4x larger and
reduced (smooth edges). The palette has 15 alpha levels x 16 fill/outline blends, as the player's
PGS reader expects (straight alpha, BT.709 limited range).
"""
from __future__ import annotations

import os
import struct
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

from . import sup_reader
from .regras.codificacao import decodificar
from .regras.modelo import interpretar_flexivel

FONT_DIR = Path(__file__).resolve().parent / "fonts"
# name shown, file prefix
FONTS = [("Roboto", "roboto"), ("Inter", "inter"), ("Arimo", "arimo"), ("Noto Sans", "notosans"),
         ("Open Sans", "opensans"), ("Source Sans", "sourcesans3"), ("Lato", "lato"),
         ("Atkinson Hyperlegible", "atkinson"), ("DejaVu Sans", "dejavusans")]
# The player's 20 colours: English name (file suffix), Portuguese name, RGB.
COLORS = [("white", "branco", 0xFFFFFF), ("soft-white", "branco-suave", 0xE0E0E0), ("light-gray", "cinza-claro", 0xC8C8C8),
          ("gray", "cinza", 0x9A9A9A), ("cream", "creme", 0xF3E5C4), ("yellow", "amarelo", 0xFFFF00),
          ("light-yellow", "amarelo-claro", 0xFFF59D), ("dark-yellow", "amarelo-escuro", 0xD7C246), ("amber", "ambar", 0xFFBF00),
          ("orange", "laranja", 0xFF9A3C), ("green", "verde", 0x00FF00), ("light-green", "verde-claro", 0xA5F2A0),
          ("lime", "verde-limao", 0xC8FF50), ("cyan", "ciano", 0x00FFFF), ("light-cyan", "ciano-claro", 0xA8FFFF),
          ("light-blue", "azul-claro", 0x8EC5FF), ("lilac", "lilas", 0xD7B4FF), ("pink", "rosa", 0xFFAFD7),
          ("magenta", "magenta", 0xFF50FF), ("light-red", "vermelho-claro", 0xFF8C8C)]
SIZES = (30, 72)   # allowed size range, px at 1080p
OUTLINES = (0, 6)  # allowed outline range, px
BOTTOM, GAP, SS = 64, 4, 4


def color(name: str):
    """English or Portuguese name (any case, accents ignored) -> (english name, (r, g, b)) or None."""
    import unicodedata
    key = "".join(c for c in unicodedata.normalize("NFKD", name.strip().lower()) if not unicodedata.combining(c))
    key = key.replace(" ", "-")
    for en, pt, rgb in COLORS:
        if key in (en, pt):
            return en, ((rgb >> 16) & 255, (rgb >> 8) & 255, rgb & 255)
    return None


def font(name: str):
    key = name.strip().lower().replace(" ", "")
    for shown, prefix in FONTS:
        if key in (shown.lower().replace(" ", ""), prefix):
            return shown, prefix
    return None


@dataclass
class Style:
    font: str = "roboto"
    bold: bool = False
    size: int = 48
    outline: float = 2
    fill: tuple = (0xE0, 0xE0, 0xE0)
    stroke: tuple = (0, 0, 0)

    def files(self):
        w = "700" if self.bold else "400"
        return FONT_DIR / ("%s-%s.ttf" % (self.font, w)), FONT_DIR / ("%s-italic-%s.ttf" % (self.font, w))


class Renderer:
    def __init__(self, style: Style):
        regular, italic = style.files()
        engine = ImageFont.Layout.BASIC  # same spacing on every computer
        self.font = ImageFont.truetype(str(regular), style.size * SS, layout_engine=engine)
        self.italic = ImageFont.truetype(str(italic), style.size * SS, layout_engine=engine)
        self.cmaps = {False: set(TTFont(str(regular)).getBestCmap()), True: set(TTFont(str(italic)).getBestCmap())}
        self.style = style

    def line(self, runs):
        """One line ([(text, italic)]) -> tightly cropped RGBA image at 1080p."""
        s, n = self.style, SS
        ascent, descent = self.font.getmetrics()
        pad = (int(s.outline + 0.999) + 4 + s.size // 4) * n
        width = sum(int((self.italic if i else self.font).getlength(t)) + 1 for t, i in runs) + 2 * pad
        height = ascent + descent + 2 * pad
        width += -width % n; height += -height % n
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0)); x = pad
        for text, italic in runs:
            f = self.italic if italic else self.font
            ImageDraw.Draw(canvas).text((x, pad), text, font=f, fill=s.fill + (255,),
                                        stroke_width=round(s.outline * n), stroke_fill=s.stroke + (255,))
            x += int(f.getlength(text)) + 1
        canvas = canvas.convert("RGBa").resize((width // n, height // n), Image.BOX).convert("RGBA")
        box = canvas.getchannel("A").getbbox()
        return canvas.crop(box) if box else None


def quantize(images, fill, stroke):
    """Each pixel -> (fill/outline blend, 16 levels) x (alpha, 15 levels), index 0 = transparent."""
    fr, fg, fb = fill; sr, sg, sb = stroke
    dr, dg, db = fr - sr, fg - sg, fb - sb; den = dr * dr + dg * dg + db * db
    palette = [(0, 0, 0, 0)] * 241
    for al in range(1, 16):
        for tl in range(16):
            t = tl / 15
            palette[1 + (al - 1) * 16 + tl] = (round(sr + t * dr), round(sg + t * dg), round(sb + t * db), al * 17)
    out = []
    for im in images:
        w, h = im.size; idx = bytearray(w * h)
        for k, (r, g, b, a) in enumerate(im.getdata()):
            al = (a * 2 + 17) // 34
            if al == 0:
                continue
            t = 1.0 if den == 0 else ((r - sr) * dr + (g - sg) * dg + (b - sb) * db) / den
            idx[k] = 1 + (al - 1) * 16 + min(15, max(0, round(t * 15)))
        out.append((w, h, bytes(idx)))
    return palette, out


def rgb_to_ycbcr(r, g, b):
    y = 16 + 0.1826 * r + 0.6142 * g + 0.0620 * b
    cb = 128 - 0.1006 * r - 0.3386 * g + 0.4392 * b
    cr = 128 + 0.4392 * r - 0.3989 * g - 0.0403 * b
    c = lambda v: max(16, min(240, round(v)))
    return max(16, min(235, round(y))), c(cr), c(cb)


def rle(w, h, idx):
    out = bytearray()
    for y in range(h):
        row = idx[y * w:(y + 1) * w]; x = 0
        while x < w:
            c = row[x]; n = 1
            while x + n < w and row[x + n] == c and n < 16383:
                n += 1
            if c and n <= 2:
                out += bytes([c]) * n
            elif c == 0:
                out += bytes([0, n]) if n < 64 else bytes([0, 0x40 | (n >> 8), n & 255])
            else:
                out += bytes([0, 0x80 | n, c]) if n < 64 else bytes([0, 0xC0 | (n >> 8), n & 255, c])
            x += n
        out += b"\x00\x00"
    return bytes(out)


def _segment(kind, pts, payload):
    if len(payload) > 65535:
        raise ValueError("segment too large")
    return b"PG" + struct.pack(">IIBH", pts & 0xFFFFFFFF, 0, kind, len(payload)) + payload


class TooLarge(ValueError):
    """A subtitle does not fit the player's image limits at this size."""
    def __init__(self, start_ms):
        super().__init__(start_ms); self.start_ms = start_ms


_RENDERER = None


def _worker_init(style):
    global _RENDERER
    _RENDERER = Renderer(style)


def _render_cue(args):
    """Worker: one subtitle -> (palette, objects) ready to be written."""
    start, lines = args
    images = [im for im in (_RENDERER.line(runs) for runs in lines) if im is not None]
    palette, objects = quantize(images, _RENDERER.style.fill, _RENDERER.style.stroke)
    return start, palette, [(w, h, rle(w, h, idx)) for w, h, idx in objects]


def cues_from_srt(data: bytes):
    """A file that passed the check -> [(start, end, [[(text, italic)], ...])]."""
    text, _ = decodificar(data, None)
    cues = []
    for e in interpretar_flexivel(text).entradas:
        # U+00AD (soft hyphen) is invisible and some fonts lack it.
        lines = [[(t.texto.replace("\u00ad", ""), t.italico) for t in line if t.texto.replace("\u00ad", "")] for line in e.linhas]
        cues.append((e.inicio, e.fim, [l for l in lines if l]))
    return cues


def missing_letters(cues, style: Style):
    r = Renderer(style); missing = set()
    for _, _, lines in cues:
        for runs in lines:
            for text, italic in runs:
                missing |= {c for c in text if not c.isspace() and ord(c) not in r.cmaps[italic]}
    return sorted(missing)


def convert(cues, style: Style, progress=None, workers=None) -> bytes:
    """Render every subtitle (in parallel) and write the .sup stream."""
    workers = workers or max(1, min(8, (os.cpu_count() or 2)))
    jobs = [(start, lines) for start, _, lines in cues]
    results = []
    if workers == 1:
        _worker_init(style)
        for k, job in enumerate(jobs, 1):
            results.append(_render_cue(job))
            if progress:
                progress(k, len(jobs))
    else:
        with ProcessPoolExecutor(workers, initializer=_worker_init, initargs=(style,)) as pool:
            for k, res in enumerate(pool.map(_render_cue, jobs, chunksize=8), 1):
                results.append(res)
                if progress:
                    progress(k, len(jobs))
    out = bytearray(); number = 0; previous_windows = None; previous_end = None
    for (start, end, _), (_, palette, objects) in zip(cues, results):
        positions = []; y = 1080 - BOTTOM
        for w, h, _ in reversed(objects):
            y -= h; positions.append(((1920 - w) // 2, y)); y -= GAP
        positions.reverse()
        for (w, h, _), (x, y) in zip(objects, positions):
            if w * h > 262144 or w > 1536 or y < 540:
                raise TooLarge(start)
        left = min(x for x, _ in positions); right = max(x + o[0] for o, (x, _) in zip(objects, positions))
        if (right - left) * (positions[-1][1] + objects[-1][1] - positions[0][1]) > 262144:
            raise TooLarge(start)
        pts = start * 90
        if previous_end is not None and previous_end < start:
            out += _clear(previous_end * 90, number, previous_windows); number += 1
        windows = [(i, x, y, w, h) for i, ((w, h, _), (x, y)) in enumerate(zip(objects, positions))]
        pcs = struct.pack(">HHBHBBBB", 1920, 1080, 0x10, number & 0xFFFF, 0x80, 0, 0, len(objects))
        for i, (x, y) in enumerate(positions):
            pcs += struct.pack(">HBBHH", i, i, 0, x, y)
        out += _segment(0x16, pts, pcs)
        out += _segment(0x17, pts, bytes([len(windows)]) + b"".join(struct.pack(">BHHHH", *wd) for wd in windows))
        out += _segment(0x14, pts, bytes([0, 0]) + b"".join(bytes([i, *rgb_to_ycbcr(*palette[i][:3]), palette[i][3]])
                                                           for i in range(1, len(palette))))
        for i, (w, h, data) in enumerate(objects):
            chunks = []; pos = 0; limit = 65535 - 11
            while True:
                chunk = data[pos:pos + limit]; chunks.append(chunk); pos += len(chunk); limit = 65535 - 4
                if pos >= len(data):
                    break
            for k, chunk in enumerate(chunks):
                flag = (0x80 if k == 0 else 0) | (0x40 if k == len(chunks) - 1 else 0)
                body = struct.pack(">HBB", i, 0, flag)
                if k == 0:
                    body += (len(data) + 4).to_bytes(3, "big") + struct.pack(">HH", w, h)
                out += _segment(0x15, pts, body + chunk)
        out += _segment(0x80, pts, b"")
        number += 1; previous_windows = windows; previous_end = end
    out += _clear(previous_end * 90, number, previous_windows)
    data = bytes(out)
    if len(data) > sup_reader.LIMIT:
        raise ValueError("over 64 MB")
    sup_reader.parse(data)  # the same strict reading as the player
    return data


def _clear(pts, number, windows):
    pcs = struct.pack(">HHBHBBBB", 1920, 1080, 0x10, number & 0xFFFF, 0x00, 0, 0, 0)
    return (_segment(0x16, pts, pcs)
            + _segment(0x17, pts, bytes([len(windows)]) + b"".join(struct.pack(">BHHHH", *wd) for wd in windows))
            + _segment(0x80, pts, b""))
