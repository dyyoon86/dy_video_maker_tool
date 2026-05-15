import os
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QComboBox, QCheckBox,
    QProgressBar, QPlainTextEdit, QMessageBox, QGroupBox,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

import transcribe as core


MEDIA_FILTER = (
    "Media files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.mp3 *.wav *.m4a *.aac *.flac *.ogg);;"
    "All files (*.*)"
)

MODELS = ["tiny", "base", "small", "medium", "large-v3"]
LANGUAGES = [
    ("auto-detect", None),
    ("Korean (ko)", "ko"),
    ("English (en)", "en"),
    ("Japanese (ja)", "ja"),
    ("Chinese (zh)", "zh"),
    ("Spanish (es)", "es"),
    ("French (fr)", "fr"),
    ("German (de)", "de"),
]


class TranscribeSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)


class TranscribeWorker(QThread):
    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self.signals = TranscribeSignals()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = core.transcribe(
                media_path=self.params["media"],
                model_size=self.params["model"],
                language=self.params["language"],
                output_formats=self.params["formats"],
                output_dir=self.params.get("output_dir"),
                force=self.params.get("force", True),
                log=lambda msg: self.signals.log.emit(msg),
                progress=lambda pct: self.signals.progress.emit(int(pct * 100)),
                cancel_check=lambda: self._cancel,
            )
            self.signals.finished.emit(result)
        except Exception as e:
            tb = traceback.format_exc()
            self.signals.failed.emit(f"{e}\n\n{tb}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Transcriber — Subtitle Generator")
        self.resize(820, 640)

        self.worker: TranscribeWorker | None = None
        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        file_box = QGroupBox("Input")
        file_layout = QHBoxLayout(file_box)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Select a video or audio file…")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        file_layout.addWidget(self.path_edit, 1)
        file_layout.addWidget(browse_btn)
        root.addWidget(file_box)

        opts_box = QGroupBox("Options")
        opts = QGridLayout(opts_box)

        opts.addWidget(QLabel("Model:"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(MODELS)
        self.model_combo.setCurrentText("large-v3")
        opts.addWidget(self.model_combo, 0, 1)

        opts.addWidget(QLabel("Language:"), 0, 2)
        self.lang_combo = QComboBox()
        for label, _ in LANGUAGES:
            self.lang_combo.addItem(label)
        self.lang_combo.setCurrentIndex(0)
        opts.addWidget(self.lang_combo, 0, 3)

        opts.addWidget(QLabel("Output:"), 1, 0)
        self.cb_srt = QCheckBox(".srt")
        self.cb_srt.setChecked(True)
        self.cb_txt = QCheckBox(".txt (plain)")
        self.cb_ts = QCheckBox(".timestamped.txt")
        out_row = QHBoxLayout()
        out_row.addWidget(self.cb_srt)
        out_row.addWidget(self.cb_txt)
        out_row.addWidget(self.cb_ts)
        out_row.addStretch(1)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        opts.addWidget(out_wrap, 1, 1, 1, 3)

        opts.addWidget(QLabel("Output dir:"), 2, 0)
        default_out = str(Path(__file__).parent / "output")
        self.outdir_edit = QLineEdit(default_out)
        out_browse = QPushButton("…")
        out_browse.setMaximumWidth(30)
        out_browse.clicked.connect(self._on_outdir_browse)
        out_dir_row = QHBoxLayout()
        out_dir_row.addWidget(self.outdir_edit, 1)
        out_dir_row.addWidget(out_browse)
        out_dir_wrap = QWidget()
        out_dir_wrap.setLayout(out_dir_row)
        opts.addWidget(out_dir_wrap, 2, 1, 1, 3)

        root.addWidget(opts_box)

        action_row = QHBoxLayout()
        self.start_btn = QPushButton("Generate subtitles")
        self.start_btn.setMinimumHeight(36)
        self.start_btn.clicked.connect(self._on_start)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.open_out_btn = QPushButton("Open output folder")
        self.open_out_btn.setMinimumHeight(36)
        self.open_out_btn.clicked.connect(self._on_open_output)
        action_row.addWidget(self.start_btn, 2)
        action_row.addWidget(self.cancel_btn, 1)
        action_row.addWidget(self.open_out_btn, 1)
        root.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.log_view.setFont(mono)
        log_layout.addWidget(self.log_view)
        root.addWidget(log_box, 1)

    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select media file", "", MEDIA_FILTER)
        if path:
            self.path_edit.setText(path)

    def _on_outdir_browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select output folder", self.outdir_edit.text() or "")
        if path:
            self.outdir_edit.setText(path)

    def _on_open_output(self):
        out = self.outdir_edit.text().strip() or str(Path(__file__).parent / "output")
        Path(out).mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(out)
        elif sys.platform == "darwin":
            os.system(f'open "{out}"')
        else:
            os.system(f'xdg-open "{out}"')

    def _append_log(self, msg: str):
        self.log_view.appendPlainText(msg)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.path_edit.setEnabled(not running)
        self.model_combo.setEnabled(not running)
        self.lang_combo.setEnabled(not running)
        self.cb_srt.setEnabled(not running)
        self.cb_txt.setEnabled(not running)
        self.cb_ts.setEnabled(not running)
        self.outdir_edit.setEnabled(not running)

    def _on_start(self):
        media = self.path_edit.text().strip()
        if not media:
            QMessageBox.warning(self, "No file", "Please select a video or audio file first.")
            return
        if not os.path.isfile(media):
            QMessageBox.warning(self, "File not found", f"File does not exist:\n{media}")
            return

        formats: list[str] = []
        if self.cb_srt.isChecked():
            formats.append("srt")
        if self.cb_txt.isChecked():
            formats.append("txt")
        if self.cb_ts.isChecked():
            formats.append("timestamped")
        if not formats:
            QMessageBox.warning(self, "No output format", "Select at least one output format.")
            return

        lang_idx = self.lang_combo.currentIndex()
        language = LANGUAGES[lang_idx][1]

        params = {
            "media": media,
            "model": self.model_combo.currentText(),
            "language": language,
            "formats": formats,
            "output_dir": self.outdir_edit.text().strip() or None,
            "force": True,
        }

        self.log_view.clear()
        self.progress.setValue(0)
        self._set_running(True)

        self.worker = TranscribeWorker(params)
        self.worker.signals.log.connect(self._append_log)
        self.worker.signals.progress.connect(self.progress.setValue)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self.worker.start()

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self._append_log("[INFO] Cancel requested. Stopping after current segment…")
            self.worker.cancel()

    def _on_finished(self, result: dict):
        self._set_running(False)
        if result.get("cancelled"):
            self.progress.setValue(0)
            QMessageBox.information(self, "Cancelled", "Transcription was cancelled.")
            return
        if result.get("skipped"):
            QMessageBox.information(
                self, "Already exists",
                "Output already exists. Re-running is forced from GUI; if you saw this, please re-run.",
            )
            return
        self.progress.setValue(100)
        outputs = "\n".join(result.get("outputs", []))
        QMessageBox.information(
            self, "Done",
            f"Transcription complete.\n\nLanguage: {result.get('language')}\n"
            f"Duration: {result.get('duration', 0):.1f}s\n"
            f"Device: {result.get('device')}\n"
            f"Elapsed: {result.get('elapsed', 0):.1f}s\n\n"
            f"Outputs:\n{outputs}",
        )

    def _on_failed(self, message: str):
        self._set_running(False)
        self._append_log(f"[ERROR] {message}")
        QMessageBox.critical(self, "Failed", message)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
