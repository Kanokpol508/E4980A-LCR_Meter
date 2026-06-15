# หน้าต่างหลัก (ประกอบจิ๊กซอว์ทุก panel เข้าด้วยกัน)


from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QMessageBox
from PyQt6.QtCore import Qt, QLocale

from core.measurement_thread import MeasurementWorker
from hardware.lcr_meter import E4980A

# นำเข้าชิ้นส่วน UI ที่เราแยกไฟล์ไว้ (Panels & Displays)
from gui.panels.connection_panel import ConnectionPanel
from gui.panels.input_panel import InputPanel
from gui.panels.advanced_panel import AdvancedPanel
from gui.panels.control_panel import ControlPanel
from gui.displays.graph_display import GraphDisplay
from gui.displays.lcd_display import LcdDisplay

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LCR Metrology Software (E4980A/AL)")
        self.resize(1280, 720)
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

        # ตัวแปรสถานะ
        self.is_dc_error = False
        self.is_dev_error = False
        self.is_visa_error = True
        self.worker = None

        self.meas_options = {
            "Capacitance (ความจุไฟฟ้า)": [
                ("Cp-D", "CPD"), ("Cp-Q", "CPQ"), ("Cp-G", "CPG"), ("Cp-Rp", "CPRP"),
                ("Cs-D", "CSD"), ("Cs-Q", "CSQ"), ("Cs-Rs", "CSRS")
            ],
            "Inductance (ความเหนี่ยวนำ)": [
                ("Lp-D", "LPD"), ("Lp-Q", "LPQ"), ("Lp-G", "LPG"), ("Lp-Rp", "LPRP"), ("Lp-Rdc", "LPRD"),
                ("Ls-D", "LSD"), ("Ls-Q", "LSQ"), ("Ls-Rs", "LSRS"), ("Ls-Rdc", "LSRD")
            ],
            "Impedance (อิมพีแดนซ์)": [("R-X", "RX"), ("Z-θd", "ZTD"), ("Z-θr", "ZTR")],
            "Admittance (แอดมิตแทนซ์)": [("G-B", "GB"), ("Y-θd", "YTD"), ("Y-θr", "YTR")],
            "DC Measurement (ต้องมี Option 001)": [("Vdc-Idc", "VDID")]
        }

        # ประกอบ UI ร่างหลัก
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # ----------------------------------------------------
        # โซนฝั่งซ้าย (Left Layout)
        # ----------------------------------------------------
        left_panel_container = QWidget()
        left_panel_container.setMinimumWidth(450)
        left_panel_container.setMaximumWidth(500)
        left_main_layout = QVBoxLayout(left_panel_container)
        left_main_layout.setContentsMargins(0, 0, 0, 0)

        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.left_content = QWidget()
        left_layout = QVBoxLayout(self.left_content)
        
        # ดึงจิ๊กซอว์ Panels มาประกอบ
        self.conn_panel = ConnectionPanel()
        self.input_panel = InputPanel()
        self.adv_panel = AdvancedPanel()
        self.ctrl_panel = ControlPanel()

        left_layout.addWidget(self.conn_panel)
        left_layout.addWidget(self.input_panel)
        left_layout.addWidget(self.adv_panel)
        left_layout.addStretch(1)
        
        self.left_scroll.setWidget(self.left_content)
        left_main_layout.addWidget(self.left_scroll, stretch=1)
        left_main_layout.addWidget(self.ctrl_panel, stretch=0)
        
        main_layout.addWidget(left_panel_container)

        # ----------------------------------------------------
        # โซนฝั่งขวา (Right Layout)
        # ----------------------------------------------------
        right_layout = QVBoxLayout()
        
        self.graph_display = GraphDisplay()
        self.lcd_display = LcdDisplay()
        
        right_layout.addWidget(self.graph_display, stretch=1)
        right_layout.addWidget(self.lcd_display, stretch=0)
        
        main_layout.addLayout(right_layout)

        # ----------------------------------------------------
        # การผูก Event Signals
        # ----------------------------------------------------
        self.input_panel.combo_prop_group.currentIndexChanged.connect(self.update_scpi_modes)
        
        self.conn_panel.btn_refresh.clicked.connect(self.scan_visa_ports)
        self.conn_panel.combo_visa.currentTextChanged.connect(self.validate_visa)

        self.adv_panel.widget_dc_inner.setEnabled(False)
        self.adv_panel.chk_dc_enable.stateChanged.connect(self.toggle_dc_bias)
        self.adv_panel.chk_opt001.stateChanged.connect(self.validate_dc_bias)
        self.adv_panel.btn_dc_v.toggled.connect(self.validate_dc_bias)
        self.adv_panel.input_dc_level.valueChanged.connect(self.validate_dc_bias)

        self.adv_panel.widget_dev_inner.setEnabled(False)
        self.adv_panel.chk_dev_enable.stateChanged.connect(self.toggle_deviation)
        self.adv_panel.input_dev_pri.textChanged.connect(self.validate_deviation)

        self.ctrl_panel.btn_mode_single.toggled.connect(self.toggle_run_mode)
        
        self.ctrl_panel.btn_start.clicked.connect(self.start_measurement)
        self.ctrl_panel.btn_stop.clicked.connect(self.stop_measurement)

        # รันตอนเปิดโปรแกรมครั้งแรก
        self.input_panel.combo_prop_group.addItems(self.meas_options.keys())
        self.update_scpi_modes()
        self.scan_visa_ports()

    # ========================================================
    # Logic Methods (อัปเดตการอ้างอิง object ให้ถูกต้อง)
    # ========================================================
    def scan_visa_ports(self):
        self.conn_panel.combo_visa.clear()
        resources = E4980A.scan_ports()
        if resources:
            self.conn_panel.combo_visa.addItems(resources)
        else:
            self.conn_panel.combo_visa.addItem("No Device Found")
        self.validate_visa()

    def set_ui_locked(self, locked: bool):
        self.left_content.setEnabled(not locked)
        self.ctrl_panel.btn_mode_single.setEnabled(not locked)
        self.ctrl_panel.btn_mode_sweep.setEnabled(not locked)
        self.ctrl_panel.btn_stop.setEnabled(locked)
        if locked:
            self.ctrl_panel.btn_start.setEnabled(False)
            self.ctrl_panel.btn_start.setText("⏳ RUNNING...")
        else:
            self.ctrl_panel.btn_start.setText("START")
            self.ctrl_panel.btn_stop.setText("STOP")
            self.update_start_button_state()

    def start_measurement(self):
        settings = {
            'run_mode': 'SWEEP' if self.ctrl_panel.btn_mode_sweep.isChecked() else 'SINGLE',
            'visa_resource': self.conn_panel.combo_visa.currentText(),
            'freq': self.input_panel.input_freq.value(),
            'start_freq': self.input_panel.input_start_freq.value(),
            'stop_freq': self.input_panel.input_stop_freq.value(),
            'sweep_points': self.input_panel.input_points.value(),
            'sweep_scale': 'LOG' if self.input_panel.radio_log.isChecked() else 'LIN',
            'scpi_mode': self.input_panel.combo_scpi_mode.currentData(),
            'volt': self.input_panel.input_volt.value(),
            'time_mode': self.input_panel.combo_time.currentText(),
            'avg': self.input_panel.input_avg.value(),
            'cable': self.input_panel.combo_cable.currentText(),
            'imp_range': self.input_panel.combo_range.currentText(),
        }
        
        self.worker = MeasurementWorker(settings)
        self.worker.data_ready.connect(self.handle_data_ready)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.progress_updated.connect(self.handle_progress_update)
        self.worker.finished.connect(self.handle_worker_finished)
        
        self.set_ui_locked(True)
        
        self.lcd_display.lbl_pri_val.setText("Measuring...")
        self.lcd_display.lbl_sec_val.setText("Measuring...")
        
        self.worker.start()

    def stop_measurement(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop() 
            self.ctrl_panel.btn_stop.setText("STOPPING...")
            self.ctrl_panel.btn_stop.setEnabled(False) 

    def handle_data_ready(self, data):
        self.lcd_display.lbl_pri_val.setText(f"{data.get('primary', 0.0):.5e}")
        self.lcd_display.lbl_sec_val.setText(f"{data.get('secondary', 0.0):.5e}")

    def handle_worker_error(self, error_msg):
        QMessageBox.critical(self, "Hardware Error", error_msg)

    def handle_progress_update(self, percent):
        if self.ctrl_panel.btn_mode_sweep.isChecked():
            self.ctrl_panel.btn_start.setText(f"⏳ SWEEPING... {percent}%")

    def handle_worker_finished(self):
        self.set_ui_locked(False) 
        self.worker = None

    def validate_visa(self):
        text = self.conn_panel.combo_visa.currentText()
        self.is_visa_error = (text == "No Device Found" or text.strip() == "")
        self.update_start_button_state()

    def update_scpi_modes(self):
        self.input_panel.combo_scpi_mode.clear()
        selected_group = self.input_panel.combo_prop_group.currentText()
        modes = self.meas_options.get(selected_group, [])
        for display_text, scpi_code in modes:
            self.input_panel.combo_scpi_mode.addItem(f"{scpi_code} ({display_text})", userData=scpi_code)

    def update_start_button_state(self):
        is_blocked = self.is_dc_error or self.is_dev_error or self.is_visa_error

        self.ctrl_panel.lbl_warn_visa.setVisible(self.is_visa_error)
        self.ctrl_panel.lbl_warn_dc_start.setVisible(self.is_dc_error)
        self.ctrl_panel.lbl_warn_dev_start.setVisible(self.is_dev_error)

        if is_blocked:
            self.ctrl_panel.btn_start.setText("🔒 BLOCKED")
            self.ctrl_panel.btn_start.setEnabled(False)
        else:
            self.ctrl_panel.btn_start.setText("START")
            self.ctrl_panel.btn_start.setEnabled(True)

    def toggle_run_mode(self):
        is_sweep = self.ctrl_panel.btn_mode_sweep.isChecked()
        self.input_panel.input_start_freq.setEnabled(is_sweep)
        self.input_panel.input_stop_freq.setEnabled(is_sweep)
        self.input_panel.input_points.setEnabled(is_sweep)
        self.input_panel.radio_log.setEnabled(is_sweep)
        self.input_panel.radio_lin.setEnabled(is_sweep)
        self.update_start_button_state()

    def toggle_dc_bias(self):
        is_enabled = self.adv_panel.chk_dc_enable.isChecked()
        self.adv_panel.widget_dc_inner.setEnabled(is_enabled)
        if is_enabled:
            self.validate_dc_bias()
        else:
            self.adv_panel.lbl_dc_warning.setText("⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!")
            self.is_dc_error = False
            self.update_start_button_state()

    def validate_dc_bias(self):
        if not self.adv_panel.chk_dc_enable.isChecked():
            self.is_dc_error = False
            self.update_start_button_state()
            return

        is_voltage = self.adv_panel.btn_dc_v.isChecked()
        self.adv_panel.lbl_dc_unit.setText("V" if is_voltage else "A")
        
        warning_msg = "⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!"
        self.is_dc_error = False
        val = self.adv_panel.input_dc_level.value()
        has_opt = self.adv_panel.chk_opt001.isChecked()
        
        if not is_voltage: 
            if not has_opt:
                warning_msg = "⚠️ ไม่รองรับ! ต้องติ๊ก Option 001 ก่อนถึงจะใช้กระแส (Current Bias) ได้"
                self.is_dc_error = True
            elif val < -0.1 or val > 0.1:
                warning_msg = "⚠️ กระแสเกินฮาร์ดแวร์! รองรับสูงสุด -0.1A ถึง +0.1A (100 mA)"
                self.is_dc_error = True
        else: 
            if not has_opt:
                DISCRETE = [0.0, 1.5, 2.0]
                TOLERANCE = 1e-9
                if not any(abs(val - v) < TOLERANCE for v in DISCRETE):
                    warning_msg = "⚠️ เครื่องรุ่นปกติปรับแรงดันได้แค่ 0, 1.5 หรือ 2.0 V เท่านั้น"
                    self.is_dc_error = True
            else:
                if val < -40.0 or val > 40.0:
                    warning_msg = "⚠️ แรงดันเกินขีดจำกัด! Option 001 รองรับ -40.0 V ถึง +40.0 V"
                    self.is_dc_error = True
            
        self.adv_panel.lbl_dc_warning.setText(warning_msg)
        self.update_start_button_state()

    def toggle_deviation(self):
        is_enabled = self.adv_panel.chk_dev_enable.isChecked()
        self.adv_panel.widget_dev_inner.setEnabled(is_enabled)
        if is_enabled:
            self.validate_deviation()
        else:
            self.adv_panel.lbl_dev_warning.setText("")
            self.is_dev_error = False
            self.update_start_button_state()

    def validate_deviation(self):
        if not self.adv_panel.chk_dev_enable.isChecked():
            self.is_dev_error = False
            self.update_start_button_state()
            return
        pri_text = self.adv_panel.input_dev_pri.text().strip()
        if not pri_text:
            self.adv_panel.lbl_dev_warning.setText("⚠️ ต้องระบุ Primary Reference (หลัก) ก่อนเริ่มวัด")
            self.is_dev_error = True
        else:
            try:
                float(pri_text)
                self.adv_panel.lbl_dev_warning.setText("")
                self.is_dev_error = False
            except ValueError:
                self.adv_panel.lbl_dev_warning.setText("⚠️ กรุณาป้อนตัวเลขให้ถูกต้อง เช่น 100E-9")
                self.is_dev_error = True
        self.update_start_button_state()