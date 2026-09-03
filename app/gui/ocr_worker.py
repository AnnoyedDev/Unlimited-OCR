import copy

from PySide6.QtCore import QObject, Signal

from ..batch_advisor import finish_measurement, start_measurement
from ..config import DEFAULT_OCR_PROMPT
from ..subtitles.builder import AnalyzedFrame
from ..subtitles.lang_filter import looks_like_unwanted_chinese
from ..video.filters import FilterPipeline
from ..video.italic import DEFAULT_ANGLE_THRESHOLD_DEG, detect_italic
from ..video.reader import VideoReader, crop_frame
from ..video.similarity import DuplicateSkipper
from ..video.textbox import find_bright_text_bbox, looks_like_garbage, prepare_retry_crop

_GAP_EPSILON = 0.05


class EngineManager:
    def __init__(self):
        self._engine = None

    def get(self):
        if self._engine is None:
            from ..ocr_engine import OcrEngine

            self._engine = OcrEngine.load()
        return self._engine

    @property
    def loaded(self):
        return self._engine is not None


class OcrWorker(QObject):
    progress = Signal(int, int)
    frameResult = Signal(object)
    finished = Signal(list)
    error = Signal(str)
    status = Signal(str)
    memoryCalibrated = Signal(float)

    def __init__(
        self,
        engine_manager,
        video_path,
        rect_norm,
        step,
        similarity_threshold,
        filter_steps,
        prompt=DEFAULT_OCR_PROMPT,
        filter_chinese=True,
        force_periodic_check=False,
        scan_by_interval=False,
        batch_size=4,
        retry_on_empty=True,
        detect_italic=False,
        italic_angle_threshold=DEFAULT_ANGLE_THRESHOLD_DEG,
        parent=None,
    ):
        super().__init__(parent)
        self._engine_manager = engine_manager
        self.video_path = video_path
        self.rect_norm = rect_norm
        self.step = max(1, step)
        self.similarity_threshold = similarity_threshold
        self.filter_steps = copy.deepcopy(filter_steps)
        self.prompt = prompt
        self.filter_chinese = filter_chinese
        self.force_periodic_check = force_periodic_check
        self.scan_by_interval = scan_by_interval
        self.batch_size = max(1, batch_size)
        self.retry_on_empty = retry_on_empty
        self.detect_italic = detect_italic
        self.italic_angle_threshold = italic_angle_threshold
        self._stop_requested = False
        self._calibrated = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        engine = None
        try:
            from ..ocr_engine import bgr_to_pil

            if not self._engine_manager.loaded:
                self.status.emit("Chargement du modèle Unlimited-OCR (première utilisation)...")
            engine = self._engine_manager.get()
            self.status.emit(f"Modèle prêt sur {engine.device_info}")

            pipeline = FilterPipeline(self.filter_steps)
            skipper = DuplicateSkipper(threshold_percent=self.similarity_threshold)
            results = []

            pending_meta = []
            pending_images = []
            pending_raw_crops = []

            def flush_batch():
                if not pending_images:
                    return
                measuring = not self._calibrated
                if measuring:
                    baseline = start_measurement(engine.device_info)
                texts = engine.ocr_images_batch(list(pending_images), prompt=self.prompt)
                if measuring:
                    used = finish_measurement(engine.device_info, baseline)
                    self._calibrated = True
                    if used > 0:
                        self.memoryCalibrated.emit(used / len(pending_images))

                if self.retry_on_empty:
                    retry_positions, retry_images = [], []
                    for pos, (text, raw_crop) in enumerate(zip(texts, pending_raw_crops)):
                        if text.strip():
                            continue
                        bbox = find_bright_text_bbox(raw_crop)
                        if bbox is None:
                            continue
                        retry_positions.append(pos)
                        retry_images.append(bgr_to_pil(prepare_retry_crop(raw_crop, bbox)))

                    if retry_images:
                        retry_texts = engine.ocr_images_batch(retry_images, prompt=self.prompt)
                        for pos, retry_text in zip(retry_positions, retry_texts):
                            retry_text = retry_text.strip()
                            if retry_text and not looks_like_garbage(retry_text):
                                texts[pos] = retry_text

                for (idx, ts), text, raw_crop in zip(pending_meta, texts, pending_raw_crops):
                    if self.filter_chinese and looks_like_unwanted_chinese(text):
                        text = ""
                    italic = self.detect_italic and detect_italic(raw_crop, self.italic_angle_threshold)
                    analyzed = AnalyzedFrame(idx, ts, text=text, italic=italic)
                    results.append(analyzed)
                    self.frameResult.emit(analyzed)
                pending_meta.clear()
                pending_images.clear()
                pending_raw_crops.clear()

            scan_step = self.step if self.scan_by_interval else 1
            with VideoReader(self.video_path) as reader:
                total = len(range(0, reader.frame_count, scan_step))
                count = 0
                last_ocr_index = -self.step
                for info in reader.iter_frames(step=scan_step):
                    if self._stop_requested:
                        break
                    count += 1

                    cropped = crop_frame(info.frame, self.rect_norm)
                    changed = not skipper.should_skip(cropped)
                    due_for_check = self.force_periodic_check and (info.index - last_ocr_index) >= self.step

                    if changed or due_for_check:
                        filtered = pipeline.apply(cropped)
                        pending_meta.append((info.index, info.timestamp))
                        pending_images.append(bgr_to_pil(filtered))
                        pending_raw_crops.append(cropped)
                        last_ocr_index = info.index
                        if len(pending_images) >= self.batch_size:
                            flush_batch()
                    else:
                        analyzed = AnalyzedFrame(info.index, info.timestamp, text=None)
                        results.append(analyzed)
                        self.frameResult.emit(analyzed)

                    self.progress.emit(count, total)

                flush_batch()

            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if engine is not None and engine.device_info.is_gpu:
                import torch

                torch.cuda.empty_cache()


class ImageSetOcrWorker(QObject):
    progress = Signal(int, int)
    frameResult = Signal(object)
    finished = Signal(list)
    error = Signal(str)
    status = Signal(str)
    memoryCalibrated = Signal(float)

    def __init__(
        self,
        engine_manager,
        events,
        rect_norm,
        similarity_threshold,
        filter_steps,
        prompt=DEFAULT_OCR_PROMPT,
        filter_chinese=True,
        batch_size=4,
        retry_on_empty=True,
        detect_italic=False,
        italic_angle_threshold=DEFAULT_ANGLE_THRESHOLD_DEG,
        parent=None,
    ):
        super().__init__(parent)
        self._engine_manager = engine_manager
        self.events = events
        self.rect_norm = rect_norm
        self.similarity_threshold = similarity_threshold
        self.filter_steps = copy.deepcopy(filter_steps)
        self.prompt = prompt
        self.filter_chinese = filter_chinese
        self.batch_size = max(1, batch_size)
        self.retry_on_empty = retry_on_empty
        self.detect_italic = detect_italic
        self.italic_angle_threshold = italic_angle_threshold
        self._stop_requested = False
        self._calibrated = False

    def stop(self):
        self._stop_requested = True

    def run(self):
        engine = None
        try:
            from ..ocr_engine import bgr_to_pil

            if not self._engine_manager.loaded:
                self.status.emit("Chargement du modèle Unlimited-OCR (première utilisation)...")
            engine = self._engine_manager.get()
            self.status.emit(f"Modèle prêt sur {engine.device_info}")

            pipeline = FilterPipeline(self.filter_steps)
            skipper = DuplicateSkipper(threshold_percent=self.similarity_threshold)
            results = []

            pending_meta = []
            pending_images = []
            pending_raw_crops = []

            def emit_result(idx, ts, text, gap_end, italic=False):
                analyzed = AnalyzedFrame(idx, ts, text=text, italic=italic)
                results.append(analyzed)
                self.frameResult.emit(analyzed)
                if gap_end is not None:
                    results.append(AnalyzedFrame(idx + 1, gap_end, text=""))

            def flush_batch():
                if not pending_images:
                    return
                measuring = not self._calibrated
                if measuring:
                    baseline = start_measurement(engine.device_info)
                texts = engine.ocr_images_batch(list(pending_images), prompt=self.prompt)
                if measuring:
                    used = finish_measurement(engine.device_info, baseline)
                    self._calibrated = True
                    if used > 0:
                        self.memoryCalibrated.emit(used / len(pending_images))

                if self.retry_on_empty:
                    retry_positions, retry_images = [], []
                    for pos, (text, raw_crop) in enumerate(zip(texts, pending_raw_crops)):
                        if text.strip():
                            continue
                        bbox = find_bright_text_bbox(raw_crop)
                        if bbox is None:
                            continue
                        retry_positions.append(pos)
                        retry_images.append(bgr_to_pil(prepare_retry_crop(raw_crop, bbox)))

                    if retry_images:
                        retry_texts = engine.ocr_images_batch(retry_images, prompt=self.prompt)
                        for pos, retry_text in zip(retry_positions, retry_texts):
                            retry_text = retry_text.strip()
                            if retry_text and not looks_like_garbage(retry_text):
                                texts[pos] = retry_text

                for (idx, ts, gap_end), text, raw_crop in zip(pending_meta, texts, pending_raw_crops):
                    if self.filter_chinese and looks_like_unwanted_chinese(text):
                        text = ""
                    italic = self.detect_italic and detect_italic(raw_crop, self.italic_angle_threshold)
                    emit_result(idx, ts, text, gap_end, italic=italic)
                pending_meta.clear()
                pending_images.clear()
                pending_raw_crops.clear()

            total = len(self.events)
            for i, event in enumerate(self.events):
                if self._stop_requested:
                    break

                next_start = self.events[i + 1].start if i + 1 < total else None
                needs_gap = next_start is None or (next_start - event.end) > _GAP_EPSILON
                gap_end = event.end if needs_gap else None

                cropped = crop_frame(event.image, self.rect_norm)
                if not skipper.should_skip(cropped):
                    filtered = pipeline.apply(cropped)
                    pending_meta.append((2 * i, event.start, gap_end))
                    pending_images.append(bgr_to_pil(filtered))
                    pending_raw_crops.append(cropped)
                    if len(pending_images) >= self.batch_size:
                        flush_batch()
                else:
                    emit_result(2 * i, event.start, None, gap_end)

                self.progress.emit(i + 1, total)

            flush_batch()

            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if engine is not None and engine.device_info.is_gpu:
                import torch

                torch.cuda.empty_cache()


class ImageSetLoadWorker(QObject):
    finished = Signal(object)
    error = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            lower = self.path.lower()
            if lower.endswith(".sup"):
                from ..formats.pgs import load_pgs

                reader = load_pgs(self.path)
            elif lower.endswith(".idx"):
                from ..formats.vobsub import load_vobsub

                reader = load_vobsub(self.path)
            else:
                self.error.emit("Choisissez un fichier .sup (PGS) ou .idx (VobSub).")
                return
        except Exception as exc:
            self.error.emit(str(exc))
            return
        self.finished.emit(reader)
