# กล่องสำหรับกรอกค่าพารามิเตอร์ต่างๆ เช่น ความถี่, แรงดัน, โหมดสแกน

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QGridLayout,
                             QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QHBoxLayout,
                             QSizePolicy, QLineEdit, QCheckBox)
from PyQt6.QtCore import Qt

# ความกว้างมาตรฐานของช่องกรอกค่าตัวเลขสั้นๆ (ความถี่ / แรงดัน)
FREQ_FIELD_WIDTH = 150
VOLT_FIELD_WIDTH = 90


class CleanDoubleSpinBox(QDoubleSpinBox):
    def textFromValue(self, val):
        # โชว์ตัวเลขเต็ม ไม่มีย่อ (k, M) และตัดทศนิยม .00 ด้านหลังทิ้ง
        text = f"{val:.{self.decimals()}f}"
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return text


def _make_row(label_text, widget, unit_text=None):
    """สร้างแถว: [หัวข้อ:] [ช่องกรอก/dropdown (ขยายเต็มที่)] [หน่วย (ถ้ามี)]"""
    row = QHBoxLayout()
    row.addWidget(QLabel(label_text))
    row.addWidget(widget, stretch=1)
    if unit_text:
        row.addWidget(QLabel(unit_text))
    return row


def _make_fixed_row(label_text, widget, unit_text=None, width=FREQ_FIELD_WIDTH):
    """สร้างแถว: [หัวข้อ:] [ช่องกรอก ความกว้างคงที่เป๊ะๆ ไม่ว่าตัวเลขข้างในจะสั้นหรือยาว] [หน่วย (ถ้ามี)] ...พื้นที่ว่าง"""
    widget.setFixedWidth(width)
    row = QHBoxLayout()
    row.addWidget(QLabel(label_text))
    row.addWidget(widget)
    if unit_text:
        row.addWidget(QLabel(unit_text))
    row.addStretch()
    return row


class InputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ==========================================================
        # 1. ประเภทการวัด (Measurement Type)
        # ใช้ QGridLayout เพื่อให้ทั้ง 2 dropdown อยู่คอลัมน์เดียวกัน
        # ความกว้างเท่ากันและชิดตรงกันโดยอัตโนมัติ
        # ==========================================================
        self.group_prop = QGroupBox("ประเภทการวัด (Measurement Type)")
        grid_prop = QGridLayout()
        grid_prop.setVerticalSpacing(8)
        grid_prop.setColumnStretch(1, 1)

        self.combo_prop_group = QComboBox()
        self.combo_scpi_mode = QComboBox()

        lbl_prop_group = QLabel("กลุ่มพารามิเตอร์\n(Parameter Group):")
        lbl_scpi_mode = QLabel("โหมดพารามิเตอร์\n(SCPI Mode):")
        lbl_prop_group.setMaximumWidth(120)
        lbl_scpi_mode.setMaximumWidth(120)

        grid_prop.addWidget(lbl_prop_group, 0, 0)
        grid_prop.addWidget(self.combo_prop_group, 0, 1)
        grid_prop.addWidget(lbl_scpi_mode, 1, 0)
        grid_prop.addWidget(self.combo_scpi_mode, 1, 1)

        self.group_prop.setLayout(grid_prop)

        # ==========================================================
        # 2. ตั้งค่าความถี่ (Frequency Settings)
        # ==========================================================
        self.group_mode = QGroupBox("ตั้งค่าความถี่ (Frequency Settings)")
        v_mode = QVBoxLayout()
        v_mode.setSpacing(10)

        # --- Dropdown เลือกโหมดการวัด ---
        v_mode.addWidget(QLabel("เลือกโหมดการวัด (Select Measurement Mode):"))
        self.combo_run_mode = QComboBox()
        self.combo_run_mode.addItem("วัดจุดเดียว (Single)", userData="SINGLE")
        self.combo_run_mode.addItem("สแกนความถี่ (Sweep)", userData="SWEEP")
        self.combo_run_mode.addItem("รายการความถี่ (List)", userData="LIST")
        self.combo_run_mode.setCurrentIndex(1)  # ค่าเริ่มต้น = Sweep
        v_mode.addWidget(self.combo_run_mode)

        # --- เนื้อหาย่อย: วัดจุดเดียว (SINGLE) ---
        self.widget_freq_single = QWidget()
        v_freq_single = QVBoxLayout(self.widget_freq_single)
        v_freq_single.setContentsMargins(0, 0, 0, 0)
        v_freq_single.setSpacing(8)

        self.input_freq = CleanDoubleSpinBox()
        self.input_freq.setRange(20.0, 2000000.0)
        self.input_freq.setDecimals(2)
        self.input_freq.setSingleStep(100)
        self.input_freq.setValue(100000.0)

        v_freq_single.addLayout(_make_fixed_row("ความถี่ (Frequency):", self.input_freq, "Hz"))
        v_mode.addWidget(self.widget_freq_single)

        # --- เนื้อหาย่อย: สแกนความถี่ Linear (SWEEP) ---
        # ใช้ QGridLayout เหมือนกลุ่มฮาร์ดแวร์ฯ เพื่อให้ label คอลัมน์ 0
        # ความกว้างเท่ากันทุกแถว -> ช่องกรอก (คอลัมน์ 1) เริ่มต้นตำแหน่งเดียวกันเป๊ะ
        self.widget_sweep = QWidget()
        grid_sweep = QGridLayout(self.widget_sweep)
        grid_sweep.setContentsMargins(0, 0, 0, 0)
        grid_sweep.setVerticalSpacing(8)

        self.input_start_freq = CleanDoubleSpinBox()
        self.input_start_freq.setRange(20.0, 2000000.0)
        self.input_start_freq.setDecimals(2)
        self.input_start_freq.setSingleStep(100)
        self.input_start_freq.setValue(100.0)
        self.input_start_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        self.input_stop_freq = CleanDoubleSpinBox()
        self.input_stop_freq.setRange(20.0, 2000000.0)
        self.input_stop_freq.setDecimals(2)
        self.input_stop_freq.setSingleStep(100)
        self.input_stop_freq.setValue(1000000.0)
        self.input_stop_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        self.input_step_freq = CleanDoubleSpinBox()
        self.input_step_freq.setRange(0.01, 1999980.0)
        self.input_step_freq.setDecimals(2)
        self.input_step_freq.setSingleStep(100)
        self.input_step_freq.setValue(20000.0)
        self.input_step_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        self.lbl_calculated_points = QLabel("-")
        self.lbl_calculated_points.setStyleSheet("color: #38bdf8; font-weight: bold;")

        grid_sweep.addWidget(QLabel("ความถี่เริ่มต้น (Start Freq):"), 0, 0)
        grid_sweep.addWidget(self.input_start_freq, 0, 1)
        grid_sweep.addWidget(QLabel("Hz"), 0, 2)

        grid_sweep.addWidget(QLabel("ความถี่สิ้นสุด (Stop Freq):"), 1, 0)
        grid_sweep.addWidget(self.input_stop_freq, 1, 1)
        grid_sweep.addWidget(QLabel("Hz"), 1, 2)

        grid_sweep.addWidget(QLabel("ค่าเพิ่มต่อจุด (Step Size):"), 2, 0)
        grid_sweep.addWidget(self.input_step_freq, 2, 1)
        grid_sweep.addWidget(QLabel("Hz"), 2, 2)

        grid_sweep.addWidget(QLabel("จำนวนจุดที่ได้:"), 3, 0)
        grid_sweep.addWidget(self.lbl_calculated_points, 3, 1)

        grid_sweep.setColumnStretch(3, 1)  # เผื่อพื้นที่ว่างด้านขวาสุด

        v_mode.addWidget(self.widget_sweep)

        # --- เนื้อหาย่อย: รายการความถี่ + Samples ต่อจุด (LIST) ---
        self.widget_list = QWidget()
        v_list = QVBoxLayout(self.widget_list)
        v_list.setContentsMargins(0, 0, 0, 0)
        v_list.setSpacing(10)

        v_list.addWidget(QLabel("รายการความถี่ (คั่นด้วย comma เช่น 100, 1k, 10k, 100k, 1M):"))
        self.input_freq_list = QLineEdit()
        self.input_freq_list.setPlaceholderText("100, 1k, 10k, 100k, 1M, 2M")
        v_list.addWidget(self.input_freq_list)

        h_samples = QHBoxLayout()
        h_samples.addWidget(QLabel("จำนวนรอบวัดซ้ำต่อความถี่ (Samples per Sweep):"))
        self.input_samples = QSpinBox()
        self.input_samples.setRange(1, 999)
        self.input_samples.setValue(10)
        h_samples.addWidget(self.input_samples)
        v_list.addLayout(h_samples)

        v_mode.addWidget(self.widget_list)

        self.group_mode.setLayout(v_mode)

        # ==========================================================
        # 3. สัญญาณทดสอบ (Test Signal) + DC Bias (วางข้างกัน)
        # ==========================================================

        # --- 3a. Test Signal - ช่องกรอกแรงดันสั้นลง ---
        self.group_signal = QGroupBox("สัญญาณทดสอบ (Test Signal)")
        v_signal = QVBoxLayout()

        self.input_volt = CleanDoubleSpinBox()
        self.input_volt.setRange(0.0001, 20.0)
        self.input_volt.setDecimals(4)
        self.input_volt.setSingleStep(0.1)
        self.input_volt.setValue(1.0)

        v_signal.addWidget(QLabel("แรงดัน (Voltage):"))
        v_signal.addLayout(_make_row("", self.input_volt, "Vrms"))
        v_signal.addStretch()
        self.group_signal.setLayout(v_signal)

        # --- 3b. DC Bias ---
        self.group_dc = QGroupBox("ไฟเลี้ยงกระแสตรง (DC Bias)")
        v_dc = QVBoxLayout()

        h_dc_enable = QHBoxLayout()
        self.chk_dc_enable = QCheckBox("เปิดใช้งาน (Enable)")
        h_dc_enable.addWidget(self.chk_dc_enable)
        v_dc.addLayout(h_dc_enable)

        self.widget_dc_inner = QWidget()
        v_dc_inner = QVBoxLayout(self.widget_dc_inner)
        v_dc_inner.setContentsMargins(0, 0, 0, 0)
        v_dc_inner.setSpacing(8)

        self.combo_dc_level = QComboBox()
        self.combo_dc_level.addItem("1.5 V", userData=1.5)
        self.combo_dc_level.addItem("2.0 V", userData=2.0)

        v_dc_inner.addWidget(QLabel("ระดับไฟ (Level):"))
        v_dc_inner.addWidget(self.combo_dc_level)

        self.lbl_dc_warning = QLabel("")
        self.lbl_dc_warning.setWordWrap(True)
        self.lbl_dc_warning.setMaximumWidth(190)
        self.lbl_dc_warning.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")
        v_dc_inner.addWidget(self.lbl_dc_warning)

        v_dc.addWidget(self.widget_dc_inner)
        v_dc.addStretch()
        self.group_dc.setLayout(v_dc)

        h_signal_dc = QHBoxLayout()
        h_signal_dc.addWidget(self.group_signal, stretch=1)
        h_signal_dc.addWidget(self.group_dc, stretch=1)

        # ==========================================================
        # 4. ฮาร์ดแวร์และเวลา (Hardware & Timing)
        # ใช้ QGridLayout เพื่อให้ทั้ง 4 ช่อง (dropdown/spinbox) อยู่
        # คอลัมน์เดียวกัน -> ความกว้างเท่ากันและชิดตรงกันโดยอัตโนมัติ
        # ==========================================================
        self.group_hw = QGroupBox("ฮาร์ดแวร์และเวลา (Hardware & Timing)")
        grid_hw = QGridLayout()
        grid_hw.setVerticalSpacing(8)
        grid_hw.setColumnStretch(1, 1)

        self.combo_time = QComboBox()
        self.combo_time.addItems(["SHORT", "MEDIUM", "LONG"])

        self.input_avg = QSpinBox()
        self.input_avg.setRange(1, 256)
        self.input_avg.setValue(1)

        self.combo_cable = QComboBox()
        self.combo_cable.addItems(["0 m", "1 m", "2 m", "4 m"])

        self.combo_range = QComboBox()
        self.combo_range.addItem("AUTO", userData="AUTO")
        self.combo_range.addItem("0.1 Ω", userData=0.1)
        self.combo_range.addItem("1 Ω", userData=1)
        self.combo_range.addItem("10 Ω", userData=10)
        self.combo_range.addItem("100 Ω", userData=100)
        self.combo_range.addItem("300 Ω", userData=300)
        self.combo_range.addItem("1 kΩ", userData=1000)
        self.combo_range.addItem("3 kΩ", userData=3000)
        self.combo_range.addItem("10 kΩ", userData=10000)
        self.combo_range.addItem("30 kΩ", userData=30000)
        self.combo_range.addItem("100 kΩ", userData=100000)

        grid_hw.addWidget(QLabel("เวลาวัด (Meas Time):"), 0, 0)
        grid_hw.addWidget(self.combo_time, 0, 1)
        grid_hw.addWidget(QLabel("ค่าเฉลี่ย (Averaging):"), 1, 0)
        grid_hw.addWidget(self.input_avg, 1, 1)
        grid_hw.addWidget(QLabel("สายวัด (Cable Length):"), 2, 0)
        grid_hw.addWidget(self.combo_cable, 2, 1)
        grid_hw.addWidget(QLabel("ย่านอิมพีแดนซ์ (Z Range):"), 3, 0)
        grid_hw.addWidget(self.combo_range, 3, 1)

        self.group_hw.setLayout(grid_hw)

        # ==========================================================
        # ประกอบ Layout
        # ==========================================================
        layout.addWidget(self.group_prop)
        layout.addWidget(self.group_mode)
        layout.addLayout(h_signal_dc)
        layout.addWidget(self.group_hw)

        layout.addStretch()