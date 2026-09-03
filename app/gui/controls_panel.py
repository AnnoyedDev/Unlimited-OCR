from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..config import DEFAULT_OCR_PROMPT


class ControlsPanel(QWidget):
    runRequested = Signal()
    stopRequested = Signal()
    exportRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        sampling_box = QGroupBox("Échantillonnage")
        form = QFormLayout(sampling_box)

        self.similarity_spin = QDoubleSpinBox()
        self.similarity_spin.setRange(0.0, 100.0)
        self.similarity_spin.setDecimals(1)
        self.similarity_spin.setValue(99.0)
        self.similarity_spin.setSuffix(" %")
        self.similarity_spin.setToolTip(
            "Une frame est sautée (pas d'OCR) dès qu'elle ressemble à au moins ce % "
            "à la dernière frame où l'OCR a tourné. Plus le % est HAUT, plus c'est "
            "strict/prudent (barre dure à atteindre = seuls les quasi-doublons sont "
            "sautés). Plus le % est BAS, plus c'est agressif (barre facile à "
            "atteindre = beaucoup de paires, même différentes, sont sautées) -- "
            "c'est l'inverse de l'intuition habituelle. Montez-le si des textes "
            "courts (\"Hé\", \"Wouah !\") sont ratés."
        )
        form.addRow("Seuil de similarité image (skip) :", self.similarity_spin)

        self.scan_by_interval_check = QCheckBox("Vérifier le changement toutes les N frames seulement")
        self.scan_by_interval_check.setChecked(False)
        self.scan_by_interval_check.setToolTip(
            "Désactivé (recommandé) : chaque frame de la vidéo est comparée à la "
            "précédente (rapide, léger) -- garantit qu'aucun sous-titre affiché moins "
            "de N frames n'est raté.\n"
            "Activé : seule 1 frame sur N est même regardée, ce qui accélère le "
            "décodage vidéo mais peut faire rater des sous-titres affichés moins de N "
            "frames de suite."
        )
        form.addRow(self.scan_by_interval_check)

        self.force_periodic_check = QCheckBox("Vérification de sécurité périodique")
        self.force_periodic_check.setChecked(False)
        self.force_periodic_check.setToolTip(
            "Désactivé (recommandé) : l'OCR ne tourne QUE quand un changement est "
            "détecté -- aucun appel gaspillé sur des images identiques.\n"
            "Activé : force un appel OCR même sans changement détecté toutes les N "
            "frames ci-dessous, au cas où une dérive très lente ne franchirait "
            "jamais le seuil de similarité. Coûte des appels OCR en plus, y compris "
            "sur de longues zones vides."
        )
        form.addRow(self.force_periodic_check)

        self.n_frames_spin = QSpinBox()
        self.n_frames_spin.setRange(1, 10_000)
        self.n_frames_spin.setValue(5)
        self.n_frames_spin.setEnabled(False)
        self.scan_by_interval_check.toggled.connect(self._update_n_frames_enabled)
        self.force_periodic_check.toggled.connect(self._update_n_frames_enabled)
        form.addRow("  Intervalle (N frames) :", self.n_frames_spin)

        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 32)
        self.batch_size_spin.setValue(4)
        self.batch_size_spin.setToolTip(
            "Nombre d'images regroupées en un seul appel au modèle. Mesuré ~2,5x plus "
            "rapide par image en batch de 8 vs une par une sur GPU. Plus haut = plus "
            "rapide mais plus de mémoire GPU utilisée, et attendez un peu plus "
            "longtemps entre deux résultats affichés (le batch se remplit avant "
            "d'être envoyé). 1 = désactive le batching (comportement d'origine)."
        )
        form.addRow("Taille du batch OCR :", self.batch_size_spin)

        self.text_merge_spin = QDoubleSpinBox()
        self.text_merge_spin.setRange(0.0, 100.0)
        self.text_merge_spin.setDecimals(0)
        self.text_merge_spin.setValue(85.0)
        self.text_merge_spin.setSuffix(" %")
        self.text_merge_spin.setToolTip(
            "Deux résultats OCR consécutifs dont le texte se ressemble à plus de ce "
            "% (fautes/bruit OCR) sont fusionnés en un seul sous-titre au lieu d'en "
            "créer plusieurs qui scintillent."
        )
        form.addRow("Seuil de fusion des textes similaires :", self.text_merge_spin)

        self.min_duration_spin = QDoubleSpinBox()
        self.min_duration_spin.setRange(0.0, 5.0)
        self.min_duration_spin.setDecimals(2)
        self.min_duration_spin.setValue(0.0)
        self.min_duration_spin.setSuffix(" s")
        self.min_duration_spin.setToolTip(
            "Sous-titres plus courts que cette durée = ignorés (filtre anti-scintillement)."
        )
        form.addRow("Durée min. d'un sous-titre :", self.min_duration_spin)

        layout.addWidget(sampling_box)

        ocr_box = QGroupBox("OCR")
        ocr_form = QFormLayout(ocr_box)

        self.prompt_edit = QLineEdit(DEFAULT_OCR_PROMPT)
        ocr_form.addRow("Prompt :", self.prompt_edit)

        self.filter_chinese_check = QCheckBox("Écarter les blocs probablement en chinois (sans kana)")
        self.filter_chinese_check.setChecked(True)
        self.filter_chinese_check.setToolTip(
            "Heuristique : les idéogrammes CJK sont partagés entre chinois et kanji japonais. "
            "Un bloc avec des idéogrammes mais aucun kana ni lettre latine est considéré "
            "comme probablement chinois et écarté."
        )
        ocr_form.addRow(self.filter_chinese_check)

        self.retry_on_empty_check = QCheckBox("Deuxième passe si rien détecté (zoom auto)")
        self.retry_on_empty_check.setChecked(True)
        self.retry_on_empty_check.setToolTip(
            "Quand une frame signalée comme 'changée' revient vide de l'OCR, c'est "
            "souvent un texte court sur un fond chargé (photo, mur en pierre...) qui "
            "brouille le modèle, pas une vraie absence de texte. Cette option relance "
            "l'OCR sur un zoom automatique et resserré autour de la zone la plus "
            "lumineuse de l'image (le texte est presque toujours plus clair que le "
            "fond), avec un fort seuillage pour éliminer le fond chargé. Coûte un "
            "appel OCR de plus, seulement quand le premier essai est vide."
        )
        ocr_form.addRow(self.retry_on_empty_check)

        layout.addWidget(ocr_box)

        run_row = QVBoxLayout()
        self.run_button = QPushButton("Lancer l'OCR")
        self.run_button.clicked.connect(self.runRequested.emit)
        run_row.addWidget(self.run_button)

        self.stop_button = QPushButton("Arrêter")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stopRequested.emit)
        run_row.addWidget(self.stop_button)
        layout.addLayout(run_row)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel("<b>Résultats</b>"))
        self.results_list = QListWidget()
        layout.addWidget(self.results_list, stretch=1)
        self._last_text = None
        self._last_item = None
        self._last_first_ts = 0.0
        self._last_repeat_count = 1

        self.export_button = QPushButton("Exporter en .ass...")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.exportRequested.emit)
        layout.addWidget(self.export_button)

        self.device_label = QLabel("")
        self.device_label.setStyleSheet("color: #888;")
        layout.addWidget(self.device_label)

    def _update_n_frames_enabled(self):
        self.n_frames_spin.setEnabled(
            self.scan_by_interval_check.isChecked() or self.force_periodic_check.isChecked()
        )

    def set_image_mode(self, enabled):
        self.scan_by_interval_check.setEnabled(not enabled)
        self.force_periodic_check.setEnabled(not enabled)
        if enabled:
            self.n_frames_spin.setEnabled(False)
        else:
            self._update_n_frames_enabled()

    def set_running(self, running):
        self.run_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.export_button.setEnabled(not running and self.results_list.count() > 0)

    def set_progress(self, current, total):
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(current)

    def set_status(self, text):
        self.status_label.setText(text)

    def add_result(self, analyzed):
        if analyzed.text is None:
            return

        if analyzed.text == self._last_text and self._last_item is not None:
            self._last_repeat_count += 1
            base = repr(analyzed.text) if analyzed.text else "(vide)"
            self._last_item.setText(
                f"[{_fmt(self._last_first_ts)} -> {_fmt(analyzed.timestamp)}] "
                f"{base} (x{self._last_repeat_count})"
            )
            return

        label = f"[{_fmt(analyzed.timestamp)}] {analyzed.text!r}" if analyzed.text else f"[{_fmt(analyzed.timestamp)}] (vide)"
        self.results_list.addItem(label)
        self._last_text = analyzed.text
        self._last_item = self.results_list.item(self.results_list.count() - 1)
        self._last_first_ts = analyzed.timestamp
        self._last_repeat_count = 1

    def clear_results(self):
        self.results_list.clear()
        self._last_text = None
        self._last_item = None
        self._last_first_ts = 0.0
        self._last_repeat_count = 1

    def set_export_enabled(self, enabled):
        self.export_button.setEnabled(enabled)

    def set_device_text(self, text):
        self.device_label.setText(text)


def _fmt(seconds):
    seconds = max(0, seconds)
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"
