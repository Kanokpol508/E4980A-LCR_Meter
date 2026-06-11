# หน้าต่างหลัก (ประกอบจิ๊กซอว์ทุก panel เข้าด้วยกัน)


from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                             QGroupBox, QLabel, QComboBox, QPushButton, 
                             QLineEdit, QRadioButton, QCheckBox, QScrollArea, QGridLayout, QFormLayout, QButtonGroup, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator, QDoubleValidator
import pyqtgraph as pg


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCR Metrology Software (E4980A/AL)")
        self.resize(1280, 720)

        # ========================================================
        # ตัวแปรสถานะข้อผิดพลาด (Error Flags) สำหรับระบบล็อกปุ่ม
        # ========================================================
        self.is_dc_error = False
        self.is_dev_error = False

        # ========================================================
        # ฐานข้อมูลตัวเลือกการวัด (Mapping Property Group -> SCPI)
        # ========================================================
        self.meas_options = {
            "Capacitance (ความจุไฟฟ้า)": [
                ("Cp-D", "CPD"), ("Cp-Q", "CPQ"), ("Cp-G", "CPG"), ("Cp-Rp", "CPRP"),
                ("Cs-D", "CSD"), ("Cs-Q", "CSQ"), ("Cs-Rs", "CSRS")
            ],
            "Inductance (ความเหนี่ยวนำ)": [
                ("Lp-D", "LPD"), ("Lp-Q", "LPQ"), ("Lp-G", "LPG"), ("Lp-Rp", "LPRP"), ("Lp-Rdc", "LPRD"),
                ("Ls-D", "LSD"), ("Ls-Q", "LSQ"), ("Ls-Rs", "LSRS"), ("Ls-Rdc", "LSRD")
            ],
            "Impedance (อิมพีแดนซ์)": [
                ("R-X", "RX"), ("Z-θd", "ZTD"), ("Z-θr", "ZTR")
            ],
            "Admittance (แอดมิตแทนซ์)": [
                ("G-B", "GB"), ("Y-θd", "YTD"), ("Y-θr", "YTR")
            ],
            "DC Measurement (ต้องมี Option 001)": [
                ("Vdc-Idc", "VDID")
            ]
        }

        # วิดเจ็ตหลัก (Main Widget)
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        

        # ========================================================
        # [ ฝั่งซ้าย ] : คอนเทนเนอร์หลักฝั่งซ้าย
        # ========================================================
        left_panel_container = QWidget()
        left_panel_container.setMinimumWidth(400)
        left_panel_container.setMaximumWidth(450)
        left_main_layout = QVBoxLayout(left_panel_container)
        left_main_layout.setContentsMargins(0, 0, 0, 0)

        # 1. แผงตั้งค่าแบบเลื่อนได้ (Scrollable Input Panel)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        
        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        
        # --- VISA Resource ---
        group_visa = QGroupBox("VISA Resource")
        h_visa = QHBoxLayout()
        self.combo_visa = QComboBox()
        self.combo_visa.addItem("No Device Found")
        self.combo_visa.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_refresh = QPushButton("REFRESH")
        h_visa.addWidget(self.combo_visa, stretch=1)
        h_visa.addWidget(self.btn_refresh)
        group_visa.setLayout(h_visa)
        left_layout.addWidget(group_visa)
        
        # --- 1. Measurement Type ---
        group_meas = QGroupBox("1. ประเภทการวัด (Measurement Type)")
        form_meas = QFormLayout()
        
        self.combo_prop_group = QComboBox()
        self.combo_prop_group.addItems(self.meas_options.keys())
        self.combo_prop_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.combo_scpi_mode = QComboBox()
        self.combo_scpi_mode.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        form_meas.addRow("กลุ่มคุณสมบัติ:", self.combo_prop_group)
        form_meas.addRow("โหมดพารามิเตอร์:", self.combo_scpi_mode)
        group_meas.setLayout(form_meas)
        left_layout.addWidget(group_meas)

        self.combo_prop_group.currentIndexChanged.connect(self.update_scpi_modes)
        self.update_scpi_modes()

        # --- 2. Test Signal ---
        group_signal = QGroupBox("2. สัญญาณทดสอบ AC (Test Signal)")
        grid_signal = QGridLayout()
        grid_signal.setColumnStretch(0, 1)
        grid_signal.setColumnStretch(1, 1)
        grid_signal.addWidget(QLabel("ความถี่ (Hz):"), 0, 0)
        self.input_freq = QLineEdit("100000")
        grid_signal.addWidget(self.input_freq, 1, 0)
        
        grid_signal.addWidget(QLabel("แรงดัน (Vrms):"), 0, 1)
        self.input_volt = QLineEdit("1.0")
        grid_signal.addWidget(self.input_volt, 1, 1)
        group_signal.setLayout(grid_signal)
        left_layout.addWidget(group_signal)

        # --- 3. Hardware & Timing ---
        group_hw = QGroupBox("3. ฮาร์ดแวร์และเวลา (Hardware & Timing)")
        grid_hw = QGridLayout()
        grid_hw.setColumnStretch(0, 1)
        grid_hw.setColumnStretch(1, 1)
        
        self.combo_time = QComboBox()
        self.combo_time.addItems(["SHORT", "MEDIUM", "LONG"])
        self.combo_time.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.input_avg = QLineEdit("1")
        self.input_avg.setValidator(QIntValidator(1, 256))
        
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
        left_layout.addWidget(group_hw)

        # --- 4. Correction ---
        group_corr = QGroupBox("4. การปรับชดเชยค่าสายวัด (Correction)")
        h_corr = QHBoxLayout()
        self.btn_open_corr = QPushButton("OPEN Correction")
        self.btn_short_corr = QPushButton("SHORT Correction")
        h_corr.addWidget(self.btn_open_corr)
        h_corr.addWidget(self.btn_short_corr)
        group_corr.setLayout(h_corr)
        left_layout.addWidget(group_corr)

        # --- 5. Sweep Settings ---
        self.group_sweep = QGroupBox("5. การสแกนความถี่ (Sweep Settings)")
        grid_sweep = QGridLayout()
        grid_sweep.setColumnStretch(0, 1)
        grid_sweep.setColumnStretch(1, 1)
        grid_sweep.setColumnStretch(2, 1)
        self.input_start_freq = QLineEdit("100")
        self.input_stop_freq = QLineEdit("1000000")
        self.input_points = QLineEdit("50")
        
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
        left_layout.addWidget(self.group_sweep)

        # --- 6. DC Bias ---
        self.group_dc = QGroupBox("6. ไฟตรง (DC BIAS)")
        v_dc = QVBoxLayout()
        v_dc.setSpacing(10)
        
        h_enable = QHBoxLayout()
        h_enable.addStretch()
        self.chk_dc_enable = QCheckBox("เปิดใช้งาน")
        h_enable.addWidget(self.chk_dc_enable)
        v_dc.addLayout(h_enable)

        self.widget_dc_inner = QWidget()
        v_dc_inner = QVBoxLayout(self.widget_dc_inner)
        v_dc_inner.setContentsMargins(0, 0, 0, 0)
        v_dc_inner.setSpacing(10)

        h_va = QHBoxLayout()
        h_va.setSpacing(0)
        self.dc_btn_group = QButtonGroup()
        
        self.btn_dc_v = QPushButton("Voltage Bias (V)")
        self.btn_dc_a = QPushButton("Current Bias (A)")
        self.btn_dc_v.setCheckable(True)
        self.btn_dc_a.setCheckable(True)
        self.btn_dc_v.setChecked(True)
        
        self.dc_btn_group.addButton(self.btn_dc_v)
        self.dc_btn_group.addButton(self.btn_dc_a)
        
        h_va.addWidget(self.btn_dc_v)
        h_va.addWidget(self.btn_dc_a)
        v_dc_inner.addLayout(h_va)

        lbl_level = QLabel("ระดับไฟตรง (LEVEL)")
        v_dc_inner.addWidget(lbl_level)
        
        h_level = QHBoxLayout()
        h_level.setSpacing(0)
        
        self.input_dc_level = QLineEdit("1.5")
        self.input_dc_level.setValidator(QDoubleValidator())
        
        self.lbl_dc_unit = QLabel("V")
        self.lbl_dc_unit.setFixedWidth(40)
        self.lbl_dc_unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.chk_opt001 = QCheckBox("เปิดใช้งาน Option 001 (ขยายขอบเขต DC Bias)")
        
        h_level.addWidget(self.input_dc_level)
        h_level.addWidget(self.lbl_dc_unit)
        h_level.addSpacing(20)                          # เว้นระยะห่างระหว่างช่องตัวเลขกับ Checkbox
        h_level.addWidget(self.chk_opt001)
        
        v_dc_inner.addLayout(h_level)

        self.lbl_dc_warning = QLabel("⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!")
        self.lbl_dc_warning.setWordWrap(True)
        v_dc_inner.addWidget(self.lbl_dc_warning)

        v_dc.addWidget(self.widget_dc_inner)
        self.group_dc.setLayout(v_dc)
        left_layout.addWidget(self.group_dc)

        # --- 7. Deviation ---
        self.group_dev = QGroupBox("7. เบี่ยงเบน (DEVIATION)")
        v_dev = QVBoxLayout()
        v_dev.setSpacing(10)

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
        grid_dev_refs.setColumnStretch(0, 1)
        grid_dev_refs.setColumnStretch(1, 1)
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
        left_layout.addWidget(self.group_dev)

        left_layout.addStretch(1)
        left_scroll.setWidget(left_content)
        
        # นำ Scroll area ใส่ใน Container ด้านซ้าย
        left_main_layout.addWidget(left_scroll, stretch=1)

        # ========================================================
        # 2. โซนปุ่มควบคุมการรัน (Run Zone) ถูกล็อคตายตัวด้านล่างสุดของฝั่งซ้าย
        # ========================================================
        v_run_zone = QVBoxLayout()
        v_run_zone.setContentsMargins(0, 10, 0, 0)
        v_run_zone.setSpacing(5)

        # จัด Layout ส่วนปุ่ม Start/Stop แบบตารางเพื่อให้ขนาดเท่ากัน 50:50
        grid_run = QGridLayout()
        grid_run.setColumnStretch(0, 1)
        grid_run.setColumnStretch(1, 1)
        grid_run.setVerticalSpacing(5)

        # ปุ่มสลับโหมด Single / Sweep
        h_run_mode = QHBoxLayout()
        h_run_mode.setSpacing(0)
        self.btn_mode_single = QPushButton("วัดจุดเดียว")
        self.btn_mode_sweep = QPushButton("สแกนความถี่")
        self.btn_mode_single.setCheckable(True)
        self.btn_mode_sweep.setCheckable(True)
        self.btn_mode_sweep.setChecked(True)
        
        self.run_mode_group = QButtonGroup()
        self.run_mode_group.addButton(self.btn_mode_single)
        self.run_mode_group.addButton(self.btn_mode_sweep)
        
        h_run_mode.addWidget(self.btn_mode_single)
        h_run_mode.addWidget(self.btn_mode_sweep)
        grid_run.addLayout(h_run_mode, 0, 0)

        # ปุ่ม START และ STOP
        self.btn_start = QPushButton("START")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.btn_start.setMinimumHeight(60)
        
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.btn_stop.setMinimumHeight(60)
        
        grid_run.addWidget(self.btn_start, 1, 0)
        grid_run.addWidget(self.btn_stop, 1, 1)

        # ป้ายแจ้งเตือนข้อผิดพลาดใต้ปุ่ม START
        self.lbl_warn_dc_start = QLabel("⚠️ ตั้งค่า DC Bias ไม่ถูกต้อง")
        self.lbl_warn_dev_start = QLabel("⚠️ ต้องกรอก Primary Ref ก่อน")
        self.lbl_warn_dc_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_dev_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_dc_start.setVisible(False)
        self.lbl_warn_dev_start.setVisible(False)
        
        v_warn = QVBoxLayout()
        v_warn.addWidget(self.lbl_warn_dc_start)
        v_warn.addWidget(self.lbl_warn_dev_start)
        grid_run.addLayout(v_warn, 2, 0)

        v_run_zone.addLayout(grid_run)
        
        left_main_layout.addLayout(v_run_zone, stretch=0)
        main_layout.addWidget(left_panel_container)


        # ========================================================
        # [ ฝั่งขวา ] : แผงแสดงผล (Output)
        # ========================================================
        right_layout = QVBoxLayout()
        
        # --- 1. กราฟพารามิเตอร์หลัก (Primary Graph) ---
        self.plot_primary = pg.PlotWidget(title="กราฟ Primary")
        self.plot_primary.showGrid(x=True, y=True)
        right_layout.addWidget(self.plot_primary, stretch=2)

        # --- 2. กราฟพารามิเตอร์รอง (Secondary Graph) ---
        self.plot_secondary = pg.PlotWidget(title="กราฟ Secondary")
        self.plot_secondary.showGrid(x=True, y=True)
        right_layout.addWidget(self.plot_secondary, stretch=2)

        # --- 3. โซนแสดงผลด้านล่างสุด (หน้าจอ LCD + ปุ่มเครื่องมือ) ---
        h_bottom_right = QHBoxLayout()

        # หน้าจอแสดงผลลัพธ์ (LCD Results) อยู่ฝั่งซ้าย
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
        
        h_bottom_right.addWidget(group_lcd, stretch=1)

        # ปุ่มเครื่องมือ 3 ปุ่ม เรียงแนวตั้งอยู่ฝั่งขวาของกรอบ LCD
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
        
        h_bottom_right.addLayout(v_tools)

        right_layout.addLayout(h_bottom_right)
        
        # นำแผงขวาเข้า Main Layout
        main_layout.addLayout(right_layout)

        # ========================================================
        # [ ผูกคำสั่ง Event เริ่มต้น ]
        # ========================================================
        
        # DC Bias Events
        self.widget_dc_inner.setEnabled(False)
        self.chk_dc_enable.stateChanged.connect(self.toggle_dc_bias)
        self.chk_opt001.stateChanged.connect(self.validate_dc_bias)
        self.btn_dc_v.toggled.connect(self.validate_dc_bias)
        self.input_dc_level.textChanged.connect(self.validate_dc_bias)

        # Deviation Events
        self.widget_dev_inner.setEnabled(False)
        self.chk_dev_enable.stateChanged.connect(self.toggle_deviation)
        self.input_dev_pri.textChanged.connect(self.validate_deviation)

        # Run Mode Events
        self.btn_mode_single.toggled.connect(self.toggle_run_mode)

    # ========================================================
    # ฟังก์ชันเสริมสำหรับจัดการ UI (UI Logic Methods)
    # ========================================================
    def update_scpi_modes(self):
        """อัปเดตรายการใน Dropdown 'โหมดพารามิเตอร์'"""
        self.combo_scpi_mode.clear()
        
        selected_group = self.combo_prop_group.currentText()
        modes = self.meas_options.get(selected_group, [])
        
        for display_text, scpi_code in modes:
            self.combo_scpi_mode.addItem(f"{scpi_code} ({display_text})", userData=scpi_code)

    def update_start_button_state(self):
        """ระบบ Interlock สำหรับล็อกปุ่ม START และแสดงป้ายเตือน"""
        is_blocked = self.is_dc_error or self.is_dev_error

        self.lbl_warn_dc_start.setVisible(self.is_dc_error)
        self.lbl_warn_dev_start.setVisible(self.is_dev_error)

        if is_blocked:
            self.btn_start.setText("🔒 BLOCKED")
            self.btn_start.setEnabled(False)
        else:
            self.btn_start.setText("START")
            self.btn_start.setEnabled(True)

    def toggle_run_mode(self):
        """เปิด-ปิด การป้อนข้อมูล Sweep ตามโหมดการทำงาน"""
        is_sweep = self.btn_mode_sweep.isChecked()
        
        # ปิดช่องกรอก 5. Sweep Settings ถ้าเลือกวัดจุดเดียว
        self.input_start_freq.setEnabled(is_sweep)
        self.input_stop_freq.setEnabled(is_sweep)
        self.input_points.setEnabled(is_sweep)
        self.radio_log.setEnabled(is_sweep)
        self.radio_lin.setEnabled(is_sweep)
        
        self.update_start_button_state()


    # ---------------- DC Bias Logic ----------------
    def toggle_dc_bias(self):
        is_enabled = self.chk_dc_enable.isChecked()
        self.widget_dc_inner.setEnabled(is_enabled)
        
        if is_enabled:
            self.validate_dc_bias()
        else:
            self.lbl_dc_warning.setText("⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!")
            self.is_dc_error = False
            self.update_start_button_state()

    def validate_dc_bias(self):
        if not self.chk_dc_enable.isChecked():
            self.is_dc_error = False
            self.update_start_button_state()
            return

        is_voltage = self.btn_dc_v.isChecked()
        self.lbl_dc_unit.setText("V" if is_voltage else "A")
        
        warning_msg = "⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!"
        self.is_dc_error = False
        
        try:
            val = float(self.input_dc_level.text())
        except ValueError:
            warning_msg = "⚠️ กรุณาป้อนตัวเลขให้ถูกต้อง"
            self.is_dc_error = True
            val = None
            
        has_opt = self.chk_opt001.isChecked()
        
        if val is not None:
            if not is_voltage: 
                if not has_opt:
                    warning_msg = "⚠️ ไม่รองรับ! ต้องติ๊ก Option 001 ก่อนถึงจะใช้กระแส (Current Bias) ได้"
                    self.is_dc_error = True
                elif val < -0.1 or val > 0.1:
                    warning_msg = "⚠️ กระแสเกินฮาร์ดแวร์! รองรับสูงสุด -0.1A ถึง +0.1A (100 mA)"
                    self.is_dc_error = True
            else: 
                if not has_opt:
                    if val not in [0.0, 1.5, 2.0]:
                        warning_msg = "⚠️ เครื่องรุ่นปกติปรับแรงดันได้แค่ 0, 1.5 หรือ 2.0 V เท่านั้น"
                        self.is_dc_error = True
                else:
                    if val < -40.0 or val > 40.0:
                        warning_msg = "⚠️ แรงดันเกินขีดจำกัด! Option 001 รองรับ -40.0 V ถึง +40.0 V"
                        self.is_dc_error = True
            
        self.lbl_dc_warning.setText(warning_msg)
        self.update_start_button_state()


    # ---------------- Deviation Logic ----------------
    def toggle_deviation(self):
        is_enabled = self.chk_dev_enable.isChecked()
        self.widget_dev_inner.setEnabled(is_enabled)
        
        if is_enabled:
            self.validate_deviation()
        else:
            self.lbl_dev_warning.setText("")
            self.is_dev_error = False
            self.update_start_button_state()

    def validate_deviation(self):
        if not self.chk_dev_enable.isChecked():
            self.is_dev_error = False
            self.update_start_button_state()
            return

        pri_text = self.input_dev_pri.text().strip()
        if not pri_text:
            self.lbl_dev_warning.setText("⚠️ ต้องระบุ Primary Reference (หลัก) ก่อนเริ่มวัด")
            self.is_dev_error = True
        else:
            try:
                float(pri_text)
                self.lbl_dev_warning.setText("")
                self.is_dev_error = False
            except ValueError:
                self.lbl_dev_warning.setText("⚠️ กรุณาป้อนตัวเลขให้ถูกต้อง เช่น 100E-9")
                self.is_dev_error = True

        self.update_start_button_state()