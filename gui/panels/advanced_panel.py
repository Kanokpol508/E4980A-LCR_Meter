# กล่องตั้งค่า Correction, Deviation
# (หมายเหตุ: DC Bias ย้ายไปอยู่ใน input_panel.py แล้ว
#  เพื่อให้วางคู่กับกล่อง "สัญญาณทดสอบ (Test Signal)" ในแนวนอนเดียวกัน)

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, 
                             QPushButton, QLabel, QCheckBox, 
                             QGridLayout, QLineEdit, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt


def _make_row(label_text, widget):
    """สร้างแถว: [หัวข้อ:] [ช่องกรอก/dropdown (ขยายเต็มที่)]"""
    row = QHBoxLayout()
    row.addWidget(QLabel(label_text))
    row.addWidget(widget, stretch=1)
    return row


class AdvancedPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # --- 5. Correction ---
        group_corr = QGroupBox("การปรับชดเชยค่าสายวัด (Correction)")
        v_corr = QVBoxLayout()
        v_corr.setSpacing(10)
        lbl_corr_hint = QLabel(
            "💡 คำแนะนำ:\n"
            "• ถ่างปลายสายวัดออกจากกัน ➔ กด OPEN\n"
            "• นำปลายสายวัดมาช็อตกัน ➔ กด SHORT\n"
            "• ตรวจสอบตั้งค่า สายวัด (Cable Length) ให้ตรงกับสายที่ใช้จริงก่อนกดปุ่มเสมอ"
        )
        lbl_corr_hint.setWordWrap(True)
        v_corr.addWidget(lbl_corr_hint)
        
        h_corr_buttons = QHBoxLayout()
        self.btn_open_corr = QPushButton("OPEN Correction")
        self.btn_open_corr.setObjectName("btnOpenCorr")  
        
        self.btn_short_corr = QPushButton("SHORT Correction")
        self.btn_short_corr.setObjectName("btnShortCorr") 
        
        h_corr_buttons.addWidget(self.btn_open_corr)
        h_corr_buttons.addWidget(self.btn_short_corr)
        v_corr.addLayout(h_corr_buttons)
        group_corr.setLayout(v_corr)

        # --- 6. Deviation (เปรียบเทียบค่า) ---
        group_dev = QGroupBox("เปรียบเทียบค่าอ้างอิง (Deviation)")
        v_dev = QVBoxLayout()
        
        h_dev_enable = QHBoxLayout()
        self.chk_dev_enable = QCheckBox("เปิดใช้งาน (Enable Deviation)")
        h_dev_enable.addWidget(self.chk_dev_enable)
        v_dev.addLayout(h_dev_enable)
        
        self.widget_dev_inner = QWidget()
        v_dev_inner = QVBoxLayout(self.widget_dev_inner)
        v_dev_inner.setContentsMargins(0, 0, 0, 0)
        v_dev_inner.setSpacing(8)

        self.input_dev_pri = QLineEdit()
        self.input_dev_pri.setPlaceholderText("กรอกค่าอ้างอิงหลัก")

        self.input_dev_sec = QLineEdit()
        self.input_dev_sec.setPlaceholderText("กรอกค่าอ้างอิงรอง")

        self.combo_dev_type = QComboBox()
        self.combo_dev_type.addItems([
            "Δ (ส่วนต่างจริง)", 
            "Δ% (ส่วนต่างเป็นเปอร์เซ็นต์)"
        ])

        v_dev_inner.addLayout(_make_row("Primary Ref (หลัก) *:", self.input_dev_pri))
        v_dev_inner.addLayout(_make_row("Secondary Ref (รอง):", self.input_dev_sec))
        v_dev_inner.addLayout(_make_row("รูปแบบเอาต์พุต (OUTPUT TYPE):", self.combo_dev_type))
        
        self.lbl_dev_warning = QLabel("")
        self.lbl_dev_warning.setWordWrap(True)
        self.lbl_dev_warning.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")
        v_dev_inner.addWidget(self.lbl_dev_warning)
        
        v_dev.addWidget(self.widget_dev_inner)
        group_dev.setLayout(v_dev)

        layout.addWidget(group_corr)
        layout.addWidget(group_dev)