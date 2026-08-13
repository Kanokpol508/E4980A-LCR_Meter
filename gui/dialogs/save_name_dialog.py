# ป๊อปอัพตั้งชื่อ Save เมื่อกดปุ่ม "Save Result"

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QMessageBox)
from PyQt6.QtCore import Qt


class SaveNameDialog(QDialog):
    """
    ป๊อปอัพให้ผู้ใช้ตั้งชื่อ Save ก่อนบันทึกผลลัพธ์
    - "New Save" (เขียว) : ยืนยันบันทึก (ต้องกรอกชื่อก่อน)
    - "Cancel" (แดง)     : ยกเลิก ไม่บันทึก
    """
    def __init__(self, parent=None, default_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Save Result")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl_title = QLabel("ตั้งชื่อ Save ที่ต้องการ")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(lbl_title)

        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("กรอกชื่อ Save ที่ต้องการ")
        self.input_name.setText(default_name)
        self.input_name.setMinimumHeight(36)
        self.input_name.returnPressed.connect(self._on_confirm)
        layout.addWidget(self.input_name)

        h_buttons = QHBoxLayout()
        self.btn_new_save = QPushButton("New Save")
        self.btn_new_save.setObjectName("btnNewSave")
        self.btn_new_save.setMinimumHeight(36)
        self.btn_new_save.setStyleSheet(
            "QPushButton { background-color: #7BC99A; color: white; border-radius: 6px; "
            "font-weight: bold; padding: 6px 18px; border: 1px solid #5FAE81; }"
            "QPushButton:hover { background-color: #5FAE81; }"
        )
        self.btn_new_save.clicked.connect(self._on_confirm)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btnCancelSave")
        self.btn_cancel.setMinimumHeight(36)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #F2908C; color: white; border-radius: 6px; "
            "font-weight: bold; padding: 6px 18px; border: 1px solid #E2726D; }"
            "QPushButton:hover { background-color: #E2726D; }"
        )
        self.btn_cancel.clicked.connect(self.reject)

        h_buttons.addWidget(self.btn_new_save)
        h_buttons.addStretch()
        h_buttons.addWidget(self.btn_cancel)
        layout.addLayout(h_buttons)

        self.input_name.setFocus()

    def _on_confirm(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Name Required", "กรุณากรอกชื่อ Save ที่ต้องการก่อนบันทึก")
            self.input_name.setFocus()
            return
        self.accept()

    def get_name(self) -> str:
        return self.input_name.text().strip()