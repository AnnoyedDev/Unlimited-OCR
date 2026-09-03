from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

HANDLE_SIZE = 10.0
MIN_SIZE = 12.0


class _Signals(QObject):
    changed = Signal()


class CropRectItem(QGraphicsRectItem):
    def __init__(self, bounds, parent=None):
        super().__init__(parent)
        self.bounds = QRectF(bounds)
        self.signals = _Signals()

        init = QRectF(
            bounds.x() + bounds.width() * 0.1,
            bounds.y() + bounds.height() * 0.62,
            bounds.width() * 0.8,
            bounds.height() * 0.28,
        )
        self.setRect(init)
        self.setPen(QPen(QColor(220, 0, 0), 2))
        self.setBrush(QBrush(QColor(220, 0, 0, 40)))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        self._mode = None
        self._start_rect = None
        self._start_pos = None

    def set_bounds(self, bounds):
        x, y, w, h = self.normalized_rect()
        self.bounds = QRectF(bounds)
        self.prepareGeometryChange()
        self.setRect(QRectF(
            self.bounds.x() + x * self.bounds.width(),
            self.bounds.y() + y * self.bounds.height(),
            w * self.bounds.width(),
            h * self.bounds.height(),
        ))
        self._clamp()

    def normalized_rect(self):
        r, b = self.rect(), self.bounds
        if b.width() <= 0 or b.height() <= 0:
            return (0.0, 0.0, 1.0, 1.0)
        x = (r.x() - b.x()) / b.width()
        y = (r.y() - b.y()) / b.height()
        w = r.width() / b.width()
        h = r.height() / b.height()
        return (
            max(0.0, min(1.0, x)),
            max(0.0, min(1.0, y)),
            max(0.0, min(1.0, w)),
            max(0.0, min(1.0, h)),
        )

    def boundingRect(self):
        pad = HANDLE_SIZE
        return self.rect().adjusted(-pad, -pad, pad, pad)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def _handle_rects(self):
        r, h = self.rect(), HANDLE_SIZE
        cx, cy = r.center().x(), r.center().y()
        return {
            "tl": QRectF(r.left() - h / 2, r.top() - h / 2, h, h),
            "tr": QRectF(r.right() - h / 2, r.top() - h / 2, h, h),
            "bl": QRectF(r.left() - h / 2, r.bottom() - h / 2, h, h),
            "br": QRectF(r.right() - h / 2, r.bottom() - h / 2, h, h),
            "t": QRectF(cx - h / 2, r.top() - h / 2, h, h),
            "b": QRectF(cx - h / 2, r.bottom() - h / 2, h, h),
            "l": QRectF(r.left() - h / 2, cy - h / 2, h, h),
            "r": QRectF(r.right() - h / 2, cy - h / 2, h, h),
        }

    def _handle_at(self, pos):
        for name, hr in self._handle_rects().items():
            if hr.contains(pos):
                return name
        return None

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        painter.setBrush(QBrush(QColor(220, 0, 0)))
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        for hr in self._handle_rects().values():
            painter.drawRect(hr)

    _CURSORS = {
        "tl": Qt.SizeFDiagCursor,
        "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor,
        "bl": Qt.SizeBDiagCursor,
        "t": Qt.SizeVerCursor,
        "b": Qt.SizeVerCursor,
        "l": Qt.SizeHorCursor,
        "r": Qt.SizeHorCursor,
    }

    def hoverMoveEvent(self, event):
        handle = self._handle_at(event.pos())
        self.setCursor(self._CURSORS.get(handle, Qt.SizeAllCursor))
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        self._mode = self._handle_at(event.pos()) or "move"
        self._start_rect = QRectF(self.rect())
        self._start_pos = event.pos()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._start_pos is None or self._start_rect is None:
            return
        delta = event.pos() - self._start_pos
        r = QRectF(self._start_rect)

        if self._mode == "move":
            r.translate(delta)
        else:
            h = self._mode or ""
            if "l" in h:
                r.setLeft(r.left() + delta.x())
            if "r" in h:
                r.setRight(r.right() + delta.x())
            if "t" in h:
                r.setTop(r.top() + delta.y())
            if "b" in h:
                r.setBottom(r.bottom() + delta.y())
            r = r.normalized()
            if r.width() < MIN_SIZE:
                r.setWidth(MIN_SIZE)
            if r.height() < MIN_SIZE:
                r.setHeight(MIN_SIZE)

        self.prepareGeometryChange()
        self.setRect(r)
        self._clamp()
        self.signals.changed.emit()
        event.accept()

    def mouseReleaseEvent(self, event):
        self._mode = None
        self._start_rect = None
        self._start_pos = None
        event.accept()

    def _clamp(self):
        r, b = QRectF(self.rect()), self.bounds
        if r.width() > b.width():
            r.setWidth(b.width())
        if r.height() > b.height():
            r.setHeight(b.height())
        if r.left() < b.left():
            r.moveLeft(b.left())
        if r.top() < b.top():
            r.moveTop(b.top())
        if r.right() > b.right():
            r.moveRight(b.right())
        if r.bottom() > b.bottom():
            r.moveBottom(b.bottom())
        self.prepareGeometryChange()
        self.setRect(r)
