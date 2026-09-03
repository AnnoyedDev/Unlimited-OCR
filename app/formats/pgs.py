import struct

import numpy as np

from .image_set import ImageEvent, ImageSetReader

_PTS_CLOCK = 90_000.0

_SEG_PDS = 0x14
_SEG_ODS = 0x15
_SEG_PCS = 0x16
_SEG_END = 0x80

_HEADER_SIZE = 13

_MAX_BITMAP_DIM = 4320


class _Segment:
    def __init__(self, kind, pts, data):
        self.kind = kind
        self.pts = pts
        self.data = data


class _CompositionObject:
    def __init__(self, object_id, x, y):
        self.object_id = object_id
        self.x = x
        self.y = y


class _ObjectAccumulator:
    def __init__(self, width=0, height=0, data=None):
        self.width = width
        self.height = height
        self.data = data if data is not None else bytearray()


def _iter_segments(data):
    offset = 0
    n = len(data)
    while offset + _HEADER_SIZE <= n:
        if data[offset:offset + 2] != b"PG":
            next_magic = data.find(b"PG", offset + 1)
            if next_magic == -1:
                return
            offset = next_magic
            continue
        pts_ticks, _dts_ticks, kind, size = struct.unpack_from(">IIBH", data, offset + 2)
        seg_start = offset + _HEADER_SIZE
        seg_end = seg_start + size
        if seg_end > n:
            return
        yield _Segment(kind=kind, pts=pts_ticks / _PTS_CLOCK, data=data[seg_start:seg_end])
        offset = seg_end


def _parse_pcs(data):
    if len(data) < 11:
        return []
    num_objects = data[10]
    objects = []
    offset = 11
    for _ in range(num_objects):
        if offset + 8 > len(data):
            break
        object_id, _window_id, flags, x, y = struct.unpack_from(">HBBHH", data, offset)
        offset += 8
        if flags & 0x40:
            offset += 8
        objects.append(_CompositionObject(object_id, x, y))
    return objects


def _parse_pds(data):
    if len(data) < 2:
        return 0, {}
    palette_id = data[0]
    entries = {}
    offset = 2
    while offset + 5 <= len(data):
        entry_id, y, cr, cb, alpha = data[offset:offset + 5]
        entries[entry_id] = (y, cr, cb, alpha)
        offset += 5
    return palette_id, entries


def _parse_ods_fragment(data):
    object_id, _version, flags = struct.unpack_from(">HBB", data, 0)
    is_first = bool(flags & 0x40)
    is_last = bool(flags & 0x80)
    offset = 4
    width = height = None
    if is_first and offset + 7 <= len(data):
        offset += 3
        width, height = struct.unpack_from(">HH", data, offset)
        offset += 4
    return object_id, is_first, is_last, width, height, data[offset:]


def _decode_rle(rle, width, height):
    indices = np.zeros((height, width), dtype=np.uint8)
    row = col = 0
    i, n = 0, len(rle)
    while i < n and row < height:
        b0 = rle[i]
        i += 1
        if b0 != 0:
            if col < width:
                indices[row, col] = b0
            col += 1
            continue
        if i >= n:
            break
        b1 = rle[i]
        i += 1
        if b1 == 0:
            row += 1
            col = 0
            continue
        flag = b1 & 0xC0
        count = b1 & 0x3F
        if flag & 0x40:
            if i >= n:
                break
            count = (count << 8) | rle[i]
            i += 1
        if flag & 0x80:
            if i >= n:
                break
            color = rle[i]
            i += 1
        else:
            color = 0
        end_col = min(width, col + count)
        if end_col > col:
            indices[row, col:end_col] = color
        col = col + count
    return indices


def _ycbcr_to_rgb(y, cb, cr):
    cr_, cb_ = cr - 128, cb - 128
    r = y + 1.402 * cr_
    g = y - 0.344136 * cb_ - 0.714136 * cr_
    b = y + 1.772 * cb_
    return (
        max(0, min(255, round(r))),
        max(0, min(255, round(g))),
        max(0, min(255, round(b))),
    )


def _palette_to_lut(palette):
    lut_bgr = np.zeros((256, 3), dtype=np.uint8)
    lut_alpha = np.zeros(256, dtype=np.uint8)
    for entry_id, (y, cr, cb, alpha) in palette.items():
        if 0 <= entry_id < 256:
            r, g, b = _ycbcr_to_rgb(y, cb, cr)
            lut_bgr[entry_id] = (b, g, r)
            lut_alpha[entry_id] = alpha
    return lut_bgr, lut_alpha


def _composite(objects, bitmaps, palette):
    placed = []
    for obj in objects:
        bitmap = bitmaps.get(obj.object_id)
        if bitmap is None:
            continue
        w, h, indices = bitmap
        if w <= 0 or h <= 0:
            continue
        placed.append((obj.x, obj.y, w, h, indices))
    if not placed:
        return None

    min_x = min(p[0] for p in placed)
    min_y = min(p[1] for p in placed)
    max_x = max(p[0] + p[2] for p in placed)
    max_y = max(p[1] + p[3] for p in placed)
    if max_x - min_x > _MAX_BITMAP_DIM or max_y - min_y > _MAX_BITMAP_DIM:
        return None
    canvas = np.zeros((max_y - min_y, max_x - min_x, 3), dtype=np.float32)

    lut_bgr, lut_alpha = _palette_to_lut(palette)
    for x, y, w, h, indices in placed:
        bgr = lut_bgr[indices].astype(np.float32)
        alpha = (lut_alpha[indices].astype(np.float32) / 255.0)[..., None]
        ox, oy = x - min_x, y - min_y
        region = canvas[oy:oy + h, ox:ox + w]
        canvas[oy:oy + h, ox:ox + w] = bgr * alpha + region * (1 - alpha)

    return np.clip(canvas, 0, 255).astype(np.uint8)


def parse_pgs(path):
    with open(path, "rb") as f:
        data = f.read()
    if not data:
        raise IOError(f"Empty PGS file: {path}")

    palettes = {}
    fragments = {}
    bitmaps = {}
    current_pcs = None
    raw_entries = []

    for seg in _iter_segments(data):
        if seg.kind == _SEG_PDS:
            palette_id, entries = _parse_pds(seg.data)
            palettes.setdefault(palette_id, {}).update(entries)
        elif seg.kind == _SEG_ODS:
            object_id, is_first, is_last, width, height, chunk = _parse_ods_fragment(seg.data)
            if is_first:
                width, height = width or 0, height or 0
                if width > _MAX_BITMAP_DIM or height > _MAX_BITMAP_DIM:
                    fragments.pop(object_id, None)
                    continue
                fragments[object_id] = _ObjectAccumulator(width, height)
            acc = fragments.get(object_id)
            if acc is not None:
                acc.data.extend(chunk)
                if is_last:
                    fragments.pop(object_id, None)
                    if acc.width and acc.height:
                        bitmaps[object_id] = (acc.width, acc.height, _decode_rle(bytes(acc.data), acc.width, acc.height))
        elif seg.kind == _SEG_PCS:
            objects = _parse_pcs(seg.data)
            palette_id = seg.data[9] if len(seg.data) > 9 else 0
            current_pcs = (palette_id, objects)
            current_pts = seg.pts
        elif seg.kind == _SEG_END:
            if current_pcs is not None:
                palette_id, objects = current_pcs
                image = _composite(objects, bitmaps, palettes.get(palette_id, {})) if objects else None
                raw_entries.append((current_pts, image))
                current_pcs = None

    events = []
    idx = 0
    for i, (pts, image) in enumerate(raw_entries):
        if image is None:
            continue
        end = raw_entries[i + 1][0] if i + 1 < len(raw_entries) else pts + 4.0
        events.append(ImageEvent(index=idx, start=pts, end=max(end, pts + 0.01), image=image))
        idx += 1
    return events


def load_pgs(path):
    return ImageSetReader(path, parse_pgs(path))
