# กล่องตั้งค่า Correction, Deviation


from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, 
                             QPushButton, QLabel, QCheckBox, 
                             QGridLayout, QLineEdit, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator


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
        # แยกเป็น 2 checkbox อิสระ ใช้ Primary/Secondary Ref ชุดเดียวกัน:
        #   1) chk_dev_graph_enable -> ปรับกราฟทั้งหน้าให้แสดงเป็น Δ/Δ%
        #   2) chk_dev_ppm_enable   -> คำนวณ PPM เสริมในตาราง Statistics เท่านั้น
        # ผู้ใช้เปิดอันใดอันหนึ่ง หรือทั้งคู่พร้อมกันก็ได้ ไม่ผูกติดกันเหมือนเดิม
        group_dev = QGroupBox("เปรียบเทียบค่าอ้างอิง (Deviation)")
        v_dev = QVBoxLayout()
        v_dev.setSpacing(8)

        self.chk_dev_graph_enable = QCheckBox("ปรับกราฟเป็น Δ/Δ% (Enable Graph Deviation)")
        self.chk_dev_ppm_enable = QCheckBox("คำนวณ PPM ในตารางสถิติ (Enable PPM in Statistics Table)")

        v_dev.addWidget(self.chk_dev_graph_enable)
        v_dev.addWidget(self.chk_dev_ppm_enable)
        
        self.widget_dev_inner = QWidget()
        v_dev_inner = QVBoxLayout(self.widget_dev_inner)
        v_dev_inner.setContentsMargins(0, 0, 0, 0)
        v_dev_inner.setSpacing(8)

        self.input_dev_pri = QLineEdit()
        self.input_dev_pri.setPlaceholderText("กรอกค่าอ้างอิงหลัก")
        validator_pri = QDoubleValidator()
        validator_pri.setNotation(QDoubleValidator.Notation.ScientificNotation)
        self.input_dev_pri.setValidator(validator_pri)

        self.input_dev_sec = QLineEdit()
        self.input_dev_sec.setPlaceholderText("กรอกค่าอ้างอิงรอง")
        validator_sec = QDoubleValidator()
        validator_sec.setNotation(QDoubleValidator.Notation.ScientificNotation)
        self.input_dev_sec.setValidator(validator_sec)

        self.combo_dev_type = QComboBox()
        self.combo_dev_type.addItems([
            "Δ (ส่วนต่างจริง)", 
            "Δ% (ส่วนต่างเป็นเปอร์เซ็นต์)"
        ])
        self.combo_dev_type.setToolTip("ใช้เฉพาะตอนเปิด \"ปรับกราฟเป็น Δ/Δ%\" เท่านั้น")

        grid_dev = QGridLayout()
        grid_dev.setVerticalSpacing(8)
        grid_dev.setColumnStretch(1, 1)

        lbl_dev_pri = QLabel("Primary Ref (หลัก):")
        lbl_dev_sec = QLabel("Secondary Ref (รอง):")
        lbl_dev_type = QLabel("รูปแบบกราฟ Δ:")

        # กำหนดความกว้าง label เท่ากันทั้ง 3 แถว -> ช่องกรอก/dropdown คอลัมน์ 1
        # เริ่มต้นตำแหน่ง x เดียวกันเป๊ะ (ขนานกัน) ไม่ว่าความยาวข้อความ label จะต่างกัน
        label_width = 130
        lbl_dev_pri.setFixedWidth(label_width)
        lbl_dev_sec.setFixedWidth(label_width)
        lbl_dev_type.setFixedWidth(label_width)

        grid_dev.addWidget(lbl_dev_pri, 0, 0)
        grid_dev.addWidget(self.input_dev_pri, 0, 1)
        grid_dev.addWidget(lbl_dev_sec, 1, 0)
        grid_dev.addWidget(self.input_dev_sec, 1, 1)
        grid_dev.addWidget(lbl_dev_type, 2, 0)
        grid_dev.addWidget(self.combo_dev_type, 2, 1)

        v_dev_inner.addLayout(grid_dev)
        
        self.lbl_dev_warning = QLabel("")
        self.lbl_dev_warning.setWordWrap(True)
        self.lbl_dev_warning.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")
        v_dev_inner.addWidget(self.lbl_dev_warning)
        
        v_dev.addWidget(self.widget_dev_inner)
        group_dev.setLayout(v_dev)

        layout.addWidget(group_corr)
        layout.addWidget(group_dev)