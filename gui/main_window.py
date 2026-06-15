# หน้าต่างหลัก (ประกอบจิ๊กซอว์ทุก panel เข้าด้วยกัน)


from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, QLocale

from core.measurement_thread import MeasurementWorker
from core.correction_thread import CorrectionWorker
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
        self.corr_worker = None         
        self.progress_dialog = None     

        # ตัวแปรสำหรับเก็บข้อมูลวาดกราฟ
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []

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

        # ผูกปุ่ม OPEN / SHORT Correction (แก้ไขชื่อตัวแปรให้ตรงกับ AdvancedPanel)
        self.adv_panel.btn_open_corr.clicked.connect(lambda: self.start_correction("OPEN"))
        self.adv_panel.btn_short_corr.clicked.connect(lambda: self.start_correction("SHORT"))

        self.ctrl_panel.btn_mode_single.toggled.connect(self.toggle_run_mode)
        self.ctrl_panel.btn_start.clicked.connect(self.start_measurement)
        self.ctrl_panel.btn_stop.clicked.connect(self.stop_measurement)
        self.ctrl_panel.btn_clear_graph.clicked.connect(self.handle_clear_graph)

        self.input_panel.combo_prop_group.addItems(self.meas_options.keys())
        self.update_scpi_modes()
        self.scan_visa_ports()

    # ========================================================
    # ระบบ Correction (OPEN / SHORT)
    # ========================================================
    def start_correction(self, corr_type: str):
        """เริ่มกระบวนการชดเชยสายวัด พร้อมโชว์ Loading"""
        visa_address = self.conn_panel.combo_visa.currentText()
        if not visa_address or visa_address == "No Device Found":
            QMessageBox.warning(self, "เชื่อมต่อล้มเหลว", "กรุณาเชื่อมต่อเครื่อง LCR Meter ก่อนทำการชดเชยค่า")
            return

        # 1. ยืนยันสถานะสายวัดจากผู้ใช้ก่อนสั่งเครื่อง
        msg = ("กรุณาแยกสายวัดออกจากกัน (ปลดชิ้นงานออก)" if corr_type == "OPEN" 
               else "กรุณานำสายวัดมาแตะช็อตกัน (ใช้แผ่น Shorting Plate)")
        
        reply = QMessageBox.question(
            self, f"เตรียมความพร้อม {corr_type} Correction", 
            f"{msg}\n\nคุณพร้อมที่จะเริ่มทำการชดเชยค่าหรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 2. ล็อกหน้าจอระหว่างทำ
        self.set_ui_locked(True)
        self.ctrl_panel.btn_stop.setEnabled(False)       # ห้ามกด Stop ระหว่างแก้ Correction

        # 3. โชว์หน้าต่างโหลดแบบไม่สิ้นสุด (0-0)
        self.progress_dialog = QProgressDialog(
            f"เครื่องกำลังทำงาน {corr_type} Correction...\n(อาจใช้เวลา 15 - 60 วินาที กรุณาห้ามถอดสาย)", 
            "กำลังประมวลผล...", 0, 0, self
        )
        self.progress_dialog.setWindowTitle(f"{corr_type} Correction")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None)      # เอาปุ่มยกเลิกออก เพราะฮาร์ดแวร์กำลังรอข้อมูล
        self.progress_dialog.show()

        # 4. โยนงานให้ Worker ตัวใหม่ทำ
        self.corr_worker = CorrectionWorker(visa_address, corr_type)
        self.corr_worker.finished_signal.connect(self.handle_correction_finished)
        self.corr_worker.start()

    def handle_correction_finished(self, success: bool, msg: str):
        """รับผลลัพธ์จาก Thread ว่าทำ Correction สำเร็จหรือไม่"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.set_ui_locked(False)           # ปลดล็อกหน้าจอ
        self.corr_worker = None

        if success:
            QMessageBox.information(self, "Correction สำเร็จ", f"✅ {msg}")
        else:
            QMessageBox.critical(self, "Correction ล้มเหลว", f"❌ {msg}")


    # ========================================================
    # Logic Methods (ระบบอื่นๆ)
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
        self.ctrl_panel.btn_clear_graph.setEnabled(not locked) 
        self.ctrl_panel.btn_stop.setEnabled(locked)
        if locked:
            self.ctrl_panel.btn_start.setEnabled(False)
            self.ctrl_panel.btn_start.setText("⏳ RUNNING...")
        else:
            self.ctrl_panel.btn_start.setText("START")
            self.ctrl_panel.btn_stop.setText("STOP")
            self.update_start_button_state()
            self.update_session_lock()

    def handle_clear_graph(self):
        reply = QMessageBox.question(
            self, 'ยืนยันการล้างข้อมูล', "คุณต้องการล้างข้อมูลและรีเซ็ตกราฟใช่หรือไม่?\n(ข้อมูลที่ยังไม่ถูกบันทึกจะหายไป)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_graph_data()

    def setup_graph_labels(self):
        scpi_mode = self.input_panel.combo_scpi_mode.currentData()
        pri_label = "Primary"
        sec_label = "Secondary"
        
        if scpi_mode.startswith("CP"): pri_label = "Capacitance, Cp (F)"
        elif scpi_mode.startswith("CS"): pri_label = "Capacitance, Cs (F)"
        elif scpi_mode.startswith("LP"): pri_label = "Inductance, Lp (H)"
        elif scpi_mode.startswith("LS"): pri_label = "Inductance, Ls (H)"
        elif scpi_mode == "RX": pri_label = "Resistance, R (Ω)"
        elif scpi_mode.startswith("Z"): pri_label = "Impedance, Z (Ω)"
        elif scpi_mode.startswith("Y") or scpi_mode == "GB": pri_label = "Admittance (S)"
        elif scpi_mode == "VDID": pri_label = "DC Voltage (V)"
        
        if scpi_mode.endswith("D"): sec_label = "Dissipation Factor, D"
        elif scpi_mode.endswith("Q"): sec_label = "Quality Factor, Q"
        elif scpi_mode.endswith("RS") or scpi_mode.endswith("RP") or scpi_mode.endswith("RD") or scpi_mode == "RX": sec_label = "Resistance (Ω)"
        elif "T" in scpi_mode: sec_label = "Phase Angle, θ (°)"
        elif scpi_mode == "VDID": sec_label = "DC Current (A)"
        
        if self.adv_panel.chk_dev_enable.isChecked():
            dev_type = self.adv_panel.combo_dev_type.currentText()
            if "PCT" in dev_type or "เปอร์เซ็นต์" in dev_type:
                pri_label = f"Δ {pri_label.split(',')[0]} (%)"
                sec_label = f"Δ {sec_label.split(',')[0]} (%)"
            else:
                pri_label = f"Δ {pri_label}"
                sec_label = f"Δ {sec_label}"

        is_sweep = self.ctrl_panel.btn_mode_sweep.isChecked()
        is_log = self.input_panel.radio_log.isChecked() if is_sweep else False
        x_label = "Frequency (Hz)" if is_sweep else "Measurement Count (Points)"
        
        self.graph_display.set_axis_labels(x_label=x_label, pri_y_label=pri_label, sec_y_label=sec_label, is_log_x=is_log, is_single_mode=not is_sweep)

    def start_measurement(self):
        is_sweep = self.ctrl_panel.btn_mode_sweep.isChecked()

        if is_sweep:
            self.graph_x_data = []
            self.graph_pri_y = []
            self.graph_sec_y = []
            self.graph_display.clear_plots()

        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

        settings = {
            'run_mode': 'SWEEP' if is_sweep else 'SINGLE',
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

        is_sweep = self.ctrl_panel.btn_mode_sweep.isChecked()
        if is_sweep:
            self.graph_x_data.append(data.get('freq', 0))
        else:
            self.graph_x_data.append(len(self.graph_x_data) + 1)
            
        self.graph_pri_y.append(data.get('primary', 0.0))
        self.graph_sec_y.append(data.get('secondary', 0.0))
        self.graph_display.update_plots(self.graph_x_data, self.graph_pri_y, self.graph_sec_y)

    def handle_worker_error(self, error_msg):
        QMessageBox.critical(self, "Hardware Error", error_msg)

    def handle_progress_update(self, percent):
        if self.ctrl_panel.btn_mode_sweep.isChecked():
            self.ctrl_panel.btn_start.setText(f"⏳ SWEEPING... {percent}%")

    def handle_worker_finished(self):
        self.set_ui_locked(False) 
        self.worker = None

    def clear_graph_data(self):
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []
        self.graph_display.clear_plots()
        self.update_session_lock()

    def update_session_lock(self):
        has_data = len(self.graph_x_data) > 0
        is_sweep = self.ctrl_panel.btn_mode_sweep.isChecked()
        should_lock = has_data and not is_sweep
        
        self.input_panel.combo_prop_group.setEnabled(not should_lock)
        self.input_panel.combo_scpi_mode.setEnabled(not should_lock)
        self.ctrl_panel.btn_mode_single.setEnabled(not should_lock)
        self.ctrl_panel.btn_mode_sweep.setEnabled(not should_lock)
        
        self.adv_panel.chk_dev_enable.setEnabled(not should_lock)
        dev_enabled = self.adv_panel.chk_dev_enable.isChecked() and not should_lock
        self.adv_panel.widget_dev_inner.setEnabled(dev_enabled)
        
        if not should_lock:
            self.input_panel.input_start_freq.setEnabled(is_sweep)
            self.input_panel.input_stop_freq.setEnabled(is_sweep)
            self.input_panel.input_points.setEnabled(is_sweep)
            self.input_panel.radio_log.setEnabled(is_sweep)
            self.input_panel.radio_lin.setEnabled(is_sweep)
        else:
            self.input_panel.radio_log.setEnabled(False)
            self.input_panel.radio_lin.setEnabled(False)
            self.input_panel.input_start_freq.setEnabled(False)
            self.input_panel.input_stop_freq.setEnabled(False)
            self.input_panel.input_points.setEnabled(False)

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
        
        # หากมีการเปลี่ยนโหมด แล้วพบว่ามีข้อมูลเก่าค้างอยู่บนกราฟ
        if len(self.graph_x_data) > 0:
            reply = QMessageBox.question(
                self, 
                'ยืนยันการเปลี่ยนโหมด', 
                "การเปลี่ยนโหมดการวัดจะล้างข้อมูลที่ยังไม่ได้บันทึกทิ้ง\nคุณต้องการดำเนินการต่อและล้างกราฟใช่หรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.clear_graph_data()
            else:
                # ⚠️ คืนสถานะปุ่มกลับไปเหมือนเดิม โดยบล็อก Signal ไว้เพื่อป้องกันโปรแกรมค้าง (Infinite Loop)
                self.ctrl_panel.btn_mode_sweep.blockSignals(True)
                self.ctrl_panel.btn_mode_single.blockSignals(True)
                
                self.ctrl_panel.btn_mode_sweep.setChecked(not is_sweep)
                self.ctrl_panel.btn_mode_single.setChecked(is_sweep)
                
                self.ctrl_panel.btn_mode_sweep.blockSignals(False)
                self.ctrl_panel.btn_mode_single.blockSignals(False)
                return # หยุดการทำงานทันที ไม่ไปเปิด/ปิดช่องกรอกความถี่ด้านล่างต่อ

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