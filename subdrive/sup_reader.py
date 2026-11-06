"""Independent host reader for the strict PGS2 .sup subset (mirrors the Java helper rules).

Used to validate packages and tests on the computer. It never touches USB or the player.
"""
from pathlib import Path
import argparse, json, struct, sys

LIMIT = 67108864


class SupError(ValueError):
    pass


def ycbcr_to_argb(y, cr, cb, a):
    """BT.709 limited range, integer maths identical to the Java helper."""
    if a == 0:
        return 0
    c, d, e = y - 16, cb - 128, cr - 128
    def div(n):  # Java integer division truncates toward zero
        q = abs(n) // 1000
        return q if n >= 0 else -q
    clamp = lambda v: 0 if v < 0 else 255 if v > 255 else v
    r = clamp(div(1164 * c + 1793 * e + 500))
    g = clamp(div(1164 * c - 213 * d - 533 * e + 500))
    b = clamp(div(1164 * c + 2112 * d + 500))
    return (a << 24) | (r << 16) | (g << 8) | b


def decode_rle(data, w, h, palette=None):
    out = [0] * (w * h) if palette is not None else None
    p = x = y = 0
    n = len(data)
    while y < h:
        if p >= n:
            raise SupError('PGS_RLE_SHORT')
        b = data[p]; p += 1
        if b:
            count, color = 1, b
        else:
            if p >= n:
                raise SupError('PGS_RLE_SHORT')
            f = data[p]; p += 1
            if f == 0:
                x = 0; y += 1; continue
            count = f & 63
            if f & 64:
                if p >= n:
                    raise SupError('PGS_RLE_SHORT')
                count = (count << 8) | data[p]; p += 1
            if f & 128:
                if p >= n:
                    raise SupError('PGS_RLE_SHORT')
                color = data[p]; p += 1
            else:
                color = 0
            if count == 0:
                raise SupError('PGS_RLE_ZERO')
        if x + count > w:
            raise SupError('PGS_RLE_WIDTH')
        if out is not None:
            argb = palette[color]
            out[y * w + x:y * w + x + count] = [argb] * count
        x += count
    if p != n:
        raise SupError('PGS_RLE_TRAILING')
    return out


def parse(data):
    """Return cues: dicts with start/end ms and objects (x, y, w, h, rle, palette)."""
    if not 13 <= len(data) <= LIMIT:
        raise SupError('SUP_SIZE')
    cues = []
    palettes = [None] * 8; objects = [None] * 64; sizes = [(0, 0)] * 64
    assembly = None; assembly_id = -1
    composition = None
    open_cue = None; previous_end = 0; p = 0
    while p < len(data):
        if p + 13 > len(data) or data[p:p + 2] != b'PG':
            raise SupError('PGS_MAGIC')
        pts = struct.unpack_from('>I', data, p + 2)[0]
        kind = data[p + 10]; size = struct.unpack_from('>H', data, p + 11)[0]; q = p + 13
        if q + size > len(data):
            raise SupError('PGS_TRUNCATED')
        seg = data[q:q + size]
        if kind == 0x16:
            if composition is not None or size < 11:
                raise SupError('PGS_COMPOSITION')
            vw, vh = struct.unpack_from('>HH', seg, 0)
            if (vw, vh) != (1920, 1080):
                raise SupError('PGS_VIDEO_SIZE')
            state, update, pal, count = seg[7], seg[8], seg[9], seg[10]
            if update:
                raise SupError('PGS_PALETTE_UPDATE')
            if pal > 7 or count > 2 or size != 11 + count * 8:
                raise SupError('PGS_COMPOSITION')
            if state == 0x80:
                palettes = [None] * 8; objects = [None] * 64
            refs = []
            for i in range(count):
                at = 11 + i * 8
                oid = struct.unpack_from('>H', seg, at)[0]
                if oid > 63 or seg[at + 3] & 0x80:
                    raise SupError('PGS_OBJECT_REFERENCE')
                refs.append((oid,) + struct.unpack_from('>HH', seg, at + 4))
            composition = (pts, pal, refs)
        elif kind == 0x17:
            if composition is None or size < 1 or size != 1 + seg[0] * 9:
                raise SupError('PGS_WINDOW')
        elif kind == 0x14:
            if composition is None or size < 2 or (size - 2) % 5:
                raise SupError('PGS_PALETTE')
            pid = seg[0]
            # PGS2 subset: one complete palette per id and epoch (no partial merges).
            if pid > 7 or palettes[pid] is not None:
                raise SupError('PGS_PALETTE')
            palette = [0] * 256
            for e in range(2, size, 5):
                palette[seg[e]] = ycbcr_to_argb(seg[e + 1], seg[e + 2], seg[e + 3], seg[e + 4])
            palette[0] = 0
            palettes[pid] = palette
        elif kind == 0x15:
            if composition is None or size < 4:
                raise SupError('PGS_OBJECT')
            oid = struct.unpack_from('>H', seg, 0)[0]; flags = seg[3]
            if oid > 63:
                raise SupError('PGS_OBJECT')
            body = seg[4:]
            if flags & 0x80:
                if assembly is not None or size < 11:
                    raise SupError('PGS_OBJECT_SEQUENCE')
                total = int.from_bytes(seg[4:7], 'big'); ow, oh = struct.unpack_from('>HH', seg, 7)
                if not (1 <= ow <= 1920 and 1 <= oh <= 1080 and ow * oh <= 262144 and 5 <= total and total - 4 <= 1048576):
                    raise SupError('PGS_OBJECT_SIZE')
                assembly = bytearray(); assembly_total = total - 4; assembly_id = oid; sizes[oid] = (ow, oh)
                body = seg[11:]
            elif assembly is None or assembly_id != oid:
                raise SupError('PGS_OBJECT_SEQUENCE')
            if len(assembly) + len(body) > assembly_total:
                raise SupError('PGS_OBJECT_LENGTH')
            assembly += body
            if flags & 0x40:
                if len(assembly) != assembly_total:
                    raise SupError('PGS_OBJECT_LENGTH')
                decode_rle(bytes(assembly), *sizes[oid])
                objects[oid] = bytes(assembly); assembly = None; assembly_id = -1
        elif kind == 0x80:
            if composition is None or size != 0 or assembly is not None:
                raise SupError('PGS_END')
            cpts, pal, refs = composition
            ms = cpts // 90
            if open_cue is not None:
                if ms <= open_cue['start'] or ms - open_cue['start'] > 60000:
                    raise SupError('PGS_RANGE')
                open_cue['end'] = ms; cues.append(open_cue); previous_end = ms; open_cue = None
            if refs:
                if ms < previous_end or ms > 14400000 or len(cues) >= 3000:
                    raise SupError('PGS_RANGE')
                if palettes[pal] is None:
                    raise SupError('PGS_PALETTE_MISSING')
                objs = []
                for oid, x, y in refs:
                    if objects[oid] is None:
                        raise SupError('PGS_OBJECT_MISSING')
                    w, h = sizes[oid]
                    if x + w > 1920 or y + h > 1080:
                        raise SupError('PGS_OBJECT_OUTSIDE')
                    objs.append({'x': x, 'y': y, 'w': w, 'h': h, 'rle': objects[oid]})
                open_cue = {'start': ms, 'objects': objs, 'palette': palettes[pal]}
                box_w = max(o['x'] + o['w'] for o in objs) - min(o['x'] for o in objs)
                box_h = max(o['y'] + o['h'] for o in objs) - min(o['y'] for o in objs)
                if box_w * box_h > 262144:
                    raise SupError('PGS_IMAGE_TOO_LARGE')
            composition = None
        else:
            raise SupError('PGS_SEGMENT_TYPE')
        p = q + size
    if open_cue is not None or composition is not None or assembly is not None:
        raise SupError('PGS_UNTERMINATED')
    if not cues:
        raise SupError('PGS_EMPTY')
    return cues


def summary(path):
    data = Path(path).read_bytes(); cues = parse(data)
    boxes = [(min(o['x'] for o in c['objects']), min(o['y'] for o in c['objects']),
              max(o['x'] + o['w'] for o in c['objects']), max(o['y'] + o['h'] for o in c['objects'])) for c in cues]
    return {'bytes': len(data), 'cues': len(cues), 'first_ms': cues[0]['start'], 'last_end_ms': cues[-1]['end'],
            'max_objects': max(len(c['objects']) for c in cues),
            'max_object_pixels': max(o['w'] * o['h'] for c in cues for o in c['objects']),
            'min_top': min(b[1] for b in boxes), 'max_bottom': max(b[3] for b in boxes)}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('sup', nargs='+')
    a = ap.parse_args(); ok = True
    for f in a.sup:
        try:
            print(f, json.dumps(summary(f)))
        except SupError as e:
            ok = False; print(f, 'RECUSADO', e)
    sys.exit(0 if ok else 1)
