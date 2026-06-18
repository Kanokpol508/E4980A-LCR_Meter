# วาดหน้าจอดำๆ แสดงตัวเลข Primary/Secondary

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QGroupBox, QLabel, QPushButton, QSizePolicy
from PyQt6.QtCore import Qt

class LcdDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        group_lcd = QGroupBox("ผลการวัด (Measurement Result)")
        group_lcd.setObjectName("lcdGroup")
        group_lcd.setMinimumHeight(160)
        h_lcd = QHBoxLayout()
        
        self.lbl_pri_val = QLabel("---")
        self.lbl_pri_val.setObjectName("lblPriVal") 
        self.lbl_pri_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_pri_val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        self.lbl_sec_val = QLabel("---")
        self.lbl_sec_val.setObjectName("lblSecVal")
        self.lbl_sec_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sec_val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        v_pri = QVBoxLayout()
        lbl_pri_title = QLabel("พารามิเตอร์หลัก (Primary)")
        lbl_pri_title.setObjectName("lblPriTitle")              # ID หัวข้อหลัก
        v_pri.addWidget(lbl_pri_title)
        v_pri.addWidget(self.lbl_pri_val, stretch=1)
        
        v_sec = QVBoxLayout()
        lbl_sec_title = QLabel("พารามิเตอร์รอง (Secondary)")
        lbl_sec_title.setObjectName("lblSecTitle")              # ID หัวข้อรอง
        v_sec.addWidget(lbl_sec_title)
        v_sec.addWidget(self.lbl_sec_val, stretch=1)
        
        h_lcd.addLayout(v_pri)
        h_lcd.addLayout(v_sec)
        group_lcd.setLayout(h_lcd)
        
        layout.addWidget(group_lcd, stretch=1)

        # โซนปุ่มจัดการข้อมูลฝั่งขวา
        v_tools = QVBoxLayout()
        v_tools.setContentsMargins(10, 10, 0, 0)
        
        self.btn_save = QPushButton("Save Result")
        self.btn_view = QPushButton("View Save Result")
        self.btn_clear = QPushButton("Clear Graph")
        
        # ปรับให้ปุ่มขยายตัวเต็มพื้นที่แนวตั้ง
        self.btn_save.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.btn_view.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.btn_clear.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        
        v_tools.addWidget(self.btn_save)
        v_tools.addWidget(self.btn_view)
        v_tools.addWidget(self.btn_clear)
        
        layout.addLayout(v_tools)