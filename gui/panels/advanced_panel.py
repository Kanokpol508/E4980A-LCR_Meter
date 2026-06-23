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
        
        # --- 5. Correction ---
        group_corr = QGroupBox("5. การปรับชดเชยค่าสายวัด (Correction)")
        v_corr = QVBoxLayout()
        v_corr.setSpacing(10)
        lbl_corr_hint = QLabel("💡 คำแนะนำ:\n• ถ่างปลายสายวัดออกจากกัน ➔ กด OPEN\n• นำปลายสายวัดมาช็อตกัน ➔ กด SHORT")
        lbl_corr_hint.setWordWrap(True)
        v_corr.addWidget(lbl_corr_hint)
        
        h_corr_buttons = QHBoxLayout()
        self.btn_open_corr = QPushButton("OPEN Correction")
        self.btn_open_corr.setObjectName("btnOpenCorr")  # เพิ่ม ID เพื่อให้ qss ตกแต่งเป็นสีส้ม
        
        self.btn_short_corr = QPushButton("SHORT Correction")
        self.btn_short_corr.setObjectName("btnShortCorr") # เพิ่ม ID เพื่อให้ qss ตกแต่งเป็นสีส้ม
        
        h_corr_buttons.addWidget(self.btn_open_corr)
        h_corr_buttons.addWidget(self.btn_short_corr)
        v_corr.addLayout(h_corr_buttons)
        group_corr.setLayout(v_corr)
        
        # --- 6. DC Bias ---
        group_dc = QGroupBox("6. DC Bias (ไฟเลี้ยงกระแสตรง)")
        v_dc = QVBoxLayout()
        
        h_dc_enable = QHBoxLayout()
        self.chk_dc_enable = QCheckBox("เปิดใช้งาน (Enable DC Bias)")
        h_dc_enable.addWidget(self.chk_dc_enable)
        v_dc.addLayout(h_dc_enable)
        
        self.widget_dc_inner = QWidget()
        v_dc_inner = QVBoxLayout(self.widget_dc_inner)
        v_dc_inner.setContentsMargins(0, 0, 0, 0)
        v_dc_inner.setSpacing(10)
        
        # ลบ Checkbox Option 001 ออก
        
        h_dc_type = QHBoxLayout()
        h_dc_type.addWidget(QLabel("ชนิดของไฟเลี้ยง:"))
        
        # ลบปุ่ม Current ออก และเหลือแค่ปุ่ม Voltage (แต่ล็อกไว้ไม่ให้ผู้ใช้กดสลับ เพื่อรักษา Object ให้โค้ดฝั่ง Controller ไม่พัง)
        self.btn_dc_v = QPushButton("Voltage (V)")
        self.btn_dc_v.setCheckable(True)
        self.btn_dc_v.setChecked(True)
        self.btn_dc_v.setEnabled(False) 
        
        self.dc_type_group = QButtonGroup()
        self.dc_type_group.addButton(self.btn_dc_v)
        h_dc_type.addWidget(self.btn_dc_v)
        v_dc_inner.addLayout(h_dc_type)
        
        h_dc_level = QHBoxLayout()
        h_dc_level.addWidget(QLabel("ระดับไฟ (Level):"))
        self.input_dc_level = QDoubleSpinBox()
        self.input_dc_level.setDecimals(1)
        # ปรับ Range ให้เหลือแค่ 0.0 - 2.0 V และปรับ Step ให้สอดคล้องกับค่า Discrete (0, 1.5, 2.0)
        self.input_dc_level.setRange(0.0, 2.0)
        self.input_dc_level.setSingleStep(0.5)
        self.input_dc_level.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lbl_dc_unit = QLabel("V")
        
        h_dc_level.addWidget(self.input_dc_level, stretch=1)
        h_dc_level.addWidget(self.lbl_dc_unit)
        v_dc_inner.addLayout(h_dc_level)
        
        self.lbl_dc_warning = QLabel("⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!")
        self.lbl_dc_warning.setWordWrap(True)
        self.lbl_dc_warning.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")
        v_dc_inner.addWidget(self.lbl_dc_warning)
        
        v_dc.addWidget(self.widget_dc_inner)
        group_dc.setLayout(v_dc)

        # --- 7. Deviation (เปรียบเทียบค่า) ---
        group_dev = QGroupBox("7. Deviation (เปรียบเทียบค่าอ้างอิง)")
        v_dev = QVBoxLayout()
        
        h_dev_enable = QHBoxLayout()
        self.chk_dev_enable = QCheckBox("เปิดใช้งาน (Enable Deviation)")
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
        self.combo_dev_type.addItems([
            "Δ (ส่วนต่างจริง)", 
            "Δ% (ส่วนต่างเป็นเปอร์เซ็นต์)"
        ])
        v_dev_inner.addWidget(self.combo_dev_type)
        
        self.lbl_dev_warning = QLabel("")
        self.lbl_dev_warning.setWordWrap(True)
        self.lbl_dev_warning.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")
        v_dev_inner.addWidget(self.lbl_dev_warning)
        
        v_dev.addWidget(self.widget_dev_inner)
        group_dev.setLayout(v_dev)

        layout.addWidget(group_corr)
        layout.addWidget(group_dc)
        layout.addWidget(group_dev)