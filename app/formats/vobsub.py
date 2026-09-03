import os
import re
import struct

import numpy as np

from .image_set import ImageEvent, ImageSetReader

_SIZE_RE = re.compile(r"^size:\s*(\d+)x(\d+)", re.IGNORECASE)
_PALETTE_RE = re.compile(r"^palette:\s*(.+)", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(
    r"timestamp:\s*(\d+):(\d+):(\d+):(\d+)\s*,\s*filepos:\s*([0-9A-Fa-f]+)", re.IGNORECASE
)


def parse_idx(path):
    width = height = 0
    palette = [(0, 0, 0)] * 16
    entries = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = _SIZE_RE.match(line)
            if m:
                width, height = int(m.group(1)), int(m.group(2))
                continue
            m = _PALETTE_RE.match(line)
            if m:
                colors = []
                for c in m.group(1).split(","):
                    c = c.strip()
                    if len(c) == 6:
                        colors.append((int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)))
                if colors:
                    palette = colors
                continue
            m = _TIMESTAMP_RE.search(line)
            if m:
                h, mi, s, ms, filepos = m.groups()
                start = int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000.0
                entries.append((start, int(filepos, 16)))
    return width, height, palette, entries


def _infer_sub_path(idx_path):
    base, _ext = os.path.splitext(idx_path)
    for ext in (".sub", ".SUB"):
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return base + ".sub"


def _read_pack_header(buf, offset):
    if buf[offset:offset + 4] != b"\x00\x00\x01\xba":
        return None
    offset += 4
    if offset + 10 > len(buf):
        return None
    stuffing_length = buf[offset + 9] & 0x07
    offset += 10 + stuffing_length
    if buf[offset:offset + 4] == b"\x00\x00\x01\xbb":
        if offset + 6 > len(buf):
            return None
        header_length = struct.unpack_from(">H", buf, offset + 4)[0]
        offset += 6 + header_length
    return offset


def _read_pes_private1(buf, offset):
    if buf[offset:offset + 3] != b"\x00\x00\x01" or offset + 4 >= len(buf) or buf[offset + 3] != 0xBD:
        return None, offset
    pes_length = struct.unpack_from(">H", buf, offset + 4)[0]
    pes_start = offset + 6
    if pes_start + 3 > len(buf):
        return None, offset
    header_data_length = buf[pes_start + 2]
    payload_start = pes_start + 3 + header_data_length
    payload_end = pes_start + pes_length
    if payload_end > len(buf) or payload_start >= payload_end:
        return None, offset
    return buf[payload_start + 1:payload_end], payload_end


def _extract_spu_packet(buf, start_offset):
    offset = start_offset
    payload = bytearray()
    total_size = None
    while offset < len(buf):
        pack_end = _read_pack_header(buf, offset)
        if pack_end is not None:
            offset = pack_end
            continue
        chunk, next_offset = _read_pes_private1(buf, offset)
        if chunk is None:
            break
        payload.extend(chunk)
        offset = next_offset
        if total_size is None and len(payload) >= 2:
            total_size = struct.unpack_from(">H", payload, 0)[0]
        if total_size is not None and len(payload) >= total_size:
            return bytes(payload[:total_size])
    return bytes(payload)


class _NibbleReader:
    def __init__(self, data, byte_offset):
        self.data = data
        self.pos = byte_offset * 2

    def read_nibble(self):
        byte_index = self.pos // 2
        if byte_index >= len(self.data):
            self.pos += 1
            return 0
        byte = self.data[byte_index]
        nibble = (byte >> 4) if self.pos % 2 == 0 else (byte & 0x0F)
        self.pos += 1
        return nibble

    def align_to_byte(self):
        if self.pos % 2 != 0:
            self.pos += 1


def _read_run(reader):
    code = reader.read_nibble()
    if code >= 0x4:
        return code >> 2, code & 0x3
    code = (code << 4) | reader.read_nibble()
    if code >= 0x10:
        return code >> 2, code & 0x3
    code = (code << 4) | reader.read_nibble()
    if code >= 0x40:
        return code >> 2, code & 0x3
    code = (code << 4) | reader.read_nibble()
    return code >> 2, code & 0x3


def _decode_field(data, offset, width, num_lines):
    reader = _NibbleReader(data, offset)
    field = np.zeros((max(0, num_lines), width), dtype=np.uint8)
    for line in range(num_lines):
        x = 0
        while x < width:
            length, color = _read_run(reader)
            if length == 0:
                field[line, x:width] = color
                break
            end = min(width, x + length)
            field[line, x:end] = color
            x = end
        reader.align_to_byte()
    return field


def _decode_bitmap(data, even_offset, odd_offset, width, height):
    num_even = (height + 1) // 2
    num_odd = height // 2
    even = _decode_field(data, even_offset, width, num_even)
    odd = _decode_field(data, odd_offset, width, num_odd)
    indices = np.zeros((height, width), dtype=np.uint8)
    indices[0::2] = even[: len(indices[0::2])]
    indices[1::2] = odd[: len(indices[1::2])]
    return indices


class _SpuState:
    def __init__(self):
        self.x1 = 0
        self.y1 = 0
        self.x2 = 0
        self.y2 = 0
        self.color_idx = (0, 0, 0, 0)
        self.alpha = (0, 0, 0, 0)
        self.even_offset = 0
        self.odd_offset = 0
        self.stop_date = None


def _parse_control_sequences(data, dcsqt_offset):
    state = _SpuState()
    offset = dcsqt_offset
    seen = set()
    while 0 <= offset <= len(data) - 4 and offset not in seen:
        seen.add(offset)
        date = struct.unpack_from(">H", data, offset)[0]
        next_offset = struct.unpack_from(">H", data, offset + 2)[0]
        pos = offset + 4
        while pos < len(data):
            cmd = data[pos]
            pos += 1
            if cmd == 0xFF:
                break
            if cmd in (0x00, 0x01):
                continue
            if cmd == 0x02:
                state.stop_date = date * 1024.0 / 90_000.0
                continue
            if cmd == 0x03:
                if pos + 2 > len(data):
                    break
                b0, b1 = data[pos], data[pos + 1]
                state.color_idx = (b1 & 0xF, b1 >> 4, b0 & 0xF, b0 >> 4)
                pos += 2
                continue
            if cmd == 0x04:
                if pos + 2 > len(data):
                    break
                b0, b1 = data[pos], data[pos + 1]
                state.alpha = (b1 & 0xF, b1 >> 4, b0 & 0xF, b0 >> 4)
                pos += 2
                continue
            if cmd == 0x05:
                if pos + 6 > len(data):
                    break
                b = data[pos:pos + 6]
                state.x1 = (b[0] << 4) | (b[1] >> 4)
                state.x2 = ((b[1] & 0x0F) << 8) | b[2]
                state.y1 = (b[3] << 4) | (b[4] >> 4)
                state.y2 = ((b[4] & 0x0F) << 8) | b[5]
                pos += 6
                continue
            if cmd == 0x06:
                if pos + 4 > len(data):
                    break
                state.even_offset, state.odd_offset = struct.unpack_from(">HH", data, pos)
                pos += 4
                continue
            break
        if next_offset == offset:
            break
        offset = next_offset
    return state


def _render(indices, palette, color_idx, alpha):
    h, w = indices.shape
    canvas = np.zeros((h, w, 3), dtype=np.float32)
    for pixel_value in range(4):
        mask = indices == pixel_value
        if not mask.any():
            continue
        pal_index = color_idx[pixel_value]
        r, g, b = palette[pal_index] if 0 <= pal_index < len(palette) else (0, 0, 0)
        a = alpha[pixel_value] / 15.0
        canvas[mask] = (b * a, g * a, r * a)
    return np.clip(canvas, 0, 255).astype(np.uint8)


def parse_vobsub(idx_path, sub_path=None):
    if sub_path is None:
        sub_path = _infer_sub_path(idx_path)
    _width, _height, palette, entries = parse_idx(idx_path)
    if not entries:
        return []
    with open(sub_path, "rb") as f:
        buf = f.read()

    events = []
    idx = 0
    for i, (start, filepos) in enumerate(entries):
        try:
            packet = _extract_spu_packet(buf, filepos)
            if len(packet) < 4:
                continue
            dcsqt_offset = struct.unpack_from(">H", packet, 2)[0]
            state = _parse_control_sequences(packet, dcsqt_offset)
            w = state.x2 - state.x1 + 1
            h = state.y2 - state.y1 + 1
            if w <= 0 or h <= 0:
                continue
            bitmap = _decode_bitmap(packet, state.even_offset, state.odd_offset, w, h)
            image = _render(bitmap, palette, state.color_idx, state.alpha)
        except (struct.error, IndexError):
            continue

        if state.stop_date is not None:
            end = start + state.stop_date
        elif i + 1 < len(entries):
            end = entries[i + 1][0]
        else:
            end = start + 4.0
        end = max(end, start + 0.01)

        events.append(ImageEvent(index=idx, start=start, end=end, image=image))
        idx += 1
    return events


def load_vobsub(idx_path, sub_path=None):
    return ImageSetReader(idx_path, parse_vobsub(idx_path, sub_path))
