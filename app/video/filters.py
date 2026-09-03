import cv2
import numpy as np


def _ensure_bgr(frame):
    if frame.ndim == 2:
        return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    return frame


def f_upscale(frame, factor=2.0):
    if factor == 1.0:
        return frame
    interp = cv2.INTER_CUBIC if factor > 1.0 else cv2.INTER_AREA
    return cv2.resize(frame, None, fx=factor, fy=factor, interpolation=interp)


def f_denoise(frame, strength=7):
    return cv2.fastNlMeansDenoisingColored(frame, None, strength, strength, 7, 21)


def f_grayscale(frame, enabled=True):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return _ensure_bgr(gray)


def f_clahe(frame, clip_limit=2.5, tile_size=8):
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile_size, tile_size))
    l = clahe.apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def f_brightness_contrast(frame, contrast=1.0, brightness=0):
    return cv2.convertScaleAbs(frame, alpha=contrast, beta=brightness)


def f_gamma(frame, gamma=1.0):
    if gamma == 1.0:
        return frame
    inv = 1.0 / max(gamma, 1e-6)
    table = ((np.arange(256) / 255.0) ** inv * 255).astype(np.uint8)
    return cv2.LUT(frame, table)


def f_sharpen(frame, amount=1.0):
    if amount == 0:
        return frame
    blurred = cv2.GaussianBlur(frame, (0, 0), 3)
    return cv2.addWeighted(frame, 1 + amount, blurred, -amount, 0)


def f_threshold(frame, mode="otsu", block_size=31, c=5):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if mode == "adaptive":
        block_size = block_size if block_size % 2 == 1 else block_size + 1
        out = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c
        )
    else:
        _, out = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return _ensure_bgr(out)


def f_morphology(frame, op="dilate", kernel_size=2, iterations=1):
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    fn = cv2.dilate if op == "dilate" else cv2.erode
    return fn(frame, kernel, iterations=iterations)


def f_invert(frame, enabled=True):
    return cv2.bitwise_not(frame)


class FilterStep:
    def __init__(self, name, fn, enabled=False, params=None):
        self.name = name
        self.fn = fn
        self.enabled = enabled
        self.params = params if params is not None else {}

    def apply(self, frame):
        return self.fn(frame, **self.params)


def default_pipeline():
    return [
        FilterStep("Agrandir (upscale)", f_upscale, enabled=True, params={"factor": 2.0}),
        FilterStep("Débruitage", f_denoise, params={"strength": 7}),
        FilterStep("Niveaux de gris", f_grayscale),
        FilterStep("CLAHE (contraste local)", f_clahe, params={"clip_limit": 2.5, "tile_size": 8}),
        FilterStep("Luminosité / Contraste", f_brightness_contrast, params={"contrast": 1.0, "brightness": 0}),
        FilterStep("Gamma", f_gamma, params={"gamma": 1.0}),
        FilterStep("Netteté", f_sharpen, params={"amount": 1.0}),
        FilterStep("Seuillage (binarisation)", f_threshold, params={"mode": "otsu", "block_size": 31, "c": 5}),
        FilterStep("Morphologie", f_morphology, params={"op": "dilate", "kernel_size": 2, "iterations": 1}),
        FilterStep("Inverser les couleurs", f_invert),
    ]


class FilterPipeline:
    def __init__(self, steps=None):
        self.steps = steps if steps is not None else default_pipeline()

    def apply(self, frame):
        out = frame
        for step in self.steps:
            if step.enabled:
                out = step.apply(out)
        return out
