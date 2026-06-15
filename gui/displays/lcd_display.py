# วาดหน้าจอดำๆ แสดงตัวเลข Primary/Secondary

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt

class LcdDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        group_lcd = QGroupBox("ผลการวัด (Measurement Result)")
        group_lcd.setMinimumHeight(160)
        h_lcd = QHBoxLayout()
        
        self.lbl_pri_val = QLabel("---")
        self.lbl_pri_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pri_val.setStyleSheet("font-size: 32px; font-weight: bold;")
        self.lbl_pri_val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.lbl_sec_val = QLabel("---")
        self.lbl_sec_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sec_val.setStyleSheet("font-size: 32px; font-weight: bold;")
        self.lbl_sec_val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        v_pri = QVBoxLayout()
        v_pri.addWidget(QLabel("พารามิเตอร์หลัก (Primary)"))
        v_pri.addWidget(self.lbl_pri_val, stretch=1)
        
        v_sec = QVBoxLayout()
        v_sec.addWidget(QLabel("พารามิเตอร์รอง (Secondary)"))
        v_sec.addWidget(self.lbl_sec_val, stretch=1)
        
        h_lcd.addLayout(v_pri)
        h_lcd.addLayout(v_sec)
        group_lcd.setLayout(h_lcd)
        
        layout.addWidget(group_lcd, stretch=1)

        v_tools = QVBoxLayout()
        v_tools.setContentsMargins(10, 10, 0, 0)
        
        self.btn_save = QPushButton("Save Result")
        self.btn_view = QPushButton("View Save Result")
        self.btn_verify = QPushButton("Verify & Apply")
        
        self.btn_save.setMinimumSize(180, 45)
        self.btn_view.setMinimumSize(180, 45)
        self.btn_verify.setMinimumSize(180, 45)
        
        v_tools.addWidget(self.btn_save)
        v_tools.addWidget(self.btn_view)
        v_tools.addWidget(self.btn_verify)
        v_tools.addStretch(1)
        
        layout.addLayout(v_tools)