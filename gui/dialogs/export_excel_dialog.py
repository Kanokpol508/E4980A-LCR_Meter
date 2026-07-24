# ป๊อปอัพ "Export Excel" — เลือก Save -> (ตัวเลือก) กรอก Record details -> ตั้งค่าไฟล์ Export
# 3 หน้าใน QStackedWidget เดียว ตามลำดับ flow ในภาพตัวอย่างที่ผู้ใช้ส่งมา

import os
from pathlib import Path

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget,
                             QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
                             QPushButton, QMessageBox, QAbstractItemView, QWidget,
                             QLineEdit, QTextEdit, QFileDialog)
from PyQt6.QtCore import Qt, QStandardPaths
from utils.helpers import NoScrollComboBox

from core import save_manager


def _btn_style(color, hover_color):
    return (
        f"QPushButton {{ background-color: {color}; color: white; border-radius: 6px; "
        f"font-weight: bold; padding: 6px 16px; border: 1px solid {hover_color}; }}"
        f"QPushButton:hover {{ background-color: {hover_color}; }}"
    )


class ExportExcelDialog(QDialog):
    """
    Flow:
      Page 0 (เลือก Save) -> [Add Record details ไม่ติ๊ก] -> Page 2 (ตั้งค่าไฟล์ Export)
                           -> [Add Record details ติ๊ก]    -> Page 1 (กรอก Model/Serial/Description) -> Page 2

    ผลลัพธ์สุดท้ายอ่านได้จาก property หลัง exec() == Accepted:
        selected_saves    : list ของ dict {'path','save_name',...} (จาก save_manager.list_saves)
        record_details    : dict หรือ None
        output_path        : Path ไฟล์ .xlsx ปลายทาง
        include_stats       : bool
        include_raw          : bool
    """

    FILTER_OPTIONS = [
        ("Single (โหมดวัดจุดเดียว)", "SINGLE"),
        ("Sweep (โหมดสแกนความถี่)", "SWEEP"),
        ("List (โหมดรายการความถี่)", "LIST"),
    ]

    def __init__(self, parent=None, default_run_mode: str = "SINGLE"):
        super().__init__(parent)
        self.setWindowTitle("Export Excel")
        self.resize(760, 560)

        self.selected_saves = []
        self.record_details = None
        self.output_path = None
        self.include_stats = True
        self.include_raw = True

        self._rows_data = []
        self._checked_paths = set()

        self.stack = QStackedWidget()
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.stack)

        self._build_page_select_save(default_run_mode)
        self._build_page_record_details()
        self._build_page_export_settings()

        self.stack.setCurrentIndex(0)

    # ======================================================
    # Page 0 — เลือก Save ที่ต้องการ Export
    # ======================================================
    def _build_page_select_save(self, default_run_mode):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        h_top = QHBoxLayout()
        lbl_title = QLabel("เลือก Save ที่ต้องการ Export")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        h_top.addWidget(lbl_title)
        h_top.addStretch()

        self.combo_filter = NoScrollComboBox()
        for label, _ in self.FILTER_OPTIONS:
            self.combo_filter.addItem(label)
        self.combo_filter.setMinimumWidth(220)
        default_idx = next((i for i, (_, v) in enumerate(self.FILTER_OPTIONS) if v == default_run_mode), 0)
        self.combo_filter.setCurrentIndex(default_idx)
        self.combo_filter.currentIndexChanged.connect(self._reload_saves)
        h_top.addWidget(self.combo_filter)
        layout.addLayout(h_top)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "Date", "Save Name", "Measurement Type"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, stretch=1)

        h_buttons = QHBoxLayout()
        self.btn_next_1 = QPushButton("Next")
        self.btn_next_1.setStyleSheet(_btn_style("#22c55e", "#16a34a"))
        self.btn_next_1.setMinimumHeight(36)
        self.btn_next_1.clicked.connect(self._on_page0_next)

        self.chk_add_record = QCheckBox("Add Record details")

        self.btn_close = QPushButton("Close")
        self.btn_close.setStyleSheet(_btn_style("#3b82f6", "#2563eb"))
        self.btn_close.setMinimumHeight(36)
        self.btn_close.clicked.connect(self.reject)

        h_buttons.addWidget(self.btn_next_1)
        h_buttons.addWidget(self.chk_add_record)
        h_buttons.addStretch()
        h_buttons.addWidget(self.btn_close)
        layout.addLayout(h_buttons)

        self.stack.addWidget(page)
        self._reload_saves()

    def _current_filter_value(self) -> str:
        idx = self.combo_filter.currentIndex()
        return self.FILTER_OPTIONS[idx][1]

    def _is_multi_select_mode(self) -> bool:
        # ตามที่ผู้ใช้ระบุ: โหมด Single เลือกได้หลาย Save ต่อครั้ง, Sweep/List เลือกได้ทีละ 1 Save
        return self._current_filter_value() == "SINGLE"

    def _reload_saves(self):
        run_mode_filter = self._current_filter_value()
        self._rows_data = save_manager.list_saves(run_mode_filter)
        self._checked_paths.clear()

        if self._is_multi_select_mode():
            self.lbl_hint.setText("โหมด Single — เลือก Save ที่ต้องการ Export ได้หลาย Save ต่อครั้ง")
        else:
            self.lbl_hint.setText("โหมด Sweep และ List — เลือก Save ที่ต้องการ Export ได้แค่ Save เดียวต่อครั้ง")

        self.table.setRowCount(0)
        for item in self._rows_data:
            row = self.table.rowCount()
            self.table.insertRow(row)

            chk = QCheckBox()
            chk.stateChanged.connect(lambda state, r=row: self._on_check_changed(r))
            cell_widget = QWidget()
            h = QHBoxLayout(cell_widget)
            h.addWidget(chk)
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 0, cell_widget)

            date_item = QTableWidgetItem(item["measurement_time"] or "-")
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 1, date_item)

            self.table.setItem(row, 2, QTableWidgetItem(item["save_name"]))

            type_label = save_manager.RUN_MODE_LABELS.get(item["run_mode"], item["run_mode"])
            type_item = QTableWidgetItem(type_label)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 3, type_item)

    def _row_checkbox(self, row: int) -> QCheckBox:
        return self.table.cellWidget(row, 0).findChild(QCheckBox)

    def _on_check_changed(self, row: int):
        chk = self._row_checkbox(row)
        path = self._rows_data[row]["path"]

        if chk.isChecked():
            # Sweep/List: เลือกได้ทีละ Save เดียว -> ยกเลิกตัวที่เคยติ๊กไว้ก่อนหน้าอัตโนมัติ
            if not self._is_multi_select_mode():
                for other_row in range(self.table.rowCount()):
                    if other_row == row:
                        continue
                    other_chk = self._row_checkbox(other_row)
                    if other_chk.isChecked():
                        other_chk.blockSignals(True)
                        other_chk.setChecked(False)
                        other_chk.blockSignals(False)
                self._checked_paths = {path}
            else:
                self._checked_paths.add(path)
        else:
            self._checked_paths.discard(path)

    def _on_page0_next(self):
        if not self._checked_paths:
            QMessageBox.information(self, "No Save Selected", "กรุณาเลือก Save ที่ต้องการ Export ก่อนอย่างน้อย 1 รายการ")
            return

        self.selected_saves = [row for row in self._rows_data if row["path"] in self._checked_paths]

        if self.chk_add_record.isChecked():
            self.stack.setCurrentIndex(1)
        else:
            self.record_details = None
            self._refresh_export_summary()
            self.stack.setCurrentIndex(2)

    # ======================================================
    # Page 1 — Add Record details (Model / Serial No. / Description)
    # ======================================================
    def _build_page_record_details(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        layout.addWidget(self._section_label("Model"))
        self.input_model = QLineEdit()
        self.input_model.setPlaceholderText("จะกรอกชื่อ Model หรือไม่กรอกก็ได้")
        self.input_model.setMinimumHeight(34)
        layout.addWidget(self.input_model)

        layout.addWidget(self._section_label("Serial No."))
        self.input_serial = QLineEdit()
        self.input_serial.setPlaceholderText("จะกรอก Serial No. หรือไม่กรอกก็ได้")
        self.input_serial.setMinimumHeight(34)
        layout.addWidget(self.input_serial)

        layout.addWidget(self._section_label("Description"))
        self.input_description = QTextEdit()
        self.input_description.setPlaceholderText("จะกรอก Description หรือไม่กรอกก็ได้")
        layout.addWidget(self.input_description, stretch=1)

        h_buttons = QHBoxLayout()
        self.btn_next_2 = QPushButton("Next")
        self.btn_next_2.setStyleSheet(_btn_style("#22c55e", "#16a34a"))
        self.btn_next_2.setMinimumHeight(36)
        self.btn_next_2.clicked.connect(self._on_page1_next)

        self.btn_back_2 = QPushButton("Back")
        self.btn_back_2.setStyleSheet(_btn_style("#3b82f6", "#2563eb"))
        self.btn_back_2.setMinimumHeight(36)
        self.btn_back_2.clicked.connect(lambda: self.stack.setCurrentIndex(0))

        self.btn_cancel_2 = QPushButton("Cancel")
        self.btn_cancel_2.setStyleSheet(_btn_style("#ef4444", "#dc2626"))
        self.btn_cancel_2.setMinimumHeight(36)
        self.btn_cancel_2.clicked.connect(self.reject)

        h_buttons.addWidget(self.btn_next_2)
        h_buttons.addStretch()
        h_buttons.addWidget(self.btn_back_2)
        h_buttons.addWidget(self.btn_cancel_2)
        layout.addLayout(h_buttons)

        self.stack.addWidget(page)

    @staticmethod
    def _section_label(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold;")
        return lbl

    def _on_page1_next(self):
        self.record_details = {
            "model": self.input_model.text().strip(),
            "serial_no": self.input_serial.text().strip(),
            "description": self.input_description.toPlainText().strip(),
        }
        self._refresh_export_summary()
        self.stack.setCurrentIndex(2)

    # ======================================================
    # Page 2 — File Name / Location / Select Type of Table Export
    # ======================================================
    def _build_page_export_settings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        layout.addWidget(self._section_label("File Name"))
        self.input_filename = QLineEdit()
        self.input_filename.setPlaceholderText("กรุณาตั้งชื่อไฟล์ Excel ที่คุณกำลังจะ Export")
        self.input_filename.setMinimumHeight(34)
        layout.addWidget(self.input_filename)

        layout.addWidget(self._section_label("Select Location Export"))
        h_location = QHBoxLayout()
        self.input_location = QLineEdit()
        default_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
        self.input_location.setText(default_dir or str(Path.home()))
        self.input_location.setMinimumHeight(34)
        self.input_location.setReadOnly(True)  # แก้ไขได้ผ่านปุ่ม Browse เท่านั้น ป้องกันพิมพ์ path ผิด
        self.input_location.setStyleSheet("background-color: #1e293b; color: #cbd5e1;")
        self.btn_browse = QPushButton("📁 Browse")
        self.btn_browse.setMinimumHeight(34)
        self.btn_browse.clicked.connect(self._on_browse_location)
        h_location.addWidget(self.input_location, stretch=1)
        h_location.addWidget(self.btn_browse)
        layout.addLayout(h_location)

        layout.addWidget(self._section_label("Select Type of Table Export :"))
        self.chk_stats_table = QCheckBox("Statistics Table")
        self.chk_stats_table.setChecked(True)
        self.chk_raw_table = QCheckBox("Raw Data Table")
        self.chk_raw_table.setChecked(True)
        layout.addWidget(self.chk_stats_table)
        layout.addWidget(self.chk_raw_table)

        layout.addStretch()

        h_buttons = QHBoxLayout()
        self.btn_export = QPushButton("Export Excel")
        self.btn_export.setStyleSheet(_btn_style("#22c55e", "#16a34a"))
        self.btn_export.setMinimumHeight(36)
        self.btn_export.clicked.connect(self._on_export_clicked)

        self.btn_back_3 = QPushButton("Back")
        self.btn_back_3.setStyleSheet(_btn_style("#3b82f6", "#2563eb"))
        self.btn_back_3.setMinimumHeight(36)
        self.btn_back_3.clicked.connect(self._on_page2_back)

        self.btn_cancel_3 = QPushButton("Cancel")
        self.btn_cancel_3.setStyleSheet(_btn_style("#ef4444", "#dc2626"))
        self.btn_cancel_3.setMinimumHeight(36)
        self.btn_cancel_3.clicked.connect(self.reject)

        h_buttons.addWidget(self.btn_export)
        h_buttons.addStretch()
        h_buttons.addWidget(self.btn_back_3)
        h_buttons.addWidget(self.btn_cancel_3)
        layout.addLayout(h_buttons)

        self.stack.addWidget(page)

    def _refresh_export_summary(self):
        if len(self.selected_saves) == 1:
            self.input_filename.setText(self.selected_saves[0]["save_name"])

    def _on_page2_back(self):
        self.stack.setCurrentIndex(1 if self.chk_add_record.isChecked() else 0)

    def _on_browse_location(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Location Export", self.input_location.text())
        if folder:
            self.input_location.setText(folder)

    def _on_export_clicked(self):
        filename = self.input_filename.text().strip()
        if not filename:
            QMessageBox.warning(self, "File Name Required", "กรุณาตั้งชื่อไฟล์ Excel ที่ต้องการ Export ก่อน")
            return

        location = self.input_location.text().strip()
        if not location or not os.path.isdir(location):
            QMessageBox.warning(self, "Invalid Location", "กรุณาเลือก Location ที่ถูกต้องสำหรับ Export")
            return

        if not self.chk_stats_table.isChecked() and not self.chk_raw_table.isChecked():
            QMessageBox.warning(self, "No Table Selected", "กรุณาเลือกอย่างน้อย 1 ตาราง (Statistics Table หรือ Raw Data Table)")
            return

        if not filename.lower().endswith(".xlsx"):
            filename += ".xlsx"

        self.output_path = Path(location) / filename
        self.include_stats = self.chk_stats_table.isChecked()
        self.include_raw = self.chk_raw_table.isChecked()

        if self.output_path.exists():
            reply = QMessageBox.question(
                self, "ไฟล์มีอยู่แล้ว",
                f"มีไฟล์ชื่อ \"{filename}\" อยู่แล้วที่ตำแหน่งนี้ ต้องการเขียนทับหรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.accept()