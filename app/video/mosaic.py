from PIL import Image, ImageDraw, ImageFont

MAX_GROUP_SIZE = 8
SEPARATOR_HEIGHT = 60
SEPARATOR_BG = (255, 0, 255)
SEPARATOR_FG = (0, 0, 0)
MARKER_PREFIX = "SKIP"
MARKER_FONT_SIZE = 32


def _marker_text(index):
    return f"===={MARKER_PREFIX}{index}===="


def _font():
    try:
        return ImageFont.load_default(size=MARKER_FONT_SIZE)
    except TypeError:
        return ImageFont.load_default()


def build_mosaic(images):
    max_w = max(img.width for img in images)
    total_h = sum(img.height for img in images) + SEPARATOR_HEIGHT * (len(images) - 1)
    mosaic = Image.new("RGB", (max_w, total_h), (0, 0, 0))

    font = _font()
    markers = []
    y = 0
    for i, img in enumerate(images):
        mosaic.paste(img, (0, y))
        y += img.height
        if i < len(images) - 1:
            marker = _marker_text(i + 1)
            markers.append(marker)
            band = Image.new("RGB", (max_w, SEPARATOR_HEIGHT), SEPARATOR_BG)
            draw = ImageDraw.Draw(band)
            draw.text((10, SEPARATOR_HEIGHT // 4), marker, fill=SEPARATOR_FG, font=font)
            mosaic.paste(band, (0, y))
            y += SEPARATOR_HEIGHT
    return mosaic, markers


def split_mosaic_text(raw_text, expected_count, markers):
    if expected_count <= 1:
        return [raw_text]
    segments = []
    remaining = raw_text
    for marker in markers:
        idx = remaining.find(marker)
        if idx == -1:
            return None
        segments.append(remaining[:idx].strip())
        remaining = remaining[idx + len(marker):]
    segments.append(remaining.strip())
    if len(segments) != expected_count:
        return None
    return segments
