import cv2
import numpy as np

BRIGHTNESS_CUTOFF = 170
MIN_AREA_FRACTION = 0.003
DILATE_KERNEL = (15, 5)
MARGIN_RATIO = 0.3
RETRY_TARGET_LONG_SIDE = 900
RETRY_THRESHOLD_CUTOFF = 185

MIN_ASPECT_RATIO = 1.6
MAX_HEIGHT_FRACTION = 0.65
MAX_AREA_FRACTION = 0.35


def find_bright_text_bbox(frame_bgr):
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    crop_h, crop_w = gray.shape[:2]
    mask = (gray > BRIGHTNESS_CUTOFF).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, DILATE_KERNEL)
    mask = cv2.dilate(mask, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = MIN_AREA_FRACTION * crop_h * crop_w
    boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= min_area]
    if not boxes:
        return None

    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    w, h = x1 - x0, y1 - y0

    if h <= 0 or w / h < MIN_ASPECT_RATIO:
        return None
    if h > MAX_HEIGHT_FRACTION * crop_h:
        return None
    if (w * h) > MAX_AREA_FRACTION * (crop_w * crop_h):
        return None

    return (x0, y0, w, h)


def prepare_retry_crop(raw_crop_bgr, bbox):
    x, y, w, h = bbox
    H, W = raw_crop_bgr.shape[:2]
    mx, my = int(w * MARGIN_RATIO) + 4, int(h * MARGIN_RATIO) + 4
    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(W, x + w + mx), min(H, y + h + my)
    tight = raw_crop_bgr[y0:y1, x0:x1]

    th, tw = tight.shape[:2]
    scale = RETRY_TARGET_LONG_SIDE / max(th, tw)
    if scale > 1:
        tight = cv2.resize(tight, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(tight, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, RETRY_THRESHOLD_CUTOFF, 255, cv2.THRESH_BINARY)
    return cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)


MAX_PLAUSIBLE_RETRY_LENGTH = 120
_GARBAGE_MARKERS = ("<|det|>", "<img", "<td", "</tr", "<table", "\\hline", "\\]", "\\[", "[Non-Text]")


def looks_like_garbage(text):
    if not text:
        return False
    if len(text) > MAX_PLAUSIBLE_RETRY_LENGTH:
        return True
    return any(marker in text for marker in _GARBAGE_MARKERS)
