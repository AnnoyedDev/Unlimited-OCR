import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .crop_rect_item import CropRectItem
from .video_widget import frame_to_pixmap


class ImageSetWidget(QWidget):
    frameChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = None
        self.current_index = 0
        self._last_frame = None

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHints(self.view.renderHints())
        self.view.setDragMode(QGraphicsView.NoDrag)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.crop_item = None

        self.list_widget = QListWidget()
        self.list_widget.setMaximumWidth(220)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)

        self.prev_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.prev_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))

        self.info_label = QLabel("Aucun jeu d'images chargé")

        self.whole_image_check = QCheckBox("Toujours prendre l'image entière")
        self.whole_image_check.setToolTip(
            "Ignore le cadre de recadrage et envoie l'image entière à l'OCR pour "
            "chaque sous-titre, plutôt que la zone sélectionnée. Utile pour les "
            ".sup/.idx dont chaque image est déjà recadrée par le format autour du "
            "sous-titre, avec une position et une taille qui varient d'une image à "
            "l'autre."
        )
        self.whole_image_check.toggled.connect(self._on_whole_image_toggled)

        controls = QHBoxLayout()
        controls.addWidget(self.prev_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.info_label)
        controls.addStretch(1)
        controls.addWidget(self.whole_image_check)

        preview_col = QVBoxLayout()
        preview_col.addWidget(self.view, stretch=1)
        preview_col.addLayout(controls)
        preview_container = QWidget()
        preview_container.setLayout(preview_col)

        splitter = QSplitter()
        splitter.addWidget(self.list_widget)
        splitter.addWidget(preview_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([200, 700])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    def load_reader(self, reader):
        self.reader = reader

        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for event in reader.events:
            self.list_widget.addItem(
                QListWidgetItem(f"#{event.index}  {_fmt(event.start)} -> {_fmt(event.end)}")
            )
        self.list_widget.blockSignals(False)

        if self.crop_item is not None:
            self.scene.removeItem(self.crop_item)
            self.crop_item = None
        if reader.events:
            bounds = QRectF(0, 0, reader.width, reader.height)
            self.crop_item = CropRectItem(bounds)
            self.crop_item.signals.changed.connect(self.frameChanged.emit)
            self.crop_item.setVisible(not self.whole_image_check.isChecked())
            self.scene.addItem(self.crop_item)

        has_events = bool(reader.events)
        self.prev_button.setEnabled(has_events)
        self.next_button.setEnabled(has_events)
        self.show_index(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.reader is not None and self.reader.events:
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def show_index(self, index):
        if self.reader is None or not self.reader.events:
            return
        index = max(0, min(len(self.reader.events) - 1, index))
        event = self.reader.events[index]
        self.current_index = index
        self._last_frame = event.image

        bounds = QRectF(0, 0, event.image.shape[1], event.image.shape[0])
        if self.crop_item is not None:
            self.crop_item.set_bounds(bounds)
        self.scene.setSceneRect(bounds)

        self.pixmap_item.setPixmap(frame_to_pixmap(event.image))
        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

        self.list_widget.blockSignals(True)
        self.list_widget.setCurrentRow(index)
        self.list_widget.blockSignals(False)

        self.info_label.setText(
            f"Image {index + 1}/{len(self.reader.events)}  "
            f"[{_fmt(event.start)} -> {_fmt(event.end)}]"
        )
        self.frameChanged.emit()

    def step(self, delta):
        if self.reader is None:
            return
        self.show_index(self.current_index + delta)

    def _on_row_changed(self, row):
        if row >= 0:
            self.show_index(row)

    def _on_whole_image_toggled(self, checked):
        if self.crop_item is not None:
            self.crop_item.setVisible(not checked)
        self.frameChanged.emit()

    def get_current_frame(self):
        return self._last_frame

    def get_crop_rect_norm(self):
        if self.whole_image_check.isChecked() or self.crop_item is None:
            return (0.0, 0.0, 1.0, 1.0)
        return self.crop_item.normalized_rect()


def _fmt(seconds):
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"
