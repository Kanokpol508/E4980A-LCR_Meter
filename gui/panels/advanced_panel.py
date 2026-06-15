# กล่องตั้งค่า DC Bias, Deviation, Correction

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, 
                             QPushButton, QLabel, QCheckBox, QButtonGroup, 
                             QDoubleSpinBox, QGridLayout, QLineEdit, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt

class AdvancedPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # --- 4. Correction ---
        group_corr = QGroupBox("4. การปรับชดเชยค่าสายวัด (Correction)")
        v_corr = QVBoxLayout()
        v_corr.setSpacing(10)
        lbl_corr_hint = QLabel("💡 คำแนะนำ:\n• ถ่างปลายสายวัดออกจากกัน ➔ กด OPEN\n• นำปลายสายวัดมาช็อตกัน ➔ กด SHORT")
        lbl_corr_hint.setWordWrap(True)
        v_corr.addWidget(lbl_corr_hint)
        h_corr_buttons = QHBoxLayout()
        self.btn_open_corr = QPushButton("OPEN Correction")
        self.btn_short_corr = QPushButton("SHORT Correction")
        h_corr_buttons.addWidget(self.btn_open_corr)
        h_corr_buttons.addWidget(self.btn_short_corr)
        v_corr.addLayout(h_corr_buttons)
        group_corr.setLayout(v_corr)
        layout.addWidget(group_corr)
        
        # --- 6. DC Bias ---
        self.group_dc = QGroupBox("6. ไฟตรง (DC BIAS)")
        v_dc = QVBoxLayout()
        h_enable = QHBoxLayout()
        h_enable.addStretch()
        self.chk_dc_enable = QCheckBox("เปิดใช้งาน")
        h_enable.addWidget(self.chk_dc_enable)
        v_dc.addLayout(h_enable)
        
        self.widget_dc_inner = QWidget()
        v_dc_inner = QVBoxLayout(self.widget_dc_inner)
        v_dc_inner.setContentsMargins(0, 0, 0, 0)
        v_dc_inner.setSpacing(10)
        
        self.dc_btn_group = QButtonGroup()
        self.btn_dc_v = QPushButton("Voltage Bias (V)")
        self.btn_dc_a = QPushButton("Current Bias (A)")
        self.btn_dc_v.setCheckable(True)
        self.btn_dc_a.setCheckable(True)
        self.btn_dc_v.setChecked(True)
        self.dc_btn_group.addButton(self.btn_dc_v)
        self.dc_btn_group.addButton(self.btn_dc_a)
        
        h_va = QHBoxLayout()
        h_va.addWidget(self.btn_dc_v)
        h_va.addWidget(self.btn_dc_a)
        v_dc_inner.addLayout(h_va)
        
        v_dc_inner.addWidget(QLabel("ระดับไฟตรง (LEVEL)"))
        
        h_level = QHBoxLayout()
        self.input_dc_level = QDoubleSpinBox()
        self.input_dc_level.setRange(-40.0, 40.0)
        self.input_dc_level.setDecimals(3)
        self.input_dc_level.setSingleStep(0.1)
        self.input_dc_level.setValue(1.5)
        self.input_dc_level.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lbl_dc_unit = QLabel("V")
        self.lbl_dc_unit.setFixedWidth(40)
        self.lbl_dc_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chk_opt001 = QCheckBox("เปิดใช้งาน Option 001")
        
        h_level.addWidget(self.input_dc_level)
        h_level.addWidget(self.lbl_dc_unit)
        h_level.addSpacing(20)
        h_level.addWidget(self.chk_opt001)
        v_dc_inner.addLayout(h_level)
        
        self.lbl_dc_warning = QLabel("⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!")
        self.lbl_dc_warning.setWordWrap(True)
        v_dc_inner.addWidget(self.lbl_dc_warning)
        
        v_dc.addWidget(self.widget_dc_inner)
        self.group_dc.setLayout(v_dc)
        layout.addWidget(self.group_dc)
        
        # --- 7. Deviation ---
        self.group_dev = QGroupBox("7. เบี่ยงเบน (DEVIATION)")
        v_dev = QVBoxLayout()
        h_dev_enable = QHBoxLayout()
        h_dev_enable.addStretch()
        self.chk_dev_enable = QCheckBox("เปิดใช้งาน")
        h_dev_enable.addWidget(self.chk_dev_enable)
        v_dev.addLayout(h_dev_enable)
        
        self.widget_dev_inner = QWidget()
        v_dev_inner = QVBoxLayout(self.widget_dev_inner)
        v_dev_inner.setContentsMargins(0, 0, 0, 0)
        v_dev_inner.setSpacing(10)
        
        grid_dev_refs = QGridLayout()
        grid_dev_refs.addWidget(QLabel("Primary Ref (หลัก) *"), 0, 0)
        self.input_dev_pri = QLineEdit()
        self.input_dev_pri.setPlaceholderText("เช่น 100E-9")
        grid_dev_refs.addWidget(self.input_dev_pri, 1, 0)
        grid_dev_refs.addWidget(QLabel("Secondary Ref (รอง)"), 0, 1)
        self.input_dev_sec = QLineEdit()
        self.input_dev_sec.setPlaceholderText("เช่น 0.001")
        grid_dev_refs.addWidget(self.input_dev_sec, 1, 1)
        v_dev_inner.addLayout(grid_dev_refs)
        
        v_dev_inner.addWidget(QLabel("รูปแบบเอาต์พุต (OUTPUT TYPE)"))
        self.combo_dev_type = QComboBox()
        self.combo_dev_type.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_dev_type.addItems(["ผลต่างสัมบูรณ์ (Absolute Δ)", "เปอร์เซ็นต์ (Percentage Δ%)"])
        v_dev_inner.addWidget(self.combo_dev_type)
        
        self.lbl_dev_warning = QLabel("")
        self.lbl_dev_warning.setWordWrap(True)
        v_dev_inner.addWidget(self.lbl_dev_warning)
        
        v_dev.addWidget(self.widget_dev_inner)
        self.group_dev.setLayout(v_dev)
        layout.addWidget(self.group_dev)