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
        self.is_freqlist_error = False          # ป้องกัน AttributeError

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

        # ดึง Logger จาก LogDisplay ก่อนเรียก method อื่นๆ ที่ใช้ self.log
        self.log = self.view.log_display.get_logger()
        self.log.info("โปรแกรมเริ่มต้นเรียบร้อย | E4980A LCR Meter Controller พร้อมใช้งาน")

        # รันตอนเปิดโปรแกรม
        self._connect_signals()
        self.view.input_panel.combo_prop_group.addItems(self.meas_options.keys())
        self.update_scpi_modes()
        self.scan_visa_ports()

        self.update_hardware_limits()
        self.update_calculated_points()

        # ตั้งค่า UI เริ่มต้น
        self.view.input_panel.widget_dc_inner.setEnabled(False)
        self.view.adv_panel.widget_dev_inner.setEnabled(False)
        self.view.adv_panel.combo_dev_type.setEnabled(False)

        # ตั้งค่า visibility ของเนื้อหาย่อยใน group_mode ตามโหมดเริ่มต้น (Sweep)
        self.toggle_run_mode()

    def _connect_signals(self):
        v = self.view
        v.input_panel.combo_prop_group.currentIndexChanged.connect(self.update_scpi_modes)
        v.input_panel.combo_scpi_mode.currentIndexChanged.connect(self._refresh_deviation_preview)
        v.conn_panel.btn_refresh.clicked.connect(self.scan_visa_ports)
        v.conn_panel.combo_visa.currentTextChanged.connect(self.validate_visa)

        v.input_panel.chk_dc_enable.stateChanged.connect(self.toggle_dc_bias)
        v.input_panel.combo_dc_level.valueChanged.connect(self.validate_dc_bias)

        v.adv_panel.chk_dev_graph_enable.stateChanged.connect(self.toggle_deviation)
        v.adv_panel.chk_dev_ppm_enable.stateChanged.connect(self.toggle_deviation)
        v.adv_panel.input_dev_pri.textChanged.connect(self.validate_deviation)
        v.adv_panel.input_dev_pri.textChanged.connect(self._refresh_deviation_preview)
        v.adv_panel.input_dev_sec.textChanged.connect(self.validate_deviation)
        v.adv_panel.input_dev_sec.textChanged.connect(self._refresh_deviation_preview)
        v.adv_panel.combo_dev_type.currentIndexChanged.connect(self._refresh_deviation_preview)

        v.adv_panel.btn_open_corr.clicked.connect(lambda: self.start_correction("OPEN"))
        v.adv_panel.btn_short_corr.clicked.connect(lambda: self.start_correction("SHORT"))

        v.ctrl_panel.btn_verify.clicked.connect(self.handle_verify_apply)
        v.ctrl_panel.btn_clear.clicked.connect(self.handle_clear_graph)

        # Dropdown เลือกโหมดตอนนี้อยู่ใน input_panel (ย้ายมาจาก ctrl_panel)
        v.input_panel.combo_run_mode.currentIndexChanged.connect(self.toggle_run_mode)
        v.ctrl_panel.btn_start.clicked.connect(self.start_measurement)
        v.ctrl_panel.btn_stop.clicked.connect(self.stop_measurement)

        v.input_panel.input_start_freq.valueChanged.connect(self.update_calculated_points)
        v.input_panel.input_stop_freq.valueChanged.connect(self.update_calculated_points)
        v.input_panel.input_step_freq.valueChanged.connect(self.update_calculated_points)

        # ตรวจสอบ Frequency List ทุกครั้งที่มีการแก้ไข (เฉพาะมีผลตอนอยู่โหมด List)
        v.input_panel.input_freq_list.freq_changed.connect(self.validate_freq_list)

    # ========================================================
    # Logic Methods
    # ========================================================
    def get_current_run_mode(self) -> str:
        """คืนค่าโหมดปัจจุบันจาก Dropdown (อยู่ใน input_panel): 'SINGLE' / 'SWEEP' / 'LIST'"""
        return self.view.input_panel.combo_run_mode.currentData()

    def update_calculated_points(self):
        v = self.view
        start = v.input_panel.input_start_freq.value()
        stop = v.input_panel.input_stop_freq.value()
        step = v.input_panel.input_step_freq.value()

        if step <= 0 or stop <= start:
            v.input_panel.lbl_calculated_points.setText("-")
            return

        n_points = int((stop - start) / step) + 1
        n_points = max(2, min(201, n_points))
        v.input_panel.lbl_calculated_points.setText(f"{n_points} จุด")

    def update_hardware_limits(self):
        v = self.view
        v.input_panel.input_volt.setMaximum(2.0)
        v.input_panel.input_volt.setToolTip("เครื่องรุ่นมาตรฐาน (ไม่มี Option 001) จ่ายสัญญาณทดสอบได้สูงสุด 2.0 Vrms")

    def scan_visa_ports(self):
        self.view.conn_panel.combo_visa.clear()
        resources = E4980A.scan_ports()
        if resources:
            self.view.conn_panel.combo_visa.addItems(resources)
            self.log.info(f"สแกนพบอุปกรณ์ VISA {len(resources)} รายการ: {', '.join(resources)}")
        else:
            self.view.conn_panel.combo_visa.addItem("No Device Found")
            self.log.warning("ไม่พบอุปกรณ์ VISA — ตรวจสอบสาย USB/GPIB และ Driver")
        self.validate_visa()

    def set_ui_locked(self, locked: bool):
        v = self.view
        v.left_content.setEnabled(not locked)
        v.input_panel.combo_run_mode.setEnabled(not locked)

        v.ctrl_panel.btn_clear.setEnabled(not locked)
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
            'level_mode': v.input_panel.combo_level_mode.currentData(),
            'alc_enabled': v.input_panel.chk_alc.isChecked(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentData(),
            'dc_bias_enabled': v.input_panel.chk_dc_enable.isChecked(),
            'dc_is_voltage': True,
            'dc_bias_level': v.input_panel.combo_dc_level.value(),
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

        if success:
            self.log.info("Verify & Apply ✅ ผ่านทุกรายการ")
        else:
            fail_params = [r['param'] for r in results if "FAIL" in str(r.get('status', ''))]
            self.log.warning(f"Verify & Apply ❌ ไม่ผ่าน: {', '.join(fail_params) if fail_params else error_msg}")

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
        self.log.info(f"เริ่ม {corr_type} Correction...")

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
            self.log.info(f"{self.current_corr_type} Correction ✅ สำเร็จ")
            QMessageBox.information(self.view, "Correction สำเร็จ", f"✅ {msg}")
            green_style = "background-color: #10b981; color: white; border: none;"
            if self.current_corr_type == "OPEN":
                self.view.adv_panel.btn_open_corr.setStyleSheet(green_style)
                self.view.adv_panel.btn_open_corr.setText("OPEN Correction (OK)")
            elif self.current_corr_type == "SHORT":
                self.view.adv_panel.btn_short_corr.setStyleSheet(green_style)
                self.view.adv_panel.btn_short_corr.setText("SHORT Correction (OK)")
        else:
            self.log.error(f"{self.current_corr_type} Correction ❌ ล้มเหลว: {msg}")
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

        # ป้องกัน AttributeError ตอน combo_scpi_mode ถูก .clear() ชั่วขณะ
        # (เช่นระหว่าง update_scpi_modes() กำลังล้าง dropdown ก่อนเติมรายการใหม่)
        # ตอนนั้น currentData() จะคืนค่า None -> ยังไม่มีโหมดจริงให้ตั้งชื่อแกน จึงข้ามไปก่อน
        if scpi_mode is None:
            return

        pri_label = "Primary"
        sec_label = "Secondary"

        # --- Primary label ---
        if scpi_mode.startswith("CP"):
            pri_label = "Capacitance, Cp (F)"
        elif scpi_mode.startswith("CS"):
            pri_label = "Capacitance, Cs (F)"
        elif scpi_mode.startswith("LP"):
            pri_label = "Inductance, Lp (H)"
        elif scpi_mode.startswith("LS"):
            pri_label = "Inductance, Ls (H)"
        elif scpi_mode == "RX":
            pri_label = "Resistance, R (Ω)"
        elif scpi_mode.startswith("Z"):
            pri_label = "Impedance, Z (Ω)"
        elif scpi_mode.startswith("Y") or scpi_mode == "GB":
            pri_label = "Admittance, Y (S)"

        # --- Secondary label ---
        # ต้องเช็ค "TD"/"TR" ก่อน "D" เพราะ ZTD/YTD ลงท้ายด้วย D ด้วย
        if scpi_mode.endswith("TD"):
            sec_label = "Phase Angle, θd (°)"        # ZTD, YTD
        elif scpi_mode.endswith("TR"):
            sec_label = "Phase Angle, θr (rad)"      # ZTR, YTR
        elif scpi_mode.endswith("D"):
            sec_label = "Dissipation Factor, D"      # CPD, CSD, LPD, LSD
        elif scpi_mode.endswith("Q"):
            sec_label = "Quality Factor, Q"          # CPQ, CSQ, LPQ, LSQ
        elif scpi_mode.endswith("G"):
            sec_label = "Conductance, G (S)"         # CPG, LPG
        elif scpi_mode == "GB":
            sec_label = "Susceptance, B (S)"         # GB
        elif scpi_mode.endswith("RS") or scpi_mode.endswith("RP") or scpi_mode == "RX":
            sec_label = "Resistance (Ω)"             # CSRS, LSRS, CPRP, LPRP, RX

        # --- Deviation mode ปรับชื่อแกนตามประเภท deviation (ใช้ checkbox เฉพาะกราฟ) ---
        # Primary Ref และ Secondary Ref ไม่มีตัวไหนบังคับกรอกอีกต่อไป (สมมาตรกันทั้งคู่)
        # -> เช็คทีละตัวอิสระกัน ถ้าตัวไหนไม่มีค่า ให้คงชื่อแกนเดิมไว้ (ไม่ใส่ Δ)
        # เพราะข้อมูลจริงจะไม่ถูกแปลงเป็น Δ ด้วย (ดูตรรกะใน handle_data_ready)
        if v.adv_panel.chk_dev_graph_enable.isChecked():
            has_pri_ref = self._safe_float(v.adv_panel.input_dev_pri.text()) is not None
            has_sec_ref = self._safe_float(v.adv_panel.input_dev_sec.text()) is not None

            dev_type = v.adv_panel.combo_dev_type.currentText()
            is_pct = "PCT" in dev_type or "เปอร์เซ็นต์" in dev_type

            if is_pct:
                if has_pri_ref:
                    pri_label = f"Δ {pri_label.split(',')[0]} (%)"
                if has_sec_ref:
                    sec_label = f"Δ {sec_label.split(',')[0]} (%)"
            else:
                if has_pri_ref:
                    pri_label = f"Δ {pri_label}"
                if has_sec_ref:
                    sec_label = f"Δ {sec_label}"

        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        x_label = "Measurement Count (Points)" if is_single else "Frequency (Hz)"

        v.graph_display.set_axis_labels(
            x_label=x_label,
            pri_y_label=pri_label,
            sec_y_label=sec_label,
            is_single_mode=is_single
        )

    def start_measurement(self):
        v = self.view
        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")

        if not is_single:
            self.graph_x_data = []
            self.graph_pri_y = []
            self.graph_sec_y = []
            self.graph_raw_pri_y = []
            self.graph_raw_sec_y = []
            v.graph_display.clear_plots()

        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

        settings = {
            'run_mode': run_mode,  # 'SINGLE' / 'SWEEP' / 'LIST'
            'visa_resource': v.conn_panel.combo_visa.currentText(),
            'freq': v.input_panel.input_freq.value(),
            'start_freq': v.input_panel.input_start_freq.value(),
            'stop_freq': v.input_panel.input_stop_freq.value(),
            'step_freq': v.input_panel.input_step_freq.value(),
            'freq_list_raw': v.input_panel.input_freq_list.text(),
            'samples_per_freq': v.input_panel.input_samples.value(),
            'discard_first': v.input_panel.input_discard_first.value(),
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'level_mode': v.input_panel.combo_level_mode.currentData(),
            'alc_enabled': v.input_panel.chk_alc.isChecked(),           
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentData(),
            'dc_bias_enabled': v.input_panel.chk_dc_enable.isChecked(),
            'dc_is_voltage': True,
            'dc_bias_level': v.input_panel.combo_dc_level.value(),
        }

        self.worker = MeasurementWorker(settings)
        self.worker.data_ready.connect(self.handle_data_ready)
        self.worker.error_occurred.connect(self.handle_worker_error)
        self.worker.progress_updated.connect(self.handle_progress_update)
        self.worker.finished.connect(self.handle_worker_finished)

        self.set_ui_locked(True)
        v.lcd_display.lbl_pri_val.setText("Measuring...")
        v.lcd_display.lbl_sec_val.setText("Measuring...")

        mode_label = {"SINGLE": "วัดจุดเดียว", "SWEEP": "Sweep", "LIST": "List"}.get(run_mode, run_mode)
        scpi = settings.get('scpi_mode', '-')
        level_unit = "Arms" if settings.get('level_mode') == 'Current' else "Vrms"
        if run_mode == "SINGLE":
            freq_info = f"{settings.get('freq', '-')} Hz"
        elif run_mode == "SWEEP":
            freq_info = f"{settings.get('start_freq', '-')}–{settings.get('stop_freq', '-')} Hz"
        else:
            freq_info = "รายการความถี่"
        self.log.info(
            f"▶ เริ่มวัด | โหมด: {mode_label} | SCPI: {scpi} | "
            f"ความถี่: {freq_info} | สัญญาณ: {settings.get('volt', '-')} {level_unit} | "
            f"ALC: {'ON' if settings.get('alc_enabled') else 'OFF'}"
        )
        self.worker.start()

    def stop_measurement(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.view.ctrl_panel.btn_stop.setText("STOPPING...")
            self.view.ctrl_panel.btn_stop.setEnabled(False)
            self.log.warning("⏹ ผู้ใช้กด STOP — กำลังหยุดการวัด...")

    # ========================================================
    # การคำนวณและแสดงผลข้อมูล (Data Handling & Math)
    # ========================================================
    def handle_data_ready(self, data):
        v = self.view

        # 1. ค่าดิบจากฮาร์ดแวร์
        raw_pri = data.get('primary', 0.0)
        raw_sec = data.get('secondary', 0.0)

        # เก็บค่าดิบลง Array ไว้คำนวณ Type A Uncertainty
        self.graph_raw_pri_y.append(raw_pri)
        self.graph_raw_sec_y.append(raw_sec)

        # 2. ค่าที่จะนำไปแสดงบนกราฟและจอ LCD (อาจถูกปรับด้วย Deviation)
        disp_pri = raw_pri
        disp_sec = raw_sec

        if v.adv_panel.chk_dev_graph_enable.isChecked():
            dev_type = v.adv_panel.combo_dev_type.currentText()
            is_pct = "PCT" in dev_type or "เปอร์เซ็นต์" in dev_type

            pri_ref = self._safe_float(v.adv_panel.input_dev_pri.text())
            sec_ref = self._safe_float(v.adv_panel.input_dev_sec.text())

            if pri_ref is not None:
                if is_pct:
                    disp_pri = ((raw_pri - pri_ref) / abs(pri_ref)) * 100 if pri_ref != 0 else 0.0
                else:
                    disp_pri = raw_pri - pri_ref

            if sec_ref is not None:
                if is_pct:
                    disp_sec = ((raw_sec - sec_ref) / abs(sec_ref)) * 100 if sec_ref != 0 else 0.0
                else:
                    disp_sec = raw_sec - sec_ref

        v.lcd_display.lbl_pri_val.setText(f"{disp_pri:.5e}")
        v.lcd_display.lbl_sec_val.setText(f"{disp_sec:.5e}")

        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        if is_single:
            self.graph_x_data.append(len(self.graph_x_data) + 1)
        else:
            self.graph_x_data.append(data.get('freq', 0))

        self.graph_pri_y.append(disp_pri)
        self.graph_sec_y.append(disp_sec)

        # อัปเดตทั้งกราฟ และ Panel สถิติ (โยน raw เข้าไปคำนวณ)
        v.graph_display.update_plots(self.graph_x_data, self.graph_pri_y, self.graph_sec_y)
        v.graph_display.update_statistics(self.graph_raw_pri_y, self.graph_raw_sec_y, is_single)

        # อัปเดต Statistics Table ทุกโหมด (SINGLE=overall stats, SWEEP=per-freq raw, LIST=per-freq stats)
        self.update_statistics_table()

    def update_statistics_table(self):
        """สร้าง raw_records จากข้อมูลที่เก็บไว้ แล้วส่งให้ StatisticsTable คำนวณ/แสดงผลใหม่
        รองรับทุกโหมด: SINGLE (overall stats) / SWEEP (per-freq raw) / LIST (per-freq stats)"""
        v = self.view
        run_mode = self.get_current_run_mode()

        raw_records = [
            {'freq': f, 'primary': p, 'secondary': s}
            for f, p, s in zip(self.graph_x_data, self.graph_raw_pri_y, self.graph_raw_sec_y)
        ]

        pri_ref = self._safe_float(v.adv_panel.input_dev_pri.text()) if v.adv_panel.chk_dev_ppm_enable.isChecked() else None
        sec_ref = self._safe_float(v.adv_panel.input_dev_sec.text()) if v.adv_panel.chk_dev_ppm_enable.isChecked() else None

        v.stats_table.update_table(raw_records, pri_ref=pri_ref, sec_ref=sec_ref, mode=run_mode)

    @staticmethod
    def _safe_float(text: str):
        try:
            text = text.strip()
            return float(text) if text else None
        except (ValueError, AttributeError):
            return None

    def handle_worker_error(self, error_msg):
        self.log.error(f"Hardware Error: {error_msg}")
        QMessageBox.critical(self.view, "Hardware Error", error_msg)

    def handle_progress_update(self, percent):
        run_mode = self.get_current_run_mode()
        if run_mode in ("SWEEP", "LIST"):
            self.view.ctrl_panel.btn_start.setText(f"⏳ RUNNING... {percent}%")

    def handle_worker_finished(self):
        self.log.info("✅ การวัดเสร็จสมบูรณ์")
        self.set_ui_locked(False)
        self.worker = None

    def clear_graph_data(self):
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []
        self.graph_raw_pri_y = []
        self.graph_raw_sec_y = []
        self.view.graph_display.clear_plots()
        self.view.stats_table.clear_table()
        self.log.info("🗑 ล้างข้อมูลกราฟและตารางสถิติเรียบร้อย")
        self.update_session_lock()

    def update_session_lock(self):
        v = self.view
        has_data = len(self.graph_x_data) > 0
        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        should_lock = has_data and is_single

        v.input_panel.combo_prop_group.setEnabled(not should_lock)
        v.input_panel.combo_scpi_mode.setEnabled(not should_lock)
        v.input_panel.combo_run_mode.setEnabled(not should_lock)

        v.adv_panel.chk_dev_graph_enable.setEnabled(not should_lock)
        v.adv_panel.chk_dev_ppm_enable.setEnabled(not should_lock)
        dev_enabled = (
            (v.adv_panel.chk_dev_graph_enable.isChecked() or v.adv_panel.chk_dev_ppm_enable.isChecked())
            and not should_lock
        )
        v.adv_panel.widget_dev_inner.setEnabled(dev_enabled)
        v.adv_panel.combo_dev_type.setEnabled(v.adv_panel.chk_dev_graph_enable.isChecked() and not should_lock)

        if not should_lock:
            v.input_panel.input_start_freq.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_stop_freq.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_step_freq.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_freq_list.setEnabled(run_mode == "LIST")
            v.input_panel.input_samples.setEnabled(run_mode == "LIST")
            v.input_panel.input_discard_first.setEnabled(run_mode == "LIST")
        else:
            v.input_panel.input_start_freq.setEnabled(False)
            v.input_panel.input_stop_freq.setEnabled(False)
            v.input_panel.input_step_freq.setEnabled(False)
            v.input_panel.input_freq_list.setEnabled(False)
            v.input_panel.input_samples.setEnabled(False)
            v.input_panel.input_discard_first.setEnabled(False)

        # [restored] เช็คใหม่ทุกครั้งที่ session lock เปลี่ยน (เผื่อ mode เปลี่ยนระหว่างล็อก/ปลดล็อก)
        self.validate_freq_list()

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
        # [restored] รวม is_freqlist_error กลับเข้ามา
        is_blocked = self.is_dc_error or self.is_dev_error or self.is_visa_error or self.is_freqlist_error
        v.ctrl_panel.lbl_warn_visa.setVisible(self.is_visa_error)
        v.ctrl_panel.lbl_warn_dc_start.setVisible(self.is_dc_error)
        v.ctrl_panel.lbl_warn_dev_start.setVisible(self.is_dev_error)
        v.ctrl_panel.lbl_warn_freqlist_start.setVisible(self.is_freqlist_error)

        if is_blocked:
            v.ctrl_panel.btn_start.setText("🔒 START")
            v.ctrl_panel.btn_start.setEnabled(False)
        else:
            v.ctrl_panel.btn_start.setText("START")
            v.ctrl_panel.btn_start.setEnabled(True)

    def validate_freq_list(self):
        """
        [restored] เช็คว่ารายการความถี่ (Frequency List) ถูกกรอกและ parse ได้จริงหรือไม่
        มีผลเฉพาะตอนอยู่โหมด LIST เท่านั้น - ใช้ parser ตัวเดียวกับที่
        measurement_thread.py ใช้จริงตอนวัด (MeasurementWorker._parse_freq_list)
        เพื่อไม่ให้ผลการเช็คที่นี่กับตอนวัดจริงไม่ตรงกัน

        เช็คเพิ่มผ่าน FrequencyListWidget.is_valid() ว่ากรอกครบทุกช่อง
        (ไม่มีช่องว่างค้างระหว่างช่องที่กรอกแล้ว) และค่าที่กรอกอยู่ในช่วงสเปคเครื่อง
        (20 Hz - 2,000,000 Hz) หรือไม่ - ถ้าไม่ผ่านจะบล็อกปุ่ม Start เหมือนกัน
        พร้อมข้อความเตือนละเอียดแสดงในตัว FrequencyListWidget เอง
        """
        v = self.view
        run_mode = self.get_current_run_mode()

        if run_mode != "LIST":
            self.is_freqlist_error = False
            self.update_start_button_state()
            return

        raw_text = v.input_panel.input_freq_list.text()
        frequencies = MeasurementWorker._parse_freq_list(raw_text)

        list_widget_ok = v.input_panel.input_freq_list.is_valid()

        self.is_freqlist_error = (len(frequencies) == 0) or (not list_widget_ok)
        self.update_start_button_state()

    def toggle_run_mode(self):
        """เรียกทุกครั้งที่ Dropdown โหมดการวัด (ใน input_panel) เปลี่ยนค่า
        สลับ visibility ของเนื้อหาย่อยภายใน group_mode เดียวกัน"""
        v = self.view
        run_mode = self.get_current_run_mode()

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
                v.input_panel.combo_run_mode.blockSignals(True)
                # หมายเหตุ: ยังไม่ได้เก็บ "โหมดก่อนหน้า" ไว้ย้อนกลับแบบแม่นยำ
                # (แนะนำเพิ่ม self._last_run_mode ในอนาคตถ้าต้องการย้อนกลับ index เป๊ะๆ)
                v.input_panel.combo_run_mode.blockSignals(False)
                return

        is_single = (run_mode == "SINGLE")
        is_sweep = (run_mode == "SWEEP")
        is_list = (run_mode == "LIST")

        v.input_panel.widget_freq_single.setVisible(is_single)
        v.input_panel.widget_sweep.setVisible(is_sweep)
        v.input_panel.widget_list.setVisible(is_list)

        v.input_panel.input_start_freq.setEnabled(is_sweep)
        v.input_panel.input_stop_freq.setEnabled(is_sweep)
        v.input_panel.input_step_freq.setEnabled(is_sweep)
        v.input_panel.input_freq_list.setEnabled(is_list)
        v.input_panel.input_samples.setEnabled(is_list)
        v.input_panel.input_discard_first.setEnabled(is_list)

        # ซ่อน checkbox "คำนวณ PPM ในตารางสถิติ" เมื่อไม่ได้อยู่โหมด LIST
        # และ reset สถานะเป็นไม่ติ๊กเสมอเมื่อออกจาก LIST
        # เพื่อป้องกัน PPM ทำงานค้างอยู่ในโหมดที่ไม่รองรับ
        # ผู้ใช้ต้องกลับมา LIST แล้วติ๊กเปิดใหม่ทุกครั้ง
        if not is_list:
            v.adv_panel.chk_dev_ppm_enable.setChecked(False)
        v.adv_panel.chk_dev_ppm_enable.setVisible(is_list)

        # Sync สถานะ widget_dev_inner หลังเปลี่ยน visibility/checked state
        self.toggle_deviation()

        self.update_hardware_limits()
        self.validate_freq_list()      
        self.update_start_button_state()
        self.view.stats_table.set_mode(run_mode)

    def toggle_dc_bias(self):
        is_enabled = self.view.input_panel.chk_dc_enable.isChecked()
        self.view.input_panel.widget_dc_inner.setEnabled(is_enabled)
        if is_enabled:
            self.validate_dc_bias()
        else:
            self.view.input_panel.lbl_dc_warning.setText("")
            self.is_dc_error = False
            self.update_start_button_state()

    def validate_dc_bias(self):
        v = self.view
        if not v.input_panel.chk_dc_enable.isChecked():
            self.is_dc_error = False
            self.update_start_button_state()
            return

        warning_msg = "⚠️ ต้องต่ออุปกรณ์เข้าขั้ววัด\nก่อนเปิดสวิตช์เสมอ!"
        self.is_dc_error = False
        v.input_panel.lbl_dc_warning.setText(warning_msg)
        self.update_start_button_state()

    def _refresh_deviation_preview(self):
        """เรียกใช้ทุกครั้งที่ Ref/ประเภทกราฟ Δ เปลี่ยน เพื่ออัปเดตชื่อแกนแบบสด
        (อัปเดตเฉพาะตอนยังไม่มีข้อมูลในกราฟ - ถ้าเริ่มวัดไปแล้วชื่อแกนจะถูกล็อกไว้ตามที่ตั้งไว้ตอนเริ่ม)"""
        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

    def toggle_deviation(self):
        v = self.view
        is_enabled = v.adv_panel.chk_dev_graph_enable.isChecked() or v.adv_panel.chk_dev_ppm_enable.isChecked()
        v.adv_panel.widget_dev_inner.setEnabled(is_enabled)

        # "รูปแบบกราฟ Δ" ใช้ได้เฉพาะตอนเปิด Graph Deviation เท่านั้น
        # (แม้ widget_dev_inner โดยรวมจะ enable จาก PPM checkbox ก็ตาม)
        v.adv_panel.combo_dev_type.setEnabled(v.adv_panel.chk_dev_graph_enable.isChecked())

        if is_enabled:
            self.validate_deviation()
        else:
            v.adv_panel.lbl_dev_warning.setText("")
            self.is_dev_error = False
            self.update_start_button_state()

        self._refresh_deviation_preview()

    def validate_deviation(self):
        v = self.view
        if not (v.adv_panel.chk_dev_graph_enable.isChecked() or v.adv_panel.chk_dev_ppm_enable.isChecked()):
            self.is_dev_error = False
            self.update_start_button_state()
            return

        pri_has_value = self._safe_float(v.adv_panel.input_dev_pri.text()) is not None
        sec_has_value = self._safe_float(v.adv_panel.input_dev_sec.text()) is not None

        if not pri_has_value and not sec_has_value:
            v.adv_panel.lbl_dev_warning.setText(
                "⚠️ ต้องระบุ Primary Ref หรือ Secondary Ref อย่างน้อย 1 ค่า ก่อนเริ่มวัด"
            )
            self.is_dev_error = True
        else:
            v.adv_panel.lbl_dev_warning.setText("")
            self.is_dev_error = False
        self.update_start_button_state()