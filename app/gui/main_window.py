from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStackedWidget,
    QWidget,
)

from ..subtitles.ass_writer import write_ass
from ..subtitles.builder import build_cues
from ..video.reader import crop_frame
from .controls_panel import ControlsPanel
from .filter_panel import FilterPanel
from .image_set_widget import ImageSetWidget
from .ocr_worker import EngineManager, ImageSetLoadWorker, ImageSetOcrWorker, OcrWorker
from .video_widget import VideoWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Unlimited-OCR Subtitler")
        self.resize(1400, 900)

        self.engine_manager = EngineManager()
        self._results = []
        self._cues = []
        self._thread = None
        self._worker = None
        self._load_thread = None
        self._load_worker = None
        self._image_mode = False

        self.filter_panel = FilterPanel()
        self.video_widget = VideoWidget()
        self.image_set_widget = ImageSetWidget()
        self.controls_panel = ControlsPanel()

        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.video_widget)
        self.stacked_widget.addWidget(self.image_set_widget)

        splitter = QSplitter()
        splitter.addWidget(self.filter_panel)
        splitter.addWidget(self.stacked_widget)
        splitter.addWidget(self.controls_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 800, 320])
        self.setCentralWidget(splitter)

        self._build_menu()
        self._wire_signals()
        self._show_device_info()

    def _build_menu(self):
        menu = self.menuBar().addMenu("Fichier")
        open_action = menu.addAction("Ouvrir une vidéo...")
        open_action.triggered.connect(self.open_video_dialog)
        open_images_action = menu.addAction("Ouvrir un jeu d'images (.sup/.idx)...")
        open_images_action.triggered.connect(self.open_image_set_dialog)
        menu.addSeparator()
        self.image_mode_action = menu.addAction("Mode image (jeu d'images)")
        self.image_mode_action.setCheckable(True)
        self.image_mode_action.setToolTip(
            "Bascule l'aperçu principal entre lecteur vidéo (défilement continu) et "
            "navigateur d'images (une par une, avec liste) -- adapté à l'OCR à partir "
            "de sous-titres image (PGS .sup, VobSub .idx/.sub) plutôt qu'une vidéo."
        )
        self.image_mode_action.toggled.connect(self.set_image_mode)
        menu.addSeparator()
        export_action = menu.addAction("Exporter en .ass...")
        export_action.triggered.connect(self.export_ass_dialog)

    def _wire_signals(self):
        self.video_widget.frameChanged.connect(self._refresh_preview)
        self.image_set_widget.frameChanged.connect(self._refresh_preview)
        self.filter_panel.pipelineChanged.connect(self._refresh_preview)
        self.controls_panel.runRequested.connect(self.start_ocr)
        self.controls_panel.stopRequested.connect(self.stop_ocr)
        self.controls_panel.pauseToggled.connect(self.toggle_pause_ocr)
        self.controls_panel.exportRequested.connect(self.export_ass_dialog)

    @property
    def active_widget(self):
        return self.image_set_widget if self._image_mode else self.video_widget

    def set_image_mode(self, enabled):
        self._image_mode = enabled
        self.stacked_widget.setCurrentWidget(self.image_set_widget if enabled else self.video_widget)
        self.controls_panel.set_image_mode(enabled)
        self._refresh_preview()

    def _show_device_info(self):
        try:
            from ..batch_advisor import detect_capacity
            from ..device import detect_device

            info = detect_device()
            self.controls_panel.set_device_text(f"Device : {info}")
            free_bytes, total_bytes = detect_capacity(info)
            self.controls_panel.set_memory_capacity(free_bytes, total_bytes, info.is_gpu)
        except Exception as exc:
            self.controls_panel.set_device_text(f"Device : indisponible ({exc})")

    def open_video_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir une vidéo", "", "Vidéos (*.mp4 *.mkv *.avi *.mov *.webm);;Tous les fichiers (*)"
        )
        if path:
            self.video_widget.load_video(path)
            self.controls_panel.clear_results()
            self.controls_panel.set_export_enabled(False)
            self._results = []
            self._cues = []
            self.image_mode_action.setChecked(False)
            self.set_image_mode(False)

    def open_image_set_dialog(self):
        if self._load_thread is not None:
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Ouvrir un jeu d'images",
            "",
            "Sous-titres image (*.sup *.idx);;PGS (*.sup);;VobSub (*.idx);;Tous les fichiers (*)",
        )
        if not path:
            return

        progress = QProgressDialog("Chargement des sous-titres image...", None, 0, 0, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.show()

        worker = ImageSetLoadWorker(path)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_image_set_loaded)
        worker.error.connect(self._on_image_set_load_error)
        worker.finished.connect(progress.close)
        worker.error.connect(progress.close)
        worker.finished.connect(self._cleanup_load_thread)
        worker.error.connect(self._cleanup_load_thread)

        self._load_thread = thread
        self._load_worker = worker
        thread.start()

    def _cleanup_load_thread(self):
        if self._load_thread is not None:
            self._load_thread.quit()
            self._load_thread.wait()
            self._load_thread.deleteLater()
        self._load_thread = None
        self._load_worker = None

    def _on_image_set_load_error(self, message):
        QMessageBox.critical(self, "Erreur de lecture", message)

    def _on_image_set_loaded(self, reader):
        if not reader.events:
            QMessageBox.warning(self, "Aucune image", "Aucune image de sous-titre trouvée dans ce fichier.")
            return

        self.image_set_widget.load_reader(reader)
        self.controls_panel.clear_results()
        self.controls_panel.set_export_enabled(False)
        self._results = []
        self._cues = []
        self.image_mode_action.setChecked(True)
        self.set_image_mode(True)

    def _refresh_preview(self):
        widget = self.active_widget
        frame = widget.get_current_frame()
        if frame is None:
            self.filter_panel.set_preview_image(None)
            return
        rect_norm = widget.get_crop_rect_norm()
        cropped = crop_frame(frame, rect_norm)
        filtered = self.filter_panel.pipeline.apply(cropped)
        self.filter_panel.set_preview_image(filtered)

    def start_ocr(self):
        widget = self.active_widget
        if widget.reader is None:
            QMessageBox.warning(self, "Aucune source", "Ouvrez d'abord une vidéo ou un jeu d'images.")
            return
        if self._thread is not None:
            return

        self._results = []
        self._cues = []
        self.controls_panel.clear_results()
        self.controls_panel.set_export_enabled(False)
        self.controls_panel.set_running(True)
        self.controls_panel.set_status("Démarrage...")

        if self._image_mode:
            worker = ImageSetOcrWorker(
                engine_manager=self.engine_manager,
                events=widget.reader.events,
                rect_norm=widget.get_crop_rect_norm(),
                similarity_threshold=self.controls_panel.similarity_spin.value(),
                filter_steps=self.filter_panel.pipeline.steps,
                prompt=self.controls_panel.prompt_edit.text(),
                filter_chinese=self.controls_panel.filter_chinese_check.isChecked(),
                batch_size=self.controls_panel.batch_size_spin.value(),
                retry_on_empty=self.controls_panel.retry_on_empty_check.isChecked(),
                detect_italic=self.controls_panel.italic_check.isChecked(),
                italic_angle_threshold=self.controls_panel.italic_threshold_spin.value(),
                mega_batch=self.controls_panel.mega_batch_check.isChecked(),
            )
        else:
            worker = OcrWorker(
                engine_manager=self.engine_manager,
                video_path=widget.reader.path,
                rect_norm=widget.get_crop_rect_norm(),
                step=self.controls_panel.n_frames_spin.value(),
                similarity_threshold=self.controls_panel.similarity_spin.value(),
                filter_steps=self.filter_panel.pipeline.steps,
                prompt=self.controls_panel.prompt_edit.text(),
                filter_chinese=self.controls_panel.filter_chinese_check.isChecked(),
                force_periodic_check=self.controls_panel.force_periodic_check.isChecked(),
                scan_by_interval=self.controls_panel.scan_by_interval_check.isChecked(),
                batch_size=self.controls_panel.batch_size_spin.value(),
                retry_on_empty=self.controls_panel.retry_on_empty_check.isChecked(),
                detect_italic=self.controls_panel.italic_check.isChecked(),
                italic_angle_threshold=self.controls_panel.italic_threshold_spin.value(),
                mega_batch=self.controls_panel.mega_batch_check.isChecked(),
            )
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.progress.connect(self.controls_panel.set_progress)
        worker.frameResult.connect(self._on_frame_result)
        worker.status.connect(self.controls_panel.set_status)
        worker.finished.connect(self._on_run_finished)
        worker.error.connect(self._on_run_error)
        worker.memoryCalibrated.connect(self.controls_panel.set_batch_cost_estimate)

        self._thread = thread
        self._worker = worker
        thread.start()

    def stop_ocr(self):
        if self._worker is not None:
            self._worker.stop()
            self.controls_panel.set_status("Arrêt demandé...")

    def toggle_pause_ocr(self, paused):
        if self._worker is None:
            return
        if paused:
            self._worker.pause()
            self.controls_panel.set_status("En pause...")
        else:
            self._worker.resume()
            self.controls_panel.set_status("Reprise...")

    def _on_frame_result(self, analyzed):
        self._results.append(analyzed)
        self.controls_panel.add_result(analyzed)

    def _on_run_finished(self, results):
        self._results = results
        reader = self.active_widget.reader
        duration = reader.duration if reader else None
        self._cues = build_cues(
            results,
            video_duration=duration,
            min_duration=self.controls_panel.min_duration_spin.value(),
            text_similarity_threshold=self.controls_panel.text_merge_spin.value() / 100.0,
        )
        self.controls_panel.set_status(f"Terminé : {len(self._cues)} sous-titre(s) généré(s).")
        self.controls_panel.set_running(False)
        self.controls_panel.set_export_enabled(len(self._cues) > 0)
        self._cleanup_thread()

    def _on_run_error(self, message):
        QMessageBox.critical(self, "Erreur OCR", message)
        self.controls_panel.set_status(f"Erreur : {message}")
        self.controls_panel.set_running(False)
        self._cleanup_thread()

    def _cleanup_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
        self._thread = None
        self._worker = None

    def export_ass_dialog(self):
        if not self._cues:
            QMessageBox.information(self, "Rien à exporter", "Lancez d'abord l'OCR.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exporter en .ass", "subtitles.ass", "ASS (*.ass)")
        if not path:
            return
        reader = self.active_widget.reader
        write_ass(
            self._cues,
            path,
            video_width=reader.width if reader else 1920,
            video_height=reader.height if reader else 1080,
        )
        self.controls_panel.set_status(f"Exporté : {path}")

    def closeEvent(self, event):
        self.stop_ocr()
        if self._thread is not None:
            self._thread.wait(2000)
        super().closeEvent(event)
