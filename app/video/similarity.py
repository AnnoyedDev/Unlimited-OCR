import cv2
import numpy as np

DIFF_THRESHOLD = 18
MAX_SIDE = 480
GAIN = 6.0


def _prepare(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    h, w = gray.shape[:2]
    if max(h, w) > MAX_SIDE:
        scale = MAX_SIDE / max(h, w)
        gray = cv2.resize(gray, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    return gray


def _similarity(a, b):
    if a.shape != b.shape:
        b = cv2.resize(b, (a.shape[1], a.shape[0]))
    diff = cv2.absdiff(a, b)
    changed_fraction = float(np.mean(diff > DIFF_THRESHOLD))
    return 100.0 - min(100.0, changed_fraction * 100.0 * GAIN)


def similarity_percent(frame_a, frame_b):
    return _similarity(_prepare(frame_a), _prepare(frame_b))


class DuplicateSkipper:
    def __init__(self, threshold_percent=99.0):
        self.threshold_percent = threshold_percent
        self._last_prepared = None

    def should_skip(self, frame):
        prepared = _prepare(frame)
        if self._last_prepared is None:
            self._last_prepared = prepared
            return False

        similarity = _similarity(prepared, self._last_prepared)

        if similarity >= self.threshold_percent:
            return True

        self._last_prepared = prepared
        return False

    def reset(self):
        self._last_prepared = None
