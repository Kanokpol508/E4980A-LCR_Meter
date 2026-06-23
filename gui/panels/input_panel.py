# กล่องสำหรับกรอกค่าพารามิเตอร์ต่างๆ เช่น ความถี่, แรงดัน, โหมดสแกน

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QGridLayout,
                             QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QHBoxLayout, QSizePolicy)
from PyQt6.QtCore import Qt

class CleanDoubleSpinBox(QDoubleSpinBox):
    def textFromValue(self, val):
        # โชว์ตัวเลขเต็ม ไม่มีย่อ (k, M) และตัดทศนิยม .00 ด้านหลังทิ้ง
        text = f"{val:.{self.decimals()}f}"
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return text

class InputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # --- 1. Property ---
        group_prop = QGroupBox("1. ประเภทการวัด (Measurement Type)")
        v_prop = QVBoxLayout()
        self.combo_prop_group = QComboBox()
        self.combo_scpi_mode = QComboBox()
        v_prop.addWidget(QLabel("กลุ่มพารามิเตอร์ (Parameter Group):"))
        v_prop.addWidget(self.combo_prop_group)
        v_prop.addWidget(QLabel("โหมดพารามิเตอร์ (SCPI Mode):"))
        v_prop.addWidget(self.combo_scpi_mode)
        group_prop.setLayout(v_prop)
        
        # --- 2. Test Signal ---
        group_signal = QGroupBox("2. สัญญาณทดสอบ (Test Signal)")
        grid_signal = QGridLayout()
        grid_signal.addWidget(QLabel("ความถี่ (Frequency) Hz:"), 0, 0)
        self.input_freq = CleanDoubleSpinBox()
        self.input_freq.setRange(20.0, 2000000.0)
        self.input_freq.setDecimals(2)
        self.input_freq.setSingleStep(100)
        self.input_freq.setValue(100000.0)
        grid_signal.addWidget(self.input_freq, 1, 0)
        
        grid_signal.addWidget(QLabel("แรงดัน (Voltage) Vrms:"), 0, 1)
        self.input_volt = CleanDoubleSpinBox()
        self.input_volt.setRange(0.0001, 20.0)
        self.input_volt.setDecimals(4)
        self.input_volt.setSingleStep(0.1)
        self.input_volt.setValue(1.0)
        grid_signal.addWidget(self.input_volt, 1, 1)
        group_signal.setLayout(grid_signal)
        
        # --- 3. Sweep ---
        self.group_sweep = QGroupBox("3. ตั้งค่าสแกนความถี่ (Step Sweep)")
        grid_sweep = QGridLayout()
        
        self.input_start_freq = CleanDoubleSpinBox()
        self.input_start_freq.setRange(20.0, 2000000.0)
        self.input_start_freq.setDecimals(2)
        self.input_start_freq.setSingleStep(100)
        self.input_start_freq.setValue(100.0)

        self.input_stop_freq = CleanDoubleSpinBox()
        self.input_stop_freq.setRange(20.0, 2000000.0)
        self.input_stop_freq.setDecimals(2)
        self.input_stop_freq.setSingleStep(100)
        self.input_stop_freq.setValue(1000000.0)

        self.input_step_freq = CleanDoubleSpinBox()
        self.input_step_freq.setRange(0.01, 1999980.0)
        self.input_step_freq.setDecimals(2)
        self.input_step_freq.setSingleStep(100)
        self.input_step_freq.setValue(20000.0)

        grid_sweep.addWidget(QLabel("ความถี่เริ่มต้น (Start Freq):"), 0, 0)
        grid_sweep.addWidget(self.input_start_freq, 1, 0)
        grid_sweep.addWidget(QLabel("ความถี่สิ้นสุด (Stop Freq):"), 0, 1)
        grid_sweep.addWidget(self.input_stop_freq, 1, 1)

        grid_sweep.addWidget(QLabel("ค่าเพิ่มต่อจุด (Step Size) Hz:"), 2, 0)
        grid_sweep.addWidget(self.input_step_freq, 3, 0)

        self.lbl_calculated_points = QLabel("จำนวนจุดที่ได้: -")
        self.lbl_calculated_points.setStyleSheet("color: #38bdf8; font-weight: bold;")
        grid_sweep.addWidget(self.lbl_calculated_points, 3, 1)

        self.group_sweep.setLayout(grid_sweep)
        
        # --- 4. Hardware Settings ---
        group_hw = QGroupBox("4. ฮาร์ดแวร์และเวลา (Hardware & Timing)")
        grid_hw = QGridLayout()
        
        grid_hw.addWidget(QLabel("เวลาวัด (Meas Time):"), 0, 0)
        self.combo_time = QComboBox()
        self.combo_time.addItems(["SHORT", "MEDIUM", "LONG"])
        grid_hw.addWidget(self.combo_time, 1, 0)
        
        grid_hw.addWidget(QLabel("ค่าเฉลี่ย (Averaging):"), 0, 1)
        self.input_avg = QSpinBox()
        self.input_avg.setRange(1, 256)
        self.input_avg.setValue(1)
        grid_hw.addWidget(self.input_avg, 1, 1)
        
        grid_hw.addWidget(QLabel("สายวัด (Cable Length):"), 2, 0)
        self.combo_cable = QComboBox()
        self.combo_cable.addItems(["0 m", "1 m", "2 m", "4 m"])
        grid_hw.addWidget(self.combo_cable, 3, 0)
        
        grid_hw.addWidget(QLabel("ย่านอิมพีแดนซ์ (Z Range):"), 2, 1)
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
        
        grid_hw.addWidget(self.combo_range, 3, 1)
        
        group_hw.setLayout(grid_hw)

        layout.addWidget(group_prop)
        layout.addWidget(group_signal)
        layout.addWidget(self.group_sweep)
        layout.addWidget(group_hw)
        layout.addStretch()