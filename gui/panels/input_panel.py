# กล่องตั้งค่า Meas Type, Test Signal, Hardware & Timing


from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QFormLayout, 
                             QComboBox, QGridLayout, QLabel, QDoubleSpinBox, 
                             QSpinBox, QHBoxLayout, QRadioButton, QSizePolicy)
from PyQt6.QtCore import Qt

class SmartDoubleSpinBox(QDoubleSpinBox):
    """
    คลาสปรับแต่งพิเศษเพื่อซ่อนทศนิยม (.00) ในกรณีที่ผู้ใช้ไม่ได้กรอก
    แต่ยังคงอนุญาตให้กรอกทศนิยมได้ (เช่น 1000.5)
    """
    def textFromValue(self, value):
        # แปลงค่าเป็นข้อความตามจำนวนทศนิยมที่อนุญาตสูงสุด
        text = f"{value:.{self.decimals()}f}"
        # ถ้ามีจุดทศนิยม ให้ลบเลข 0 ที่อยู่ท้ายสุด และถ้าเหลือแต่จุดก็ลบจุดทิ้งด้วย
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return text

class InputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # --- 1. Measurement Type ---
        group_meas = QGroupBox("1. ประเภทการวัด (Measurement Type)")
        form_meas = QFormLayout()
        self.combo_prop_group = QComboBox()
        self.combo_prop_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_scpi_mode = QComboBox()
        self.combo_scpi_mode.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_meas.addRow("กลุ่มคุณสมบัติ:", self.combo_prop_group)
        form_meas.addRow("โหมดพารามิเตอร์:", self.combo_scpi_mode)
        group_meas.setLayout(form_meas)
        layout.addWidget(group_meas)

        # --- 2. Test Signal ---
        group_signal = QGroupBox("2. สัญญาณทดสอบ AC (Test Signal)")
        grid_signal = QGridLayout()
        
        # ใช้ SmartDoubleSpinBox และตั้งค่า SingleStep เป็น 100 สำหรับความถี่
        self.input_freq = SmartDoubleSpinBox()
        self.input_freq.setRange(20.0, 2000000.0)
        self.input_freq.setDecimals(2)
        self.input_freq.setSingleStep(100) 
        self.input_freq.setValue(100000.0)
        self.input_freq.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.input_volt = SmartDoubleSpinBox()
        self.input_volt.setRange(0.0001, 20.0)
        self.input_volt.setDecimals(3)
        self.input_volt.setSingleStep(0.1)
        self.input_volt.setValue(1.0)
        self.input_volt.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        grid_signal.addWidget(QLabel("ความถี่ (Hz):"), 0, 0)
        grid_signal.addWidget(self.input_freq, 1, 0)
        grid_signal.addWidget(QLabel("แรงดัน (Vrms):"), 0, 1)
        grid_signal.addWidget(self.input_volt, 1, 1)
        group_signal.setLayout(grid_signal)
        layout.addWidget(group_signal)

        # --- 3. Hardware & Timing ---
        group_hw = QGroupBox("3. ฮาร์ดแวร์และเวลา (Hardware & Timing)")
        grid_hw = QGridLayout()
        
        self.combo_time = QComboBox()
        self.combo_time.addItems(["SHORT", "MEDIUM", "LONG"])
        self.combo_time.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.input_avg = QSpinBox()
        self.input_avg.setRange(1, 256)
        self.input_avg.setValue(1)
        self.input_avg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.combo_range = QComboBox()
        self.combo_range.addItems(["AUTO", "HOLD"])
        self.combo_range.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.combo_cable = QComboBox()
        self.combo_cable.addItems(["0 m", "1 m", "2 m", "4 m"])
        self.combo_cable.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        grid_hw.addWidget(QLabel("เวลาวัด (TIME)"), 0, 0)
        grid_hw.addWidget(self.combo_time, 1, 0)
        grid_hw.addWidget(QLabel("ค่าเฉลี่ย (AVG)"), 0, 1)
        grid_hw.addWidget(self.input_avg, 1, 1)
        grid_hw.addWidget(QLabel("ย่าน (RANGE)"), 2, 0)
        grid_hw.addWidget(self.combo_range, 3, 0)
        grid_hw.addWidget(QLabel("สาย (CABLE)"), 2, 1)
        grid_hw.addWidget(self.combo_cable, 3, 1)
        group_hw.setLayout(grid_hw)
        layout.addWidget(group_hw)

        # --- 5. Sweep Settings ---
        self.group_sweep = QGroupBox("5. การสแกนความถี่ (Sweep Settings)")
        grid_sweep = QGridLayout()
        
        self.input_start_freq = SmartDoubleSpinBox()
        self.input_start_freq.setRange(20.0, 2000000.0)
        self.input_start_freq.setDecimals(2)
        self.input_start_freq.setSingleStep(100)
        self.input_start_freq.setValue(100.0)
        self.input_start_freq.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.input_stop_freq = SmartDoubleSpinBox()
        self.input_stop_freq.setRange(20.0, 2000000.0)
        self.input_stop_freq.setDecimals(2)
        self.input_stop_freq.setSingleStep(100)
        self.input_stop_freq.setValue(1000000.0)
        self.input_stop_freq.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.input_points = QSpinBox()
        self.input_points.setRange(2, 201)
        self.input_points.setValue(50)
        self.input_points.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        grid_sweep.addWidget(QLabel("START Freq"), 0, 0)
        grid_sweep.addWidget(self.input_start_freq, 1, 0)
        grid_sweep.addWidget(QLabel("STOP Freq"), 0, 1)
        grid_sweep.addWidget(self.input_stop_freq, 1, 1)
        grid_sweep.addWidget(QLabel("POINTS"), 0, 2)
        grid_sweep.addWidget(self.input_points, 1, 2)
        
        h_scale = QHBoxLayout()
        h_scale.addWidget(QLabel("สเกล (Scale):"))
        self.radio_log = QRadioButton("Log (ลอการิทึม)")
        self.radio_lin = QRadioButton("Linear (เชิงเส้น)")
        self.radio_log.setChecked(True)
        h_scale.addWidget(self.radio_log)
        h_scale.addWidget(self.radio_lin)
        h_scale.addStretch()
        grid_sweep.addLayout(h_scale, 2, 0, 1, 3)
        self.group_sweep.setLayout(grid_sweep)
        layout.addWidget(self.group_sweep)