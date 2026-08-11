# -*- coding: utf-8 -*-
"""V6.1 GUI 入口（PySide6）。

功能：
- 拖拽 C 源文件到窗口（或点击"选择文件"按钮）。
- 点"一键生成"：按输入文件名创建独立输出文件夹，生成全部产物
  （design.docx / design.vsdx / design.md / *.puml / *_pN.png）。
- 底部日志区实时显示每一步；产物路径可直接点击"打开所在文件夹"。

启动：python gui_main.py
"""

import os
import subprocess
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QPlainTextEdit, QFrame,
    QFileDialog, QMessageBox,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent

import pipeline


# ---------- 后台生成线程（避免阻塞界面） ----------

class GenerateWorker(QThread):
    """在子线程中跑 generate_design，通过信号回传日志与结果。"""

    log_msg = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, src_file, base_dir, export_png=True):
        super().__init__()
        self.src_file = src_file
        self.base_dir = base_dir
        self.export_png = export_png

    def run(self):
        try:
            result = pipeline.generate_design(
                self.src_file,
                base_dir=self.base_dir,
                export_png=self.export_png,
                report=self.log_msg.emit,
            )
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001  GUI 层兜底
            self.failed.emit(str(exc))


# ---------- 主窗口 ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("C 代码详细设计生成工具 — V6.1")
        self.setAcceptDrops(True)
        self.resize(720, 560)

        self.src_file = ""
        self.worker = None

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 顶部说明
        tip = QLabel(
            "把 C 源文件拖到下面，或点击「选择文件」；然后点「一键生成」。\n"
            "产物将按文件名放入独立文件夹（默认在 output/ 下）。"
        )
        tip.setWordWrap(True)
        root.addWidget(tip)

        # 文件行：拖拽区 + 选择按钮
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("拖拽 .c 文件到这里，或点右侧选择…")
        self.file_edit.setReadOnly(True)
        self.file_edit.setAcceptDrops(True)
        file_row.addWidget(self.file_edit, 1)
        self.btn_browse = QPushButton("选择文件")
        self.btn_browse.clicked.connect(self.browse_file)
        file_row.addWidget(self.btn_browse)
        root.addLayout(file_row)

        # 基目录行（可选配置）
        base_row = QHBoxLayout()
        base_row.addWidget(QLabel("输出基目录:"))
        self.base_edit = QLineEdit(os.path.abspath("output"))
        self.base_edit.setToolTip("产物子文件夹将创建在这个目录下（按文件名命名）")
        base_row.addWidget(self.base_edit, 1)
        self.btn_base = QPushButton("浏览")
        self.btn_base.clicked.connect(self.browse_base)
        base_row.addWidget(self.btn_base)
        root.addLayout(base_row)

        # 生成按钮
        self.btn_run = QPushButton("一键生成")
        self.btn_run.setMinimumHeight(40)
        self.btn_run.clicked.connect(self.run_generate)
        root.addWidget(self.btn_run)

        # 产物路径（生成成功后显示）
        self.out_label = QLabel("")
        self.out_label.setWordWrap(True)
        self.out_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.out_label)

        # 打开产物文件夹按钮（生成成功后启用）
        self.btn_open = QPushButton("打开产物文件夹")
        self.btn_open.setEnabled(False)
        self.btn_open.clicked.connect(self.open_out_dir)
        root.addWidget(self.btn_open)

        # 日志区
        log_frame = QFrame()
        log_frame.setFrameShape(QFrame.StyledPanel)
        log_lay = QVBoxLayout(log_frame)
        log_lay.setContentsMargins(8, 8, 8, 8)
        log_lay.addWidget(QLabel("日志"))
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(2000)
        log_lay.addWidget(self.log_box)
        root.addWidget(log_frame, 1)

    # ---------- 拖拽 ----------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if path and os.path.isfile(path):
            self.set_src_file(path)
            event.acceptProposedAction()

    # ---------- 按钮回调 ----------

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 C 源文件", "", "C 源文件 (*.c *.h);;所有文件 (*)")
        if path:
            self.set_src_file(path)

    def browse_base(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择输出基目录", self.base_edit.text())
        if path:
            self.base_edit.setText(path)

    def set_src_file(self, path):
        self.src_file = path
        self.file_edit.setText(path)
        self.append_log("已选择文件: %s" % path)

    # ---------- 生成 ----------

    def run_generate(self):
        if not self.src_file:
            QMessageBox.warning(self, "提示", "请先选择 C 源文件（拖拽或点击选择文件）。")
            return
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "提示", "正在生成中，请稍候…")
            return
        if not os.path.isfile(self.src_file):
            QMessageBox.warning(self, "提示", "源文件不存在:\n%s" % self.src_file)
            return

        base_dir = os.path.abspath(self.base_edit.text().strip() or "output")
        self.btn_run.setEnabled(False)
        self.btn_open.setEnabled(False)
        self.out_label.setText("")
        self.append_log("=" * 50)
        self.append_log("开始生成: %s" % self.src_file)

        self.worker = GenerateWorker(self.src_file, base_dir)
        self.worker.log_msg.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_success)
        self.worker.failed.connect(self.on_fail)
        self.worker.start()

    def on_success(self, result):
        self.btn_run.setEnabled(True)
        self.out_dir = result["out_dir"]
        lines = [
            "生成完成！",
            "目录: %s" % result["out_dir"],
            "函数: %d   结构体: %d   枚举: %d" % (
                result["functions"], result["structs"], result["enums"]),
            "Word 说明表: %s" % result["design_docx"],
        ]
        if result["design_vsdx"]:
            lines.append("Visio 流程图: %s" % result["design_vsdx"])
        else:
            lines.append("Visio 流程图: 未生成（%s）" % result["visio_error"])
        lines.append("Markdown: %s" % result["design_md"])
        self.out_label.setText("\n".join(lines))
        self.btn_open.setEnabled(True)

    def on_fail(self, msg):
        self.btn_run.setEnabled(True)
        self.append_log("生成失败: %s" % msg)
        QMessageBox.critical(self, "生成失败", msg)

    def open_out_dir(self):
        d = getattr(self, "out_dir", None)
        if d and os.path.isdir(d):
            if sys.platform == "win32":
                os.startfile(d)  # noqa: S606  Windows 打开资源管理器
            else:
                subprocess.Popen(["xdg-open", d])
        else:
            QMessageBox.warning(self, "提示", "产物目录不存在:\n%s" % (d or ""))

    # ---------- 日志 ----------

    def append_log(self, msg):
        self.log_box.appendPlainText(str(msg))
        # 滚动到底部
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
