# ป๊อปอัพ "View Save Result" — แสดงรายชื่อ Save ทั้งหมด, เปิด/ลบ/เปิดโฟลเดอร์

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QComboBox, QPushButton, QMessageBox, QAbstractItemView)
from PyQt6.QtCore import Qt, pyqtSignal

from core import save_manager


class ViewSaveDialog(QDialog):
    """
    รายชื่อ Save ในระบบ พร้อม:
    - Dropdown กรองตามประเภทโหมดวัด (All / Single / Sweep / List)
    - Open Save    : ส่ง signal open_save_requested(path) กลับไปให้ AppController โหลดข้อมูล
    - Open Folder  : เปิดโฟลเดอร์ที่เก็บไฟล์ Save ทั้งหมดด้วย File Explorer ของเครื่อง
    - Close        : ปิดหน้าต่างนี้
    - DELETE Save  : ลบไฟล์ Save ที่เลือก (มีป๊อปอัพยืนยันก่อนลบเสมอ)
    """
    open_save_requested = pyqtSignal(str)  # ส่ง path ของไฟล์ save ที่ต้องการเปิด

    FILTER_OPTIONS = [
        ("All (โหมดทั้งหมด)", "ALL"),
        ("Single (โหมดวัดจุดเดียว)", "SINGLE"),
        ("Sweep (โหมดสแกนความถี่)", "SWEEP"),
        ("List (โหมดรายการความถี่)", "LIST"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("View Save Result")
        self.resize(760, 460)

        self._rows_data = []  # เก็บข้อมูล save ปัจจุบันที่แสดงอยู่ (sync กับแถวในตาราง)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- หัวข้อ + Dropdown กรอง ---
        h_top = QHBoxLayout()
        lbl_title = QLabel("Saved Results List")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        h_top.addWidget(lbl_title)
        h_top.addStretch()

        self.combo_filter = QComboBox()
        for label, _ in self.FILTER_OPTIONS:
            self.combo_filter.addItem(label)
        self.combo_filter.setMinimumWidth(220)
        self.combo_filter.currentIndexChanged.connect(self.reload_saves)
        h_top.addWidget(self.combo_filter)
        layout.addLayout(h_top)

        # --- ตารางรายชื่อ Save ---
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Date", "Save Name", "Measurement Type"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.doubleClicked.connect(self._on_open_save)
        layout.addWidget(self.table, stretch=1)

        # --- แถวปุ่มด้านล่าง ---
        h_buttons = QHBoxLayout()

        self.btn_open_save = QPushButton("Open Save")
        self.btn_open_save.setStyleSheet(self._style("#22c55e", "#16a34a"))
        self.btn_open_save.clicked.connect(self._on_open_save)

        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.setStyleSheet(self._style("#3b82f6", "#2563eb"))
        self.btn_open_folder.clicked.connect(self._on_open_folder)

        self.btn_close = QPushButton("Close")
        self.btn_close.setStyleSheet(self._style("#3b82f6", "#2563eb"))
        self.btn_close.clicked.connect(self.reject)

        self.btn_delete = QPushButton("DELETE Save")
        self.btn_delete.setStyleSheet(self._style("#ef4444", "#dc2626"))
        self.btn_delete.clicked.connect(self._on_delete_save)

        for b in (self.btn_open_save, self.btn_open_folder, self.btn_close, self.btn_delete):
            b.setMinimumHeight(36)

        h_buttons.addWidget(self.btn_open_save)
        h_buttons.addWidget(self.btn_open_folder)
        h_buttons.addStretch()
        h_buttons.addWidget(self.btn_close)
        h_buttons.addWidget(self.btn_delete)
        layout.addLayout(h_buttons)

        self.reload_saves()

    @staticmethod
    def _style(color, hover_color):
        return (
            f"QPushButton {{ background-color: {color}; color: white; border-radius: 6px; "
            f"font-weight: bold; padding: 6px 16px; border: 1px solid {hover_color}; }}"
            f"QPushButton:hover {{ background-color: {hover_color}; }}"
        )

    def _current_filter_value(self) -> str:
        idx = self.combo_filter.currentIndex()
        return self.FILTER_OPTIONS[idx][1]

    def reload_saves(self):
        """โหลดรายชื่อ Save ใหม่ตามตัวกรองปัจจุบัน และแสดงในตาราง"""
        run_mode_filter = self._current_filter_value()
        self._rows_data = save_manager.list_saves(run_mode_filter)

        self.table.setRowCount(0)
        for item in self._rows_data:
            row = self.table.rowCount()
            self.table.insertRow(row)

            date_item = QTableWidgetItem(item["measurement_time"] or "-")
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, date_item)

            name_item = QTableWidgetItem(item["save_name"])
            self.table.setItem(row, 1, name_item)

            type_label = save_manager.RUN_MODE_LABELS.get(item["run_mode"], item["run_mode"])
            type_item = QTableWidgetItem(type_label)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, type_item)

        if self._rows_data:
            self.table.selectRow(0)

    def _selected_save(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._rows_data):
            return None
        return self._rows_data[row]

    def _on_open_save(self):
        item = self._selected_save()
        if item is None:
            QMessageBox.information(self, "No Save Selected", "กรุณาเลือกรายการ Save ที่ต้องการเปิดก่อน")
            return
        self.open_save_requested.emit(item["path"])
        self.accept()

    def _on_open_folder(self):
        save_manager.open_folder_in_explorer()

    def _on_delete_save(self):
        item = self._selected_save()
        if item is None:
            QMessageBox.information(self, "No Save Selected", "กรุณาเลือกรายการ Save ที่ต้องการลบก่อน")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete Save",
            f"คุณต้องการลบ Save นี้จริงหรือไม่ \"{item['save_name']}\"? \nการลบไม่สามารถกู้คืนได้",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        save_manager.delete_save(item["path"])
        self.reload_saves()