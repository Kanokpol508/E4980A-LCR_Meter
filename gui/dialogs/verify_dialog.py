# เป็นหน้าต่าง Popup (Dialog) ที่จะเด้งขึ้นมาโชว์ตาราง "ค่าที่ส่งไป" เทียบกับ "ค่าที่เครื่องอ่านได้" พร้อมแสดงสถานะ ✅ PASS / ❌ FAIL


from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QTableWidget, 
                             QTableWidgetItem, QPushButton, QHBoxLayout, QLabel)
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt

class VerifyDialog(QDialog):
    def __init__(self, results, error_msg="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Verification Report")
        self.resize(600, 450)
        self.results = results
        self.error_msg = error_msg
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # หัวข้อ
        lbl_title = QLabel("Hardware Verification Results")
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        lbl_title.setFont(font)
        layout.addWidget(lbl_title)

        # แสดง Error Queue (ถ้ามี)
        if self.error_msg:
            lbl_error = QLabel(f"⚠️ {self.error_msg}")
            lbl_error.setStyleSheet("color: #d32f2f; font-weight: bold; background-color: #ffebee; padding: 6px; border-radius: 4px; border: 1px solid #ffcdd2;")
            layout.addWidget(lbl_error)

        # สร้างตาราง
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["พารามิเตอร์", "ค่าที่โปรแกรมส่งไป (Expected)", "ค่าที่เครื่องตอบกลับ (Actual)", "สถานะ"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)             # ห้ามแก้ไข
        
        self.populate_table()
        layout.addWidget(self.table)

        # ปุ่มปิด
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def populate_table(self):
        self.table.setRowCount(len(self.results))
        for row, item in enumerate(self.results):
            param = item.get("param", "")
            expected = str(item.get("expected", ""))
            actual = str(item.get("actual", ""))
            passed = item.get("passed", False)

            item_param = QTableWidgetItem(param)
            item_exp = QTableWidgetItem(expected)
            item_act = QTableWidgetItem(actual)
            
            status_text = "✅ PASS" if passed else "❌ FAIL"
            item_status = QTableWidgetItem(status_text)
            
            if passed:
                item_status.setForeground(QColor("green"))
            else:
                item_status.setForeground(QColor("red"))

            self.table.setItem(row, 0, item_param)
            self.table.setItem(row, 1, item_exp)
            self.table.setItem(row, 2, item_act)
            self.table.setItem(row, 3, item_status)

        self.table.resizeColumnsToContents()