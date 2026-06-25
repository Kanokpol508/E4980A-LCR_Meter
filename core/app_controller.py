# ตัวกลางรับ Event จาก GUI ไปสั่ง Hardware และส่งผลกลับมา GUI

from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, QObject

from core.measurement_thread import MeasurementWorker
from core.correction_thread import CorrectionWorker
from hardware.lcr_meter import E4980A

class AppController(QObject):
    def __init__(self, view):
        super().__init__()
        self.view = view

        # ตัวแปรสถานะ
        self.is_dc_error = False
        self.is_dev_error = False
        self.is_visa_error = True
        
        self.worker = None
        self.corr_worker = None
        self.verify_worker = None
        self.progress_dialog = None
        self.current_corr_type = None

        # ตัวแปรสำหรับเก็บข้อมูลวาดกราฟ (อาจถูกดัดแปลงโดย Deviation)
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []
        
        # ตัวแปรสำหรับเก็บ "ค่าดิบ (Raw Data)" เพื่อนำไปคำนวณสถิติ Type A 
        self.graph_raw_pri_y = []
        self.graph_raw_sec_y = []

        self.meas_options = {
            "Capacitance (ความจุไฟฟ้า)": [
                ("Cp-D", "CPD"), ("Cp-Q", "CPQ"), ("Cp-G", "CPG"), ("Cp-Rp", "CPRP"),
                ("Cs-D", "CSD"), ("Cs-Q", "CSQ"), ("Cs-Rs", "CSRS")
            ],
            "Inductance (ความเหนี่ยวนำ)": [
                ("Lp-D", "LPD"), ("Lp-Q", "LPQ"), ("Lp-G", "LPG"), ("Lp-Rp", "LPRP"),
                ("Ls-D", "LSD"), ("Ls-Q", "LSQ"), ("Ls-Rs", "LSRS")
            ],
            "Impedance (อิมพีแดนซ์)": [("R-X", "RX"), ("Z-θd", "ZTD"), ("Z-θr", "ZTR")],
            "Admittance (แอดมิตแทนซ์)": [("G-B", "GB"), ("Y-θd", "YTD"), ("Y-θr", "YTR")]
        }

        # รันตอนเปิดโปรแกรม
        self._connect_signals()
        self.view.input_panel.combo_prop_group.addItems(self.meas_options.keys())
        self.update_scpi_modes()
        self.scan_visa_ports()
        
        self.update_hardware_limits() 
        self.update_calculated_points()

        # ตั้งค่า UI เริ่มต้น
        self.view.adv_panel.widget_dc_inner.setEnabled(False)
        self.view.adv_panel.widget_dev_inner.setEnabled(False)

    def _connect_signals(self):
        v = self.view
        v.input_panel.combo_prop_group.currentIndexChanged.connect(self.update_scpi_modes)
        v.conn_panel.btn_refresh.clicked.connect(self.scan_visa_ports)
        v.conn_panel.combo_visa.currentTextChanged.connect(self.validate_visa)

        v.adv_panel.chk_dc_enable.stateChanged.connect(self.toggle_dc_bias)
        v.adv_panel.combo_dc_level.currentIndexChanged.connect(self.validate_dc_bias)

        v.adv_panel.chk_dev_enable.stateChanged.connect(self.toggle_deviation)
        v.adv_panel.input_dev_pri.textChanged.connect(self.validate_deviation)

        v.adv_panel.btn_open_corr.clicked.connect(lambda: self.start_correction("OPEN"))
        v.adv_panel.btn_short_corr.clicked.connect(lambda: self.start_correction("SHORT"))

        v.ctrl_panel.btn_verify.clicked.connect(self.handle_verify_apply)
        v.lcd_display.btn_clear.clicked.connect(self.handle_clear_graph)

        v.ctrl_panel.btn_mode_single.toggled.connect(self.toggle_run_mode)
        v.ctrl_panel.btn_start.clicked.connect(self.start_measurement)
        v.ctrl_panel.btn_stop.clicked.connect(self.stop_measurement)
        
        v.input_panel.input_start_freq.valueChanged.connect(self.update_calculated_points)
        v.input_panel.input_stop_freq.valueChanged.connect(self.update_calculated_points)
        v.input_panel.input_step_freq.valueChanged.connect(self.update_calculated_points)

    # ========================================================
    # Logic Methods 
    # ========================================================
    def update_calculated_points(self):
        v = self.view
        start = v.input_panel.input_start_freq.value()
        stop = v.input_panel.input_stop_freq.value()
        step = v.input_panel.input_step_freq.value()

        if step <= 0 or stop <= start:
            v.input_panel.lbl_calculated_points.setText("จำนวนจุดที่ได้: -")
            return

        n_points = int((stop - start) / step) + 1
        n_points = max(2, min(201, n_points)) 
        v.input_panel.lbl_calculated_points.setText(f"จำนวนจุดที่ได้: {n_points} จุด")

    def update_hardware_limits(self):
        v = self.view
        v.input_panel.input_volt.setMaximum(2.0)
        v.input_panel.input_volt.setToolTip("เครื่องรุ่นมาตรฐาน (ไม่มี Option 001) จ่ายสัญญาณทดสอบได้สูงสุด 2.0 Vrms")

    def scan_visa_ports(self):
        self.view.conn_panel.combo_visa.clear()
        resources = E4980A.scan_ports()
        if resources:
            self.view.conn_panel.combo_visa.addItems(resources)
        else:
            self.view.conn_panel.combo_visa.addItem("No Device Found")
        self.validate_visa()

    def set_ui_locked(self, locked: bool):
        v = self.view
        v.left_content.setEnabled(not locked)
        v.ctrl_panel.btn_mode_single.setEnabled(not locked)
        v.ctrl_panel.btn_mode_sweep.setEnabled(not locked)
        
        v.lcd_display.btn_clear.setEnabled(not locked) 
        v.ctrl_panel.btn_stop.setEnabled(locked)
        
        if locked:
            v.ctrl_panel.btn_start.setEnabled(False)
            v.ctrl_panel.btn_start.setText("⏳ RUNNING...")
        else:
            v.ctrl_panel.btn_start.setText("START")
            v.ctrl_panel.btn_stop.setText("STOP")
            self.update_start_button_state()
            self.update_session_lock()

    def handle_verify_apply(self):
        v = self.view
        visa_address = v.conn_panel.combo_visa.currentText()
        if not visa_address or visa_address == "No Device Found":
            QMessageBox.warning(v, "ตรวจสอบล้มเหลว", "กรุณาเชื่อมต่อเครื่อง LCR Meter ก่อนทำการตรวจสอบการตั้งค่า")
            return

        settings = {
            'visa_resource': visa_address,
            'freq': v.input_panel.input_freq.value(),
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentData(),
            'dc_bias_enabled': v.adv_panel.chk_dc_enable.isChecked(),
            'dc_is_voltage': True, 
            'dc_bias_level': v.adv_panel.combo_dc_level.currentData(),
        }

        self.set_ui_locked(True)
        self.progress_dialog = QProgressDialog(
            "กำลังส่งค่าและตรวจสอบความถูกต้องจากเครื่อง LCR Meter...\n(Verify & Apply)", 
            "กำลังประมวลผล...", 0, 0, v
        )
        self.progress_dialog.setWindowTitle("System Verification")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None) 
        self.progress_dialog.show()

        from core.verify_thread import VerifyWorker
        self.verify_worker = VerifyWorker(visa_address, settings)
        self.verify_worker.finished_signal.connect(self.handle_verify_finished)
        self.verify_worker.start()

    def handle_verify_finished(self, success: bool, results: list, error_msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.set_ui_locked(False)
        self.verify_worker = None

        from gui.dialogs.verify_dialog import VerifyDialog
        dialog = VerifyDialog(results, error_msg, self.view)
        dialog.exec()

    def start_correction(self, corr_type: str):
        v = self.view
        visa_address = v.conn_panel.combo_visa.currentText()
        if not visa_address or visa_address == "No Device Found":
            QMessageBox.warning(v, "เชื่อมต่อล้มเหลว", "กรุณาเชื่อมต่อเครื่อง LCR Meter ก่อนทำการชดเชยค่า")
            return

        msg = ("กรุณาแยกสายวัดออกจากกัน (ปลดชิ้นงานออก)" if corr_type == "OPEN" 
               else "กรุณานำสายวัดมาแตะช็อตกัน (ใช้แผ่น Shorting Plate)")
        
        reply = QMessageBox.question(
            v, f"เตรียมความพร้อม {corr_type} Correction", 
            f"{msg}\n\nคุณพร้อมที่จะเริ่มทำการชดเชยค่าหรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.set_ui_locked(True)
        v.ctrl_panel.btn_stop.setEnabled(False) 
        self.current_corr_type = corr_type

        self.progress_dialog = QProgressDialog(
            f"เครื่องกำลังทำงาน {corr_type} Correction...\n(อาจใช้เวลา 15 - 60 วินาที กรุณาห้ามถอดสาย)", 
            "กำลังประมวลผล...", 0, 0, v
        )
        self.progress_dialog.setWindowTitle(f"{corr_type} Correction")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setCancelButton(None) 
        self.progress_dialog.show()

        self.corr_worker = CorrectionWorker(visa_address, corr_type)
        self.corr_worker.finished_signal.connect(self.handle_correction_finished)
        self.corr_worker.start()

    def handle_correction_finished(self, success: bool, msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.set_ui_locked(False) 
        self.corr_worker = None

        if success:
            QMessageBox.information(self.view, "Correction สำเร็จ", f"✅ {msg}")
            green_style = "background-color: #10b981; color: white; border: none;"
            if self.current_corr_type == "OPEN":
                self.view.adv_panel.btn_open_corr.setStyleSheet(green_style)
                self.view.adv_panel.btn_open_corr.setText("OPEN Correction (OK)")
            elif self.current_corr_type == "SHORT":
                self.view.adv_panel.btn_short_corr.setStyleSheet(green_style)
                self.view.adv_panel.btn_short_corr.setText("SHORT Correction (OK)")
        else:
            QMessageBox.critical(self.view, "Correction ล้มเหลว", f"❌ {msg}")
            
        self.current_corr_type = None

    def handle_clear_graph(self):
        reply = QMessageBox.question(
            self.view, 'ยืนยันการล้างข้อมูล', "คุณต้องการล้างข้อมูลและรีเซ็ตกราฟใช่หรือไม่?\n(ข้อมูลที่ยังไม่ถูกบันทึกจะหายไป)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.clear_graph_data()

    def setup_graph_labels(self):
        v = self.view
        scpi_mode = v.input_panel.combo_scpi_mode.currentData()
        pri_label = "Primary"
        sec_label = "Secondary"
        
        if scpi_mode.startswith("CP"): pri_label = "Capacitance, Cp (F)"
        elif scpi_mode.startswith("CS"): pri_label = "Capacitance, Cs (F)"
        elif scpi_mode.startswith("LP"): pri_label = "Inductance, Lp (H)"
        elif scpi_mode.startswith("LS"): pri_label = "Inductance, Ls (H)"
        elif scpi_mode == "RX": pri_label = "Resistance, R (Ω)"
        elif scpi_mode.startswith("Z"): pri_label = "Impedance, Z (Ω)"
        elif scpi_mode.startswith("Y") or scpi_mode == "GB": pri_label = "Admittance (S)"
        
        if scpi_mode.endswith("D"): sec_label = "Dissipation Factor, D"
        elif scpi_mode.endswith("Q"): sec_label = "Quality Factor, Q"
        elif scpi_mode.endswith("RS") or scpi_mode.endswith("RP") or scpi_mode == "RX": sec_label = "Resistance (Ω)"
        elif "T" in scpi_mode: sec_label = "Phase Angle, θ (°)"
        
        if v.adv_panel.chk_dev_enable.isChecked():
            dev_type = v.adv_panel.combo_dev_type.currentText()
            if "PCT" in dev_type or "เปอร์เซ็นต์" in dev_type:
                pri_label = f"Δ {pri_label.split(',')[0]} (%)"
                sec_label = f"Δ {sec_label.split(',')[0]} (%)"
            else:
                pri_label = f"Δ {pri_label}"
                sec_label = f"Δ {sec_label}"

        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()
        x_label = "Frequency (Hz)" if is_sweep else "Measurement Count (Points)"
        
        v.graph_display.set_axis_labels(x_label=x_label, pri_y_label=pri_label, sec_y_label=sec_label, is_single_mode=not is_sweep)

    def start_measurement(self):
        v = self.view
        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()

        if is_sweep:
            self.graph_x_data = []
            self.graph_pri_y = []
            self.graph_sec_y = []
            
            # เคลียร์ค่าดิบด้วยเมื่อกด Sweep เริ่มใหม่
            self.graph_raw_pri_y = []
            self.graph_raw_sec_y = []
            
            v.graph_display.clear_plots()

        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

        settings = {
            'run_mode': 'SWEEP' if is_sweep else 'SINGLE',
            'visa_resource': v.conn_panel.combo_visa.currentText(),
            'freq': v.input_panel.input_freq.value(),
            'start_freq': v.input_panel.input_start_freq.value(),
            'stop_freq': v.input_panel.input_stop_freq.value(),
            'step_freq': v.input_panel.input_step_freq.value(), 
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentData(),
            'dc_bias_enabled': v.adv_panel.chk_dc_enable.isChecked(),
            'dc_is_voltage': True, 
            'dc_bias_level': v.adv_panel.combo_dc_level.currentData(),
        }
        
        self.worker = MeasurementWorker(settings)
        self.worker.data_ready.connect(self.handle_data_ready)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.progress_updated.connect(self.handle_progress_update)
        self.worker.finished.connect(self.handle_worker_finished)
        
        self.set_ui_locked(True)
        v.lcd_display.lbl_pri_val.setText("Measuring...")
        v.lcd_display.lbl_sec_val.setText("Measuring...")
        self.worker.start()

    def stop_measurement(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop() 
            self.view.ctrl_panel.btn_stop.setText("STOPPING...")
            self.view.ctrl_panel.btn_stop.setEnabled(False) 

    # ========================================================
    # การคำนวณและแสดงผลข้อมูล (Data Handling & Math)
    # ========================================================
    def handle_data_ready(self, data):
        v = self.view
        
        # 1. ค่าดิบจากฮาร์ดแวร์ (เพียวๆ)
        raw_pri = data.get('primary', 0.0)
        raw_sec = data.get('secondary', 0.0)
        
        # เก็บค่าดิบลง Array ไว้คำนวณ Type A Uncertainty ทันที
        self.graph_raw_pri_y.append(raw_pri)
        self.graph_raw_sec_y.append(raw_sec)
        
        # 2. ค่าที่จะนำไปแสดงบนกราฟและจอ LCD (อาจถูกปรับด้วย Deviation)
        disp_pri = raw_pri
        disp_sec = raw_sec
        
        if v.adv_panel.chk_dev_enable.isChecked():
            try:
                pri_ref = float(v.adv_panel.input_dev_pri.text().strip())
                sec_text = v.adv_panel.input_dev_sec.text().strip()
                has_sec_ref = bool(sec_text)
                sec_ref = float(sec_text) if has_sec_ref else 0.0
                
                dev_type = v.adv_panel.combo_dev_type.currentText()
                is_pct = "PCT" in dev_type or "เปอร์เซ็นต์" in dev_type
                
                if is_pct:
                    disp_pri = ((raw_pri - pri_ref) / abs(pri_ref)) * 100 if pri_ref != 0 else 0.0
                else:
                    disp_pri = raw_pri - pri_ref
                    
                if has_sec_ref:
                    if is_pct:
                        disp_sec = ((raw_sec - sec_ref) / abs(sec_ref)) * 100 if sec_ref != 0 else 0.0
                    else:
                        disp_sec = raw_sec - sec_ref
            except ValueError:
                pass
                
        v.lcd_display.lbl_pri_val.setText(f"{disp_pri:.5e}")
        v.lcd_display.lbl_sec_val.setText(f"{disp_sec:.5e}")

        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()
        if is_sweep:
            self.graph_x_data.append(data.get('freq', 0))
        else:
            self.graph_x_data.append(len(self.graph_x_data) + 1)
            
        self.graph_pri_y.append(disp_pri)
        self.graph_sec_y.append(disp_sec)
        
        # ทั้งกราฟ และ Panel สถิติ (โยน raw เข้าไปคำนวณ)
        v.graph_display.update_plots(self.graph_x_data, self.graph_pri_y, self.graph_sec_y)
        v.graph_display.update_statistics(self.graph_raw_pri_y, self.graph_raw_sec_y, not is_sweep)

    def handle_worker_error(self, error_msg):
        QMessageBox.critical(self.view, "Hardware Error", error_msg)

    def handle_progress_update(self, percent):
        if self.view.ctrl_panel.btn_mode_sweep.isChecked():
            self.view.ctrl_panel.btn_start.setText(f"⏳ SWEEPING... {percent}%")

    def handle_worker_finished(self):
        self.set_ui_locked(False) 
        self.worker = None

    def clear_graph_data(self):
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []
        
        # ล้างข้อมูลดิบด้วยเมื่อกด Sweep เริ่มใหม่
        self.graph_raw_pri_y = []
        self.graph_raw_sec_y = []
        
        self.view.graph_display.clear_plots()
        self.update_session_lock()

    def update_session_lock(self):
        v = self.view
        has_data = len(self.graph_x_data) > 0
        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()
        should_lock = has_data and not is_sweep
        
        v.input_panel.combo_prop_group.setEnabled(not should_lock)
        v.input_panel.combo_scpi_mode.setEnabled(not should_lock)
        v.ctrl_panel.btn_mode_single.setEnabled(not should_lock)
        v.ctrl_panel.btn_mode_sweep.setEnabled(not should_lock)
        
        v.adv_panel.chk_dev_enable.setEnabled(not should_lock)
        dev_enabled = v.adv_panel.chk_dev_enable.isChecked() and not should_lock
        v.adv_panel.widget_dev_inner.setEnabled(dev_enabled)
        
        if not should_lock:
            v.input_panel.input_start_freq.setEnabled(is_sweep)
            v.input_panel.input_stop_freq.setEnabled(is_sweep)
            v.input_panel.input_step_freq.setEnabled(is_sweep)
        else:
            v.input_panel.input_start_freq.setEnabled(False)
            v.input_panel.input_stop_freq.setEnabled(False)
            v.input_panel.input_step_freq.setEnabled(False)

    def validate_visa(self):
        text = self.view.conn_panel.combo_visa.currentText()
        self.is_visa_error = (text == "No Device Found" or text.strip() == "")
        self.update_start_button_state()

    def update_scpi_modes(self):
        self.view.input_panel.combo_scpi_mode.clear()
        selected_group = self.view.input_panel.combo_prop_group.currentText()
        modes = self.meas_options.get(selected_group, [])
        for display_text, scpi_code in modes:
            self.view.input_panel.combo_scpi_mode.addItem(f"{scpi_code} ({display_text})", userData=scpi_code)

    def update_start_button_state(self):
        v = self.view
        is_blocked = self.is_dc_error or self.is_dev_error or self.is_visa_error
        v.ctrl_panel.lbl_warn_visa.setVisible(self.is_visa_error)
        v.ctrl_panel.lbl_warn_dc_start.setVisible(self.is_dc_error)
        v.ctrl_panel.lbl_warn_dev_start.setVisible(self.is_dev_error)

        if is_blocked:
            v.ctrl_panel.btn_start.setText("🔒 START")
            v.ctrl_panel.btn_start.setEnabled(False)
        else:
            v.ctrl_panel.btn_start.setText("START")
            v.ctrl_panel.btn_start.setEnabled(True)

    def toggle_run_mode(self):
        v = self.view
        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()
        
        if len(self.graph_x_data) > 0:
            reply = QMessageBox.question(
                v, 
                'ยืนยันการเปลี่ยนโหมด', 
                "การเปลี่ยนโหมดการวัดจะล้างข้อมูลที่ยังไม่ได้บันทึกทิ้ง\nคุณต้องการดำเนินการต่อและล้างกราฟใช่หรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.clear_graph_data()
            else:
                v.ctrl_panel.btn_mode_sweep.blockSignals(True)
                v.ctrl_panel.btn_mode_single.blockSignals(True)
                
                v.ctrl_panel.btn_mode_sweep.setChecked(not is_sweep)
                v.ctrl_panel.btn_mode_single.setChecked(is_sweep)
                
                v.ctrl_panel.btn_mode_sweep.blockSignals(False)
                v.ctrl_panel.btn_mode_single.blockSignals(False)
                return 

        v.input_panel.input_start_freq.setEnabled(is_sweep)
        v.input_panel.input_stop_freq.setEnabled(is_sweep)
        v.input_panel.input_step_freq.setEnabled(is_sweep)
        
        self.update_hardware_limits() 
        self.update_start_button_state()

    def toggle_dc_bias(self):
        is_enabled = self.view.adv_panel.chk_dc_enable.isChecked()
        self.view.adv_panel.widget_dc_inner.setEnabled(is_enabled)
        if is_enabled:
            self.validate_dc_bias()
        else:
            self.view.adv_panel.lbl_dc_warning.setText("")
            self.is_dc_error = False
            self.update_start_button_state()

    def validate_dc_bias(self):
        v = self.view
        if not v.adv_panel.chk_dc_enable.isChecked():
            self.is_dc_error = False
            self.update_start_button_state()
            return
            
        warning_msg = "⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!"
        self.is_dc_error = False
            
        v.adv_panel.lbl_dc_warning.setText(warning_msg)
        self.update_start_button_state()

    def toggle_deviation(self):
        is_enabled = self.view.adv_panel.chk_dev_enable.isChecked()
        self.view.adv_panel.widget_dev_inner.setEnabled(is_enabled)
        if is_enabled:
            self.validate_deviation()
        else:
            self.view.adv_panel.lbl_dev_warning.setText("")
            self.is_dev_error = False
            self.update_start_button_state()

    def validate_deviation(self):
        v = self.view
        if not v.adv_panel.chk_dev_enable.isChecked():
            self.is_dev_error = False
            self.update_start_button_state()
            return
            
        pri_text = v.adv_panel.input_dev_pri.text().strip()
        if not pri_text:
            v.adv_panel.lbl_dev_warning.setText("⚠️ ต้องระบุ Primary Reference (หลัก) ก่อนเริ่มวัด")
            self.is_dev_error = True
        else:
            try:
                float(pri_text)
                v.adv_panel.lbl_dev_warning.setText("")
                self.is_dev_error = False
            except ValueError:
                v.adv_panel.lbl_dev_warning.setText("⚠️ กรุณาป้อนตัวเลขให้ถูกต้อง เช่น 100E-9")
                self.is_dev_error = True
        self.update_start_button_state()