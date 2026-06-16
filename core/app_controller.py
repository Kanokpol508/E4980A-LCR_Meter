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

        # รันตอนเปิดโปรแกรม
        self._connect_signals()
        self.view.input_panel.combo_prop_group.addItems(self.meas_options.keys())
        self.update_scpi_modes()
        self.scan_visa_ports()

        # ตั้งค่า UI เริ่มต้น
        self.view.adv_panel.widget_dc_inner.setEnabled(False)
        self.view.adv_panel.widget_dev_inner.setEnabled(False)

    def _connect_signals(self):
        """ผูก Event/Signals ทั้งหมดของ UI เข้ากับฟังก์ชันใน Controller"""
        v = self.view
        v.input_panel.combo_prop_group.currentIndexChanged.connect(self.update_scpi_modes)
        v.conn_panel.btn_refresh.clicked.connect(self.scan_visa_ports)
        v.conn_panel.combo_visa.currentTextChanged.connect(self.validate_visa)

        v.adv_panel.chk_dc_enable.stateChanged.connect(self.toggle_dc_bias)
        v.adv_panel.chk_opt001.stateChanged.connect(self.validate_dc_bias)
        v.adv_panel.btn_dc_v.toggled.connect(self.validate_dc_bias)
        v.adv_panel.input_dc_level.valueChanged.connect(self.validate_dc_bias)

        v.adv_panel.chk_dev_enable.stateChanged.connect(self.toggle_deviation)
        v.adv_panel.input_dev_pri.textChanged.connect(self.validate_deviation)

        v.adv_panel.btn_open_corr.clicked.connect(lambda: self.start_correction("OPEN"))
        v.adv_panel.btn_short_corr.clicked.connect(lambda: self.start_correction("SHORT"))


        v.lcd_display.btn_verify.clicked.connect(self.handle_verify_apply)

        v.ctrl_panel.btn_mode_single.toggled.connect(self.toggle_run_mode)
        v.ctrl_panel.btn_start.clicked.connect(self.start_measurement)
        v.ctrl_panel.btn_stop.clicked.connect(self.stop_measurement)
        v.ctrl_panel.btn_clear_graph.clicked.connect(self.handle_clear_graph)

    # ========================================================
    # Logic Methods 
    # ========================================================
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
        v.ctrl_panel.btn_clear_graph.setEnabled(not locked) 
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
        """จัดการลอจิกเมื่อผู้ใช้กดปุ่ม Verify & Apply"""
        v = self.view
        visa_address = v.conn_panel.combo_visa.currentText()
        if not visa_address or visa_address == "No Device Found":
            QMessageBox.warning(v, "ตรวจสอบล้มเหลว", "กรุณาเชื่อมต่อเครื่อง LCR Meter ก่อนทำการตรวจสอบการตั้งค่า")
            return

        # รวบรวมข้อมูล Settings ทั้งหมด รวมถึง DC Bias
        settings = {
            'visa_resource': visa_address,
            'freq': v.input_panel.input_freq.value(),
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentText(),
            'dc_bias_enabled': v.adv_panel.chk_dc_enable.isChecked(),
            'dc_is_voltage': v.adv_panel.btn_dc_v.isChecked(),
            'dc_bias_level': v.adv_panel.input_dc_level.value(),
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

        # นำเข้าและสั่งรัน VerifyWorker เบื้องหลัง
        from core.verify_thread import VerifyWorker
        self.verify_worker = VerifyWorker(visa_address, settings)
        self.verify_worker.finished_signal.connect(self.handle_verify_finished)
        self.verify_worker.start()


    def handle_verify_finished(self, success: bool, results: list, error_msg: str):
        """รับผลลัพธ์จาก VerifyWorker และเปิดหน้าต่างตาราง"""
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None
            
        self.set_ui_locked(False)
        self.verify_worker = None

        # นำเข้าและเปิดหน้าต่าง Dialog แสดงตารางผลลัพธ์
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
        else:
            QMessageBox.critical(self.view, "Correction ล้มเหลว", f"❌ {msg}")

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
        elif scpi_mode == "VDID": pri_label = "DC Voltage (V)"
        
        if scpi_mode.endswith("D"): sec_label = "Dissipation Factor, D"
        elif scpi_mode.endswith("Q"): sec_label = "Quality Factor, Q"
        elif scpi_mode.endswith("RS") or scpi_mode.endswith("RP") or scpi_mode.endswith("RD") or scpi_mode == "RX": sec_label = "Resistance (Ω)"
        elif "T" in scpi_mode: sec_label = "Phase Angle, θ (°)"
        elif scpi_mode == "VDID": sec_label = "DC Current (A)"
        
        if v.adv_panel.chk_dev_enable.isChecked():
            dev_type = v.adv_panel.combo_dev_type.currentText()
            if "PCT" in dev_type or "เปอร์เซ็นต์" in dev_type:
                pri_label = f"Δ {pri_label.split(',')[0]} (%)"
                sec_label = f"Δ {sec_label.split(',')[0]} (%)"
            else:
                pri_label = f"Δ {pri_label}"
                sec_label = f"Δ {sec_label}"

        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()
        is_log = v.input_panel.radio_log.isChecked() if is_sweep else False
        x_label = "Frequency (Hz)" if is_sweep else "Measurement Count (Points)"
        
        v.graph_display.set_axis_labels(x_label=x_label, pri_y_label=pri_label, sec_y_label=sec_label, is_log_x=is_log, is_single_mode=not is_sweep)

    def start_measurement(self):
        v = self.view
        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()

        if is_sweep:
            self.graph_x_data = []
            self.graph_pri_y = []
            self.graph_sec_y = []
            v.graph_display.clear_plots()

        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

        settings = {
            'run_mode': 'SWEEP' if is_sweep else 'SINGLE',
            'visa_resource': v.conn_panel.combo_visa.currentText(),
            'freq': v.input_panel.input_freq.value(),
            'start_freq': v.input_panel.input_start_freq.value(),
            'stop_freq': v.input_panel.input_stop_freq.value(),
            'sweep_points': v.input_panel.input_points.value(),
            'sweep_scale': 'LOG' if v.input_panel.radio_log.isChecked() else 'LIN',
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentText(),
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

    def handle_data_ready(self, data):
        v = self.view
        v.lcd_display.lbl_pri_val.setText(f"{data.get('primary', 0.0):.5e}")
        v.lcd_display.lbl_sec_val.setText(f"{data.get('secondary', 0.0):.5e}")

        is_sweep = v.ctrl_panel.btn_mode_sweep.isChecked()
        if is_sweep:
            self.graph_x_data.append(data.get('freq', 0))
        else:
            self.graph_x_data.append(len(self.graph_x_data) + 1)
            
        self.graph_pri_y.append(data.get('primary', 0.0))
        self.graph_sec_y.append(data.get('secondary', 0.0))
        v.graph_display.update_plots(self.graph_x_data, self.graph_pri_y, self.graph_sec_y)

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
            v.input_panel.input_points.setEnabled(is_sweep)
            v.input_panel.radio_log.setEnabled(is_sweep)
            v.input_panel.radio_lin.setEnabled(is_sweep)
        else:
            v.input_panel.radio_log.setEnabled(False)
            v.input_panel.radio_lin.setEnabled(False)
            v.input_panel.input_start_freq.setEnabled(False)
            v.input_panel.input_stop_freq.setEnabled(False)
            v.input_panel.input_points.setEnabled(False)

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
            v.ctrl_panel.btn_start.setText("🔒 BLOCKED")
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
        v.input_panel.input_points.setEnabled(is_sweep)
        v.input_panel.radio_log.setEnabled(is_sweep)
        v.input_panel.radio_lin.setEnabled(is_sweep)
        self.update_start_button_state()

    def toggle_dc_bias(self):
        is_enabled = self.view.adv_panel.chk_dc_enable.isChecked()
        self.view.adv_panel.widget_dc_inner.setEnabled(is_enabled)
        if is_enabled:
            self.validate_dc_bias()
        else:
            self.view.adv_panel.lbl_dc_warning.setText("⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!")
            self.is_dc_error = False
            self.update_start_button_state()

    def validate_dc_bias(self):
        v = self.view
        if not v.adv_panel.chk_dc_enable.isChecked():
            self.is_dc_error = False
            self.update_start_button_state()
            return
            
        is_voltage = v.adv_panel.btn_dc_v.isChecked()
        v.adv_panel.lbl_dc_unit.setText("V" if is_voltage else "A")
        warning_msg = "⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัดก่อนเปิดสวิตช์เสมอ!"
        self.is_dc_error = False
        val = v.adv_panel.input_dc_level.value()
        has_opt = v.adv_panel.chk_opt001.isChecked()
        
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
                if not any(abs(val - v_test) < TOLERANCE for v_test in DISCRETE):
                    warning_msg = "⚠️ เครื่องรุ่นปกติปรับแรงดันได้แค่ 0, 1.5 หรือ 2.0 V เท่านั้น"
                    self.is_dc_error = True
            else:
                if val < -40.0 or val > 40.0:
                    warning_msg = "⚠️ แรงดันเกินขีดจำกัด! Option 001 รองรับ -40.0 V ถึง +40.0 V"
                    self.is_dc_error = True
            
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