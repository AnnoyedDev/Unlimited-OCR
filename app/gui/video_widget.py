import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..video.reader import VideoReader
from .crop_rect_item import CropRectItem


def frame_to_pixmap(frame):
    h, w = frame.shape[:2]
    frame = np.ascontiguousarray(frame)
    image = QImage(frame.data, w, h, frame.strides[0], QImage.Format_BGR888)
    return QPixmap.fromImage(image)


class VideoWidget(QWidget):
    frameChanged = Signal()
    videoLoaded = Signal(int, int, float, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.reader = None
        self.current_index = 0
        self._playing = False

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHints(self.view.renderHints())
        self.view.setDragMode(QGraphicsView.NoDrag)

        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.crop_item = None

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setEnabled(False)
        self.slider.valueChanged.connect(self._on_slider_changed)

        self.play_button = QPushButton("Lecture")
        self.play_button.setEnabled(False)
        self.play_button.clicked.connect(self.toggle_play)

        self.prev_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.prev_button.clicked.connect(lambda: self.step(-1))
        self.next_button.clicked.connect(lambda: self.step(1))

        self.time_label = QLabel("--:-- / --:--  (frame -/-)")

        controls = QHBoxLayout()
        controls.addWidget(self.play_button)
        controls.addWidget(self.prev_button)
        controls.addWidget(self.next_button)
        controls.addWidget(self.time_label)

        layout = QVBoxLayout(self)
        layout.addWidget(self.view, stretch=1)
        layout.addLayout(controls)
        layout.addWidget(self.slider)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._advance_playback)

    def load_video(self, path):
        if self.reader is not None:
            self.reader.close()
        self._playing = False
        self._timer.stop()
        self.play_button.setText("Lecture")

        self.reader = VideoReader(path)
        bounds = QRectF(0, 0, self.reader.width, self.reader.height)

        self.crop_item = CropRectItem(bounds)
        self.crop_item.signals.changed.connect(self.frameChanged.emit)
        self.scene.addItem(self.crop_item)
        self.scene.setSceneRect(bounds)

        self.slider.setEnabled(True)
        self.slider.setMinimum(0)
        self.slider.setMaximum(max(0, self.reader.frame_count - 1))
        self.play_button.setEnabled(True)
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)

        self.videoLoaded.emit(
            self.reader.width, self.reader.height, self.reader.fps, self.reader.frame_count
        )
        self.show_frame(0)
        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.reader is not None:
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def show_frame(self, index):
        if self.reader is None:
            return
        frame = self.reader.get_frame(index)
        if frame is None:
            return
        self.current_index = index
        self._last_frame = frame
        self.pixmap_item.setPixmap(frame_to_pixmap(frame))

        self.slider.blockSignals(True)
        self.slider.setValue(index)
        self.slider.blockSignals(False)

        t = self.reader.timestamp_of(index)
        total_t = self.reader.duration
        self.time_label.setText(
            f"{_fmt(t)} / {_fmt(total_t)}  (frame {index}/{self.reader.frame_count})"
        )
        self.frameChanged.emit()

    def step(self, delta):
        if self.reader is None:
            return
        self.show_frame(max(0, min(self.reader.frame_count - 1, self.current_index + delta)))

    def toggle_play(self):
        if self.reader is None:
            return
        self._playing = not self._playing
        if self._playing:
            self.play_button.setText("Pause")
            interval_ms = max(1, round(1000 / (self.reader.fps or 25)))
            self._timer.start(interval_ms)
        else:
            self.play_button.setText("Lecture")
            self._timer.stop()

    def _advance_playback(self):
        if self.reader is None:
            return
        if self.current_index >= self.reader.frame_count - 1:
            self.toggle_play()
            return
        self.show_frame(self.current_index + 1)

    def _on_slider_changed(self, value):
        if self._playing:
            self.toggle_play()
        self.show_frame(value)

    def get_current_frame(self):
        return getattr(self, "_last_frame", None)

    def get_crop_rect_norm(self):
        if self.crop_item is None:
            return (0.0, 0.0, 1.0, 1.0)
        return self.crop_item.normalized_rect()


def _fmt(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
