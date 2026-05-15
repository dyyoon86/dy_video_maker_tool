"""
DeepL SRT Translator — PyQt6 GUI

Drag an SRT into the window, pick languages, click Translate.
"""
import os
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QTextCursor, QDragEnterEvent, QDropEvent
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

import deepl_translate_srt as core


SRT_FILTER = "SRT subtitle (*.srt);;All files (*.*)"

SOURCE_LANGS = [
    ("Auto-detect", None),
    ("Japanese (JA)", "JA"),
    ("English (EN)", "EN"),
    ("Chinese (ZH)", "ZH"),
    ("Korean (KO)", "KO"),
    ("Spanish (ES)", "ES"),
    ("French (FR)", "FR"),
    ("German (DE)", "DE"),
    ("Italian (IT)", "IT"),
    ("Russian (RU)", "RU"),
    ("Portuguese (PT)", "PT"),
    ("Dutch (NL)", "NL"),
    ("Polish (PL)", "PL"),
]

TARGET_LANGS = [
    ("Korean (KO)", "KO"),
    ("English (EN-US)", "EN-US"),
    ("English (EN-GB)", "EN-GB"),
    ("Japanese (JA)", "JA"),
    ("Chinese (ZH)", "ZH"),
    ("Spanish (ES)", "ES"),
    ("French (FR)", "FR"),
    ("German (DE)", "DE"),
    ("Italian (IT)", "IT"),
    ("Russian (RU)", "RU"),
    ("Portuguese-BR (PT-BR)", "PT-BR"),
    ("Portuguese-PT (PT-PT)", "PT-PT"),
    ("Dutch (NL)", "NL"),
    ("Polish (PL)", "PL"),
]


class TranslateSignals(QObject):
    log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)


class TranslateWorker(QThread):
    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self.signals = TranslateSignals()
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            result = core.translate_srt(
                input_path=self.params["srt"],
                source=self.params["source"],
                target=self.params["target"],
                api_key=self.params["api_key"],
                force=self.params.get("force", True),
                batch_size=self.params.get("batch_size", 50),
                output_path=self.params.get("output_path"),
                log=lambda m: self.signals.log.emit(m),
                progress=lambda p: self.signals.progress.emit(int(p * 100)),
                cancel_check=lambda: self._cancel,
            )
            self.signals.finished.emit(result)
        except Exception as e:
            tb = traceback.format_exc()
            self.signals.failed.emit(f"{e}\n\n{tb}")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepL SRT Translator")
        self.resize(860, 680)
        self.setAcceptDrops(True)

        self.worker: TranslateWorker | None = None
        self._build_ui()
        self._load_initial_key()
        self._refresh_usage(silent=True)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Input
        in_box = QGroupBox("Input SRT (drag & drop supported)")
        in_layout = QHBoxLayout(in_box)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Drop an .srt file here or click Browse…")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._on_browse)
        in_layout.addWidget(self.path_edit, 1)
        in_layout.addWidget(browse_btn)
        root.addWidget(in_box)

        # Options
        opts_box = QGroupBox("Translation Options")
        opts = QGridLayout(opts_box)

        opts.addWidget(QLabel("Source:"), 0, 0)
        self.source_combo = QComboBox()
        for label, _ in SOURCE_LANGS:
            self.source_combo.addItem(label)
        self.source_combo.setCurrentIndex(1)  # Japanese default
        opts.addWidget(self.source_combo, 0, 1)

        opts.addWidget(QLabel("Target:"), 0, 2)
        self.target_combo = QComboBox()
        for label, _ in TARGET_LANGS:
            self.target_combo.addItem(label)
        self.target_combo.setCurrentIndex(0)  # Korean default
        opts.addWidget(self.target_combo, 0, 3)

        opts.addWidget(QLabel("Batch size:"), 1, 0)
        self.batch_combo = QComboBox()
        for n in [25, 50, 100]:
            self.batch_combo.addItem(str(n))
        self.batch_combo.setCurrentText("50")
        opts.addWidget(self.batch_combo, 1, 1)

        self.force_check = QCheckBox("Overwrite if output exists")
        self.force_check.setChecked(True)
        opts.addWidget(self.force_check, 1, 2, 1, 2)

        opts.addWidget(QLabel("Output:"), 2, 0)
        self.outpath_edit = QLineEdit()
        self.outpath_edit.setPlaceholderText("(auto: <stem>_<target>.srt next to input)")
        out_browse = QPushButton("…")
        out_browse.setMaximumWidth(30)
        out_browse.clicked.connect(self._on_outpath_browse)
        out_row = QHBoxLayout()
        out_row.addWidget(self.outpath_edit, 1)
        out_row.addWidget(out_browse)
        out_wrap = QWidget()
        out_wrap.setLayout(out_row)
        opts.addWidget(out_wrap, 2, 1, 1, 3)

        root.addWidget(opts_box)

        # API key
        key_box = QGroupBox("DeepL API")
        key_layout = QGridLayout(key_box)

        key_layout.addWidget(QLabel("Key:"), 0, 0)
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Your DeepL Auth Key (ends with :fx for Free)")
        key_layout.addWidget(self.key_edit, 0, 1, 1, 2)

        self.key_show = QCheckBox("Show")
        self.key_show.toggled.connect(self._toggle_key_visibility)
        key_layout.addWidget(self.key_show, 0, 3)

        self.save_key_btn = QPushButton("Save key")
        self.save_key_btn.clicked.connect(self._on_save_key)
        key_layout.addWidget(self.save_key_btn, 1, 1)

        self.refresh_usage_btn = QPushButton("Refresh usage")
        self.refresh_usage_btn.clicked.connect(lambda: self._refresh_usage(silent=False))
        key_layout.addWidget(self.refresh_usage_btn, 1, 2)

        self.usage_label = QLabel("Usage: (not loaded)")
        self.usage_label.setStyleSheet("color: #555;")
        key_layout.addWidget(self.usage_label, 1, 3)

        root.addWidget(key_box)

        # Action buttons
        action_row = QHBoxLayout()
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setMinimumHeight(36)
        self.translate_btn.clicked.connect(self._on_translate)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(36)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.open_out_btn = QPushButton("Open output folder")
        self.open_out_btn.setMinimumHeight(36)
        self.open_out_btn.clicked.connect(self._on_open_output)
        action_row.addWidget(self.translate_btn, 2)
        action_row.addWidget(self.cancel_btn, 1)
        action_row.addWidget(self.open_out_btn, 1)
        root.addLayout(action_row)

        # Progress
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # Log
        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.log_view.setFont(mono)
        log_layout.addWidget(self.log_view)
        root.addWidget(log_box, 1)

    # ----- drag & drop -----
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(".srt"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".srt"):
                self.path_edit.setText(path)
                self._append_log(f"[INFO] Loaded by drop: {path}")
                break

    # ----- API key handling -----
    def _load_initial_key(self):
        try:
            key = core.load_api_key(None)
            self.key_edit.setText(key)
        except RuntimeError:
            pass  # No key yet — user will enter or save it

    def _toggle_key_visibility(self, on: bool):
        mode = QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
        self.key_edit.setEchoMode(mode)

    def _on_save_key(self):
        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "Empty key", "Please enter a DeepL API key first.")
            return
        try:
            core.save_api_key(key)
            QMessageBox.information(
                self, "Saved",
                f"API key saved to:\n{core.DEFAULT_KEY_FILE}",
            )
            self._refresh_usage(silent=True)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))

    def _refresh_usage(self, silent: bool = False):
        key = self.key_edit.text().strip()
        if not key:
            if not silent:
                QMessageBox.warning(self, "No key", "Enter a DeepL API key first.")
            return
        try:
            info = core.get_usage(key)
            if info.get("valid"):
                used = info["count"]
                limit = info["limit"]
                remaining = info["remaining"]
                pct = (1 - used / limit) * 100 if limit else 0
                self.usage_label.setText(
                    f"Usage: {used:,}/{limit:,}  (Remaining: {remaining:,}, {pct:.1f}% left)"
                )
            else:
                self.usage_label.setText("Usage: not available for this account")
        except Exception as e:
            self.usage_label.setText("Usage: (error)")
            if not silent:
                QMessageBox.warning(self, "Usage fetch failed", str(e))

    # ----- file dialogs -----
    def _on_browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select SRT file", "", SRT_FILTER)
        if path:
            self.path_edit.setText(path)

    def _on_outpath_browse(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save translated SRT as", "", SRT_FILTER)
        if path:
            self.outpath_edit.setText(path)

    def _on_open_output(self):
        # Try output_path first, else folder of input
        out = self.outpath_edit.text().strip()
        if out:
            folder = str(Path(out).parent)
        else:
            inp = self.path_edit.text().strip()
            folder = str(Path(inp).parent) if inp else str(Path(__file__).parent)
        if not folder or not Path(folder).exists():
            QMessageBox.warning(self, "No folder", "Output folder does not exist yet.")
            return
        if sys.platform.startswith("win"):
            os.startfile(folder)
        elif sys.platform == "darwin":
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')

    # ----- log / state -----
    def _append_log(self, msg: str):
        self.log_view.appendPlainText(msg)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    def _set_running(self, running: bool):
        self.translate_btn.setEnabled(not running)
        self.cancel_btn.setEnabled(running)
        self.path_edit.setEnabled(not running)
        self.source_combo.setEnabled(not running)
        self.target_combo.setEnabled(not running)
        self.batch_combo.setEnabled(not running)
        self.outpath_edit.setEnabled(not running)
        self.key_edit.setEnabled(not running)
        self.save_key_btn.setEnabled(not running)
        self.refresh_usage_btn.setEnabled(not running)
        self.force_check.setEnabled(not running)

    # ----- translate flow -----
    def _on_translate(self):
        srt_path = self.path_edit.text().strip()
        if not srt_path:
            QMessageBox.warning(self, "No file", "Select an .srt file first.")
            return
        if not os.path.isfile(srt_path):
            QMessageBox.warning(self, "Missing file", f"File not found:\n{srt_path}")
            return

        key = self.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "No API key", "Enter your DeepL API key first.")
            return

        source = SOURCE_LANGS[self.source_combo.currentIndex()][1]
        target = TARGET_LANGS[self.target_combo.currentIndex()][1]

        try:
            batch_size = int(self.batch_combo.currentText())
        except ValueError:
            batch_size = 50

        params = {
            "srt": srt_path,
            "source": source,
            "target": target,
            "api_key": key,
            "force": self.force_check.isChecked(),
            "batch_size": batch_size,
            "output_path": self.outpath_edit.text().strip() or None,
        }

        self.log_view.clear()
        self.progress.setValue(0)
        self._set_running(True)

        self.worker = TranslateWorker(params)
        self.worker.signals.log.connect(self._append_log)
        self.worker.signals.progress.connect(self.progress.setValue)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self.worker.start()

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self._append_log("[INFO] Cancel requested. Finishing current batch…")
            self.worker.cancel()

    def _on_finished(self, result: dict):
        self._set_running(False)
        if result.get("cancelled"):
            self.progress.setValue(0)
            QMessageBox.information(self, "Cancelled", "Translation was cancelled.")
            self._refresh_usage(silent=True)
            return
        if result.get("skipped"):
            QMessageBox.information(
                self, "Skipped",
                "Output already exists. Enable 'Overwrite' and try again.",
            )
            return
        self.progress.setValue(100)
        out = result.get("output", "")
        msg = (
            f"Translation complete.\n\n"
            f"Total blocks : {result.get('total', '-')}\n"
            f"Unique texts : {result.get('unique', '-')}\n"
            f"Failed blocks: {result.get('failed', 0)}\n\n"
            f"Output:\n{out}"
        )
        QMessageBox.information(self, "Done", msg)
        self._refresh_usage(silent=True)

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
