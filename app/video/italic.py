import cv2
import numpy as np

BRIGHTNESS_CUTOFF = 170
MIN_FOREGROUND_PIXELS = 40
SHEAR_ANGLES_DEG = np.arange(-30.0, 30.5, 1.0)
DEFAULT_ANGLE_THRESHOLD_DEG = 8.0


def _binarize(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return (gray > BRIGHTNESS_CUTOFF).astype(np.uint8)


def _shear_score(binary, angle_deg):
    h, w = binary.shape
    shear = np.tan(np.radians(angle_deg))
    pad = int(np.ceil(abs(shear) * h))
    new_w = w + pad
    tx = pad if shear < 0 else 0
    matrix = np.float32([[1, shear, tx], [0, 1, 0]])
    sheared = cv2.warpAffine(binary, matrix, (new_w, h), flags=cv2.INTER_NEAREST)
    col_sums = sheared.sum(axis=0).astype(np.float64)
    return float(np.sum(col_sums ** 2))


def detect_italic(image_bgr, angle_threshold_deg=DEFAULT_ANGLE_THRESHOLD_DEG):
    binary = _binarize(image_bgr)
    if int(binary.sum()) < MIN_FOREGROUND_PIXELS:
        return False
    scores = [_shear_score(binary, angle) for angle in SHEAR_ANGLES_DEG]
    best_angle = SHEAR_ANGLES_DEG[int(np.argmax(scores))]
    return abs(best_angle) >= angle_threshold_deg
