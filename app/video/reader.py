import cv2
import numpy as np


class FrameInfo:
    def __init__(self, index, timestamp, frame):
        self.index = index
        self.timestamp = timestamp
        self.frame = frame


class VideoReader:
    def __init__(self, path):
        self.path = path
        self._cap = cv2.VideoCapture(path)
        if not self._cap.isOpened():
            raise IOError(f"Could not open video: {path}")

        self.fps = self._cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.frame_count = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration = self.frame_count / self.fps if self.fps else 0.0

    def timestamp_of(self, index):
        return index / self.fps if self.fps else 0.0

    def get_frame(self, index):
        index = max(0, min(index, self.frame_count - 1))
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._cap.read()
        return frame if ok else None

    def iter_frames(self, step=1, start=0, end=None):
        end = self.frame_count if end is None else min(end, self.frame_count)
        step = max(1, step)

        self._cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        index = start
        while index < end:
            ok, frame = self._cap.read()
            if not ok:
                break
            yield FrameInfo(index=index, timestamp=self.timestamp_of(index), frame=frame)

            next_index = index + step
            if step > 1:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, next_index)
            index = next_index

    def close(self):
        self._cap.release()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def crop_frame(frame, rect_norm):
    h, w = frame.shape[:2]
    x, y, rw, rh = rect_norm
    x0 = max(0, min(w - 1, round(x * w)))
    y0 = max(0, min(h - 1, round(y * h)))
    x1 = max(x0 + 1, min(w, round((x + rw) * w)))
    y1 = max(y0 + 1, min(h, round((y + rh) * h)))
    return frame[y0:y1, x0:x1]
