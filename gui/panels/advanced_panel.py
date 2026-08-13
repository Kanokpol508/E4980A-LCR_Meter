# กล่องตั้งค่า Correction, PPM Reference

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QHBoxLayout,
                             QPushButton, QLabel, QCheckBox,
                             QGridLayout, QLineEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator


class AdvancedPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Correction ---
        group_corr = QGroupBox("Correction")
        v_corr = QVBoxLayout()
        v_corr.setSpacing(10)
        lbl_corr_hint = QLabel(
            "💡ตรวจสอบให้แน่ใจว่าตั้งค่า Cable Length \n"
            "ตรงกับสายที่ใช้งานจริงก่อนกดปุ่มเสมอ"
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

        # --- PPM Reference ---
        # ใช้สำหรับคำนวณ PPM Deviation ในตารางสถิติทุกโหมดการวัด (SINGLE, SWEEP, LIST)
        # กราฟแสดงค่าดิบเสมอ — ไม่มี Graph Deviation แล้ว
        self.group_ppm = QGroupBox("PPM Deviation")
        v_ppm = QVBoxLayout()
        v_ppm.setSpacing(8)

        lbl_ppm_hint = QLabel(
            "💡ผลลัพธ์จะแสดงในคอลัมน์ PPM Dev ตาราง Statistics Table"
        )
        lbl_ppm_hint.setWordWrap(True)
        v_ppm.addWidget(lbl_ppm_hint)

        # checkbox เปิด/ปิด PPM — ใช้งานได้ทุกโหมดการวัด (SINGLE, SWEEP, LIST)
        self.chk_dev_ppm_enable = QCheckBox("Enable PPM Deviation calculation")
        v_ppm.addWidget(self.chk_dev_ppm_enable)

        # widget ที่ถูก enable/disable ตาม checkbox
        self.widget_dev_inner = QWidget()
        v_inner = QVBoxLayout(self.widget_dev_inner)
        v_inner.setContentsMargins(0, 0, 0, 0)
        v_inner.setSpacing(8)

        # validator รองรับทั้งทศนิยมปกติและ Scientific Notation เช่น 1.0e-9
        def _make_ref_input(placeholder: str) -> QLineEdit:
            w = QLineEdit()
            w.setPlaceholderText(placeholder)
            v = QDoubleValidator()
            v.setNotation(QDoubleValidator.Notation.ScientificNotation)
            w.setValidator(v)
            return w

        self.input_dev_pri = _make_ref_input("กรอกค่าอ้างอิง")
        self.input_dev_sec = _make_ref_input("กรอกค่าอ้างอิง")

        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        lbl_pri = QLabel("Primary Ref:")
        lbl_sec = QLabel("Secondary Ref:")
        label_width = 95
        lbl_pri.setFixedWidth(label_width)
        lbl_sec.setFixedWidth(label_width)

        grid.addWidget(lbl_pri,             0, 0)
        grid.addWidget(self.input_dev_pri,  0, 1)
        grid.addWidget(lbl_sec,             1, 0)
        grid.addWidget(self.input_dev_sec,  1, 1)

        v_inner.addLayout(grid)

        self.lbl_dev_warning = QLabel("")
        self.lbl_dev_warning.setWordWrap(True)
        self.lbl_dev_warning.setStyleSheet("color: #D2544B; font-weight: bold; font-size: 11px;")
        v_inner.addWidget(self.lbl_dev_warning)

        v_ppm.addWidget(self.widget_dev_inner)
        self.group_ppm.setLayout(v_ppm)

        layout.addWidget(group_corr)
        layout.addWidget(self.group_ppm)