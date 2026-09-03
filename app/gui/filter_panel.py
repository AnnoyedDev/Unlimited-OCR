import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..video.filters import FilterPipeline, default_pipeline

_PARAM_SPECS = {
    "Agrandir (upscale)": {"factor": ("double", 0.5, 4.0, 0.1, 1)},
    "Débruitage": {"strength": ("int", 1, 30)},
    "Niveaux de gris": {},
    "CLAHE (contraste local)": {
        "clip_limit": ("double", 0.5, 8.0, 0.1, 1),
        "tile_size": ("int", 2, 32),
    },
    "Luminosité / Contraste": {
        "contrast": ("double", 0.1, 3.0, 0.05, 2),
        "brightness": ("int", -100, 100),
    },
    "Gamma": {"gamma": ("double", 0.2, 3.0, 0.05, 2)},
    "Netteté": {"amount": ("double", 0.0, 3.0, 0.1, 1)},
    "Seuillage (binarisation)": {
        "mode": ("choice", ["otsu", "adaptive"]),
        "block_size": ("int", 3, 99),
        "c": ("int", -20, 20),
    },
    "Morphologie": {
        "op": ("choice", ["dilate", "erode"]),
        "kernel_size": ("int", 1, 15),
        "iterations": ("int", 1, 5),
    },
    "Inverser les couleurs": {},
}


class FilterPanel(QWidget):
    pipelineChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pipeline = FilterPipeline(default_pipeline())

        outer = QVBoxLayout(self)
        outer.addWidget(QLabel("<b>Filtres (effets en direct)</b>"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._steps_layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        for step in self.pipeline.steps:
            self._steps_layout.addWidget(self._build_step_box(step))
        self._steps_layout.addStretch(1)

        outer.addWidget(QLabel("Aperçu (zone rognée + filtres)"))
        self.preview_label = QLabel()
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background-color: #222; color: #888;")
        self.preview_label.setText("Pas d'aperçu")
        outer.addWidget(self.preview_label)

    def _build_step_box(self, step):
        box = QGroupBox()
        checkbox = QCheckBox(step.name)
        checkbox.setChecked(step.enabled)
        checkbox.toggled.connect(lambda checked, s=step: self._set_enabled(s, checked))

        form = QFormLayout()
        form.addRow(checkbox)

        for param_key, spec in _PARAM_SPECS.get(step.name, {}).items():
            widget = self._build_param_widget(step, param_key, spec)
            form.addRow(param_key.replace("_", " "), widget)

        box.setLayout(form)
        return box

    def _build_param_widget(self, step, param_key, spec):
        kind = spec[0]
        current = step.params.get(param_key)

        if kind == "double":
            _, lo, hi, inc, decimals = spec
            w = QDoubleSpinBox()
            w.setRange(lo, hi)
            w.setSingleStep(inc)
            w.setDecimals(decimals)
            w.setValue(current if current is not None else lo)
            w.valueChanged.connect(lambda v, s=step, k=param_key: self._set_param(s, k, v))
            return w

        if kind == "int":
            _, lo, hi = spec
            w = QSpinBox()
            w.setRange(lo, hi)
            w.setValue(current if current is not None else lo)
            w.valueChanged.connect(lambda v, s=step, k=param_key: self._set_param(s, k, v))
            return w

        if kind == "choice":
            options = spec[1]
            w = QComboBox()
            w.addItems(options)
            if current in options:
                w.setCurrentText(current)
            w.currentTextChanged.connect(lambda v, s=step, k=param_key: self._set_param(s, k, v))
            return w

        raise ValueError(f"Unknown widget kind: {kind}")

    def _set_enabled(self, step, checked):
        step.enabled = checked
        self.pipelineChanged.emit()

    def _set_param(self, step, key, value):
        step.params[key] = value
        self.pipelineChanged.emit()

    def set_preview_image(self, frame):
        if frame is None or frame.size == 0:
            self.preview_label.setText("Pas d'aperçu")
            self.preview_label.setPixmap(QPixmap())
            return
        frame = np.ascontiguousarray(frame)
        h, w = frame.shape[:2]
        image = QImage(frame.data, w, h, frame.strides[0], QImage.Format_BGR888)
        pixmap = QPixmap.fromImage(image).scaled(
            self.preview_label.width() or 240,
            self.preview_label.height() or 120,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)
