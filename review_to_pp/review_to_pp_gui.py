"""
review_to_pp - PyQt6 GUI

Drop a review script (.txt/.json/.csv) into the window, or click Browse,
then click Convert to produce Premiere Pro XML + SRT subtitle.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit, QMessageBox,
    QGroupBox, QListWidget, QListWidgetItem,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass
try:
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# Allow running from any directory
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import review_to_pp as core


INPUT_FILTER = "Review scripts (*.txt *.json *.csv);;All files (*.*)"


class ConvertSignals(QObject):
    log = pyqtSignal(str)
    file_done = pyqtSignal(str, str, str)  # input, xml, srt
    file_failed = pyqtSignal(str, str)  # input, error
    finished = pyqtSignal(int, int)  # success_count, fail_count


class ConvertWorker(QThread):
    def __init__(self, input_paths: list[Path], output_dir: Path | None,
                 override_video: str | None, override_title: str | None):
        super().__init__()
        self.input_paths = input_paths
        self.output_dir = output_dir
        self.override_video = override_video or None
        self.override_title = override_title or None
        self.signals = ConvertSignals()

    def run(self):
        ok = 0
        fail = 0
        for path in self.input_paths:
            try:
                self.signals.log.emit(f"[변환 시작] {path.name}")
                xml_path, srt_path = core.convert(
                    path,
                    self.output_dir,
                    self.override_video,
                    self.override_title,
                )
                self.signals.file_done.emit(str(path), str(xml_path), str(srt_path))
                self.signals.log.emit(f"  ✅ XML: {xml_path}")
                self.signals.log.emit(f"  ✅ SRT: {srt_path}")
                ok += 1
            except Exception as e:
                tb = traceback.format_exc()
                self.signals.file_failed.emit(str(path), str(e))
                self.signals.log.emit(f"  ❌ {path.name}: {e}\n{tb}")
                fail += 1
        self.signals.finished.emit(ok, fail)


class DropListWidget(QListWidget):
    files_added = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(self.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths: list[str] = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                paths.append(url.toLocalFile())
        if paths:
            self.files_added.emit(paths)
            event.acceptProposedAction()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("review_to_pp - 리뷰 스크립트 → Premiere XML + SRT")
        self.resize(900, 720)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # --- Input group ---
        in_group = QGroupBox("1. 입력 파일 (.txt / .json / .csv)  -  창에 드래그해도 됩니다")
        in_layout = QVBoxLayout(in_group)

        self.file_list = DropListWidget()
        self.file_list.files_added.connect(self._add_files)
        in_layout.addWidget(self.file_list)

        in_btn_row = QHBoxLayout()
        self.add_btn = QPushButton("파일 추가...")
        self.add_btn.clicked.connect(self._browse_files)
        self.remove_btn = QPushButton("선택 제거")
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn = QPushButton("전체 비우기")
        self.clear_btn.clicked.connect(self.file_list.clear)
        in_btn_row.addWidget(self.add_btn)
        in_btn_row.addWidget(self.remove_btn)
        in_btn_row.addWidget(self.clear_btn)
        in_btn_row.addStretch()
        in_layout.addLayout(in_btn_row)

        root.addWidget(in_group)

        # --- Options group ---
        opt_group = QGroupBox("2. 옵션 (선택 사항)")
        opt_layout = QGridLayout(opt_group)

        opt_layout.addWidget(QLabel("출력 폴더:"), 0, 0)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("(비우면 입력 파일과 같은 폴더)")
        opt_layout.addWidget(self.output_edit, 0, 1)
        self.output_btn = QPushButton("폴더 선택...")
        self.output_btn.clicked.connect(self._browse_output)
        opt_layout.addWidget(self.output_btn, 0, 2)

        opt_layout.addWidget(QLabel("영상 경로 덮어쓰기:"), 1, 0)
        self.video_edit = QLineEdit()
        self.video_edit.setPlaceholderText("(비우면 입력 파일에 적힌 [영상] 경로 사용)")
        opt_layout.addWidget(self.video_edit, 1, 1)
        self.video_btn = QPushButton("영상 선택...")
        self.video_btn.clicked.connect(self._browse_video)
        opt_layout.addWidget(self.video_btn, 1, 2)

        opt_layout.addWidget(QLabel("제목 덮어쓰기:"), 2, 0)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("(비우면 입력 파일의 [제목] 사용)")
        opt_layout.addWidget(self.title_edit, 2, 1, 1, 2)

        root.addWidget(opt_group)

        # --- Action button ---
        action_row = QHBoxLayout()
        self.convert_btn = QPushButton("🚀 변환 시작")
        self.convert_btn.setMinimumHeight(40)
        f = QFont()
        f.setPointSize(11)
        f.setBold(True)
        self.convert_btn.setFont(f)
        self.convert_btn.clicked.connect(self._start_convert)
        action_row.addWidget(self.convert_btn)
        self.open_output_btn = QPushButton("결과 폴더 열기")
        self.open_output_btn.clicked.connect(self._open_output_folder)
        action_row.addWidget(self.open_output_btn)
        root.addLayout(action_row)

        # --- Log group ---
        log_group = QGroupBox("3. 로그")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        log_layout.addWidget(self.log_view)
        root.addWidget(log_group)

        self.worker: ConvertWorker | None = None
        self.last_output_dir: Path | None = None

        self._log("준비 완료. 입력 파일을 추가하고 [변환 시작] 버튼을 누르세요.")

    # ----- helpers ----- #
    def _log(self, msg: str):
        self.log_view.appendPlainText(msg)

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "리뷰 스크립트 선택", "", INPUT_FILTER
        )
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list[str]):
        added = 0
        for p in paths:
            full = str(Path(p).resolve())
            # Avoid duplicates
            existing = [self.file_list.item(i).text() for i in range(self.file_list.count())]
            if full in existing:
                continue
            QListWidgetItem(full, self.file_list)
            added += 1
        if added:
            self._log(f"파일 {added}개 추가 (총 {self.file_list.count()}개)")

    def _remove_selected(self):
        for item in self.file_list.selectedItems():
            row = self.file_list.row(item)
            self.file_list.takeItem(row)

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "출력 폴더 선택", "")
        if d:
            self.output_edit.setText(d)

    def _browse_video(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "영상 파일 선택", "",
            "Video files (*.mp4 *.mov *.mkv *.avi);;All files (*.*)"
        )
        if p:
            self.video_edit.setText(p)

    def _open_output_folder(self):
        target = self.last_output_dir
        if target is None:
            text = self.output_edit.text().strip()
            target = Path(text) if text else None
        if target and target.exists():
            os.startfile(str(target))
        else:
            QMessageBox.information(self, "안내", "아직 출력 폴더가 없습니다. 변환을 먼저 실행하세요.")

    def _start_convert(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "진행 중", "이미 변환 작업이 진행 중입니다.")
            return

        count = self.file_list.count()
        if count == 0:
            QMessageBox.warning(self, "안내", "변환할 파일을 먼저 추가하세요.")
            return

        paths = [Path(self.file_list.item(i).text()) for i in range(count)]
        output_text = self.output_edit.text().strip()
        output_dir = Path(output_text) if output_text else None
        video_text = self.video_edit.text().strip() or None
        title_text = self.title_edit.text().strip() or None

        if output_dir:
            self.last_output_dir = output_dir
        else:
            self.last_output_dir = paths[0].parent

        self.convert_btn.setEnabled(False)
        self._log(f"\n=== 변환 시작 ({count}개 파일) ===")

        self.worker = ConvertWorker(paths, output_dir, video_text, title_text)
        self.worker.signals.log.connect(self._log)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, ok: int, fail: int):
        self.convert_btn.setEnabled(True)
        self._log(f"\n=== 완료: 성공 {ok}개, 실패 {fail}개 ===")
        if fail == 0:
            QMessageBox.information(self, "완료", f"{ok}개 파일 변환 성공!")
        else:
            QMessageBox.warning(self, "완료(일부 실패)", f"성공 {ok}개 / 실패 {fail}개. 로그를 확인하세요.")


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
