# ตัวกลางรับ Event จาก GUI ไปสั่ง Hardware และส่งผลกลับมา GUI

import time

from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, QObject

from core.measurement_thread import MeasurementWorker
from core.correction_thread import CorrectionWorker
from hardware.lcr_meter import E4980A
from data.data_processor import calculate_frequency_stats
from core import save_manager

class AppController(QObject):
    def __init__(self, view):
        super().__init__()
        self.view = view

        # ตัวแปรสถานะ
        self.is_ppm_error = False               # ป้องกัน AttributeError: เปิด PPM แต่ไม่กรอก Ref
        self.is_visa_error = True
        self.is_freqlist_error = False          # ป้องกัน AttributeError

        self.worker = None
        self.corr_worker = None
        self.verify_worker = None
        self.progress_dialog = None
        self.current_corr_type = None

        # Instance เดียวที่ถือ Connection ค้างไว้ตลอด session (ใช้ร่วมกับปุ่ม Connect/Disconnect)
        # Worker แต่ละตัว (Measurement/Correction/Verify) จะใช้ instance นี้ร่วมกัน
        # แทนที่จะเปิด-ปิด VISA session ใหม่ทุกครั้งที่กดปุ่ม
        self.lcr = E4980A()

        # ตัวแปรสำหรับเก็บข้อมูลวาดกราฟ (ค่าดิบเสมอ)
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []

        # ตัวแปรสำหรับเก็บ "ค่าดิบ (Raw Data)" เพื่อนำไปคำนวณสถิติ Type A
        self.graph_raw_pri_y = []
        self.graph_raw_sec_y = []

        # เวลาที่วัดเสร็จล่าสุด (ใช้เป็นเวลา Save จริงๆ ไม่ใช่เวลาที่กดปุ่ม Save)
        self.last_measurement_time = None
        self.last_measurement_time_iso = None

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
        self.update_single_total()
        self.update_list_total()
        self.update_sweep_total()

        # ตั้งค่า UI เริ่มต้น
        self.view.adv_panel.widget_dev_inner.setEnabled(False)

        # ตั้งค่า visibility ของเนื้อหาย่อยใน group_mode ตามโหมดเริ่มต้น (Sweep)
        self.toggle_run_mode()

    def _connect_signals(self):
        v = self.view
        v.input_panel.combo_prop_group.currentIndexChanged.connect(self.update_scpi_modes)
        # อัปเดตชื่อแกนกราฟแบบ real-time เมื่อเปลี่ยนพารามิเตอร์หรือโหมดวัด
        # (เฉพาะตอนยังไม่มีข้อมูลในกราฟ — ป้องกันชื่อแกนเปลี่ยนกลางคันขณะวัด)
        v.input_panel.combo_scpi_mode.currentIndexChanged.connect(self._refresh_graph_labels)
        v.input_panel.combo_scpi_mode.currentIndexChanged.connect(self._refresh_raw_table_headers)
        v.input_panel.combo_run_mode.currentIndexChanged.connect(self._refresh_graph_labels)
        v.input_panel.combo_scpi_mode.currentIndexChanged.connect(self._reset_correction_status)
        v.conn_panel.btn_refresh.clicked.connect(self.scan_visa_ports)
        v.conn_panel.combo_visa.currentTextChanged.connect(self.validate_visa)

        # ปุ่ม Connect / Disconnect
        v.conn_panel.btn_connect.clicked.connect(self.handle_connect)
        v.conn_panel.btn_disconnect.clicked.connect(self.handle_disconnect)

        # ผูกสัญญาณเมื่อผู้ใช้เปลี่ยนหน่วยจาก Vrms เป็น Arms ให้ไปปรับเพดานตัวเลขทันที
        v.input_panel.combo_level_mode.currentIndexChanged.connect(self.update_hardware_limits)

        # PPM Reference: เปิด/ปิด checkbox และ validate ค่า Ref ที่กรอก
        v.adv_panel.chk_dev_ppm_enable.stateChanged.connect(self.toggle_ppm)
        v.adv_panel.input_dev_pri.textChanged.connect(self.validate_ppm_ref)
        v.adv_panel.input_dev_sec.textChanged.connect(self.validate_ppm_ref)

        v.adv_panel.btn_open_corr.clicked.connect(lambda: self.start_correction("OPEN"))
        v.adv_panel.btn_short_corr.clicked.connect(lambda: self.start_correction("SHORT"))

        v.ctrl_panel.btn_verify.clicked.connect(self.handle_verify_apply)
        v.ctrl_panel.btn_clear.clicked.connect(self.handle_clear_graph)

        # Dropdown เลือกโหมดตอนนี้อยู่ใน input_panel (ย้ายมาจาก ctrl_panel)
        v.input_panel.combo_run_mode.currentIndexChanged.connect(self.toggle_run_mode)
        v.ctrl_panel.btn_start.clicked.connect(self.start_measurement)
        v.ctrl_panel.btn_stop.clicked.connect(self.stop_measurement)

        # ระบบ Save / View Save Result — ใช้ปุ่มเดิมที่อยู่ข้าง Measurement Result (lcd_display)
        v.lcd_display.btn_save.clicked.connect(self.handle_save_result)
        v.lcd_display.btn_view.clicked.connect(self.handle_view_save_result)

        v.input_panel.input_start_freq.valueChanged.connect(self.update_calculated_points)
        v.input_panel.input_stop_freq.valueChanged.connect(self.update_calculated_points)
        v.input_panel.input_step_freq.valueChanged.connect(self.update_calculated_points)

        # SINGLE: อัปเดต label รวมรอบวัดทั้งหมดเมื่อ Readings หรือ Discard เปลี่ยน
        v.input_panel.input_n_single.valueChanged.connect(self.update_single_total)
        v.input_panel.input_discard_single.valueChanged.connect(self.update_single_total)

        # LIST: อัปเดต label รวมรอบวัดทั้งหมด/ความถี่ เมื่อ Samples หรือ Discard เปลี่ยน
        v.input_panel.input_samples.valueChanged.connect(self.update_list_total)
        v.input_panel.input_discard_first.valueChanged.connect(self.update_list_total)

        # SWEEP: อัปเดต label รวมรอบวัดทั้งหมด/ความถี่ เมื่อ Samples หรือ Discard เปลี่ยน
        v.input_panel.input_samples_sweep.valueChanged.connect(self.update_sweep_total)
        v.input_panel.input_discard_first_sweep.valueChanged.connect(self.update_sweep_total)

        # ตรวจสอบ Frequency List ทุกครั้งที่มีการแก้ไข (เฉพาะมีผลตอนอยู่โหมด List)
        v.input_panel.input_freq_list.freq_changed.connect(self.validate_freq_list)

        # รีเซ็ตสถานะปุ่ม Correction เมื่อเปลี่ยนค่าที่ทำให้ Correction ใช้ไม่ได้
        # อ้างอิงจากคู่มือ E4980A หน้า 117: "after correction, different length cable/
        # different fixture is connected or settings of frequency/level is changed"
        # → Cable Length: ส่งผลโดยตรงต่อ phase compensation ของ correction
        # → Meas Mode (เช่น CPD→ZTD): เปลี่ยนฟังก์ชันวัด correction data ไม่ตรงกัน
        # → Signal Level/หน่วย: คู่มือระบุตรงๆ ว่า level เปลี่ยนแล้ว correction ไม่ valid
        v.input_panel.combo_cable.currentIndexChanged.connect(self._reset_correction_status)
        v.input_panel.combo_scpi_mode.currentIndexChanged.connect(self._reset_correction_status)
        v.input_panel.input_volt.valueChanged.connect(self._reset_correction_status)
        v.input_panel.combo_level_mode.currentIndexChanged.connect(self._reset_correction_status)

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

    def update_single_total(self):
        """คำนวณและแสดงรวมรอบวัดทั้งหมดของโหมด SINGLE
        รวมรอบ = Discard First + Readings Count
        (จำนวนครั้งที่เครื่องจะวัดจริงทั้งหมดต่อ 1 ครั้งที่กด Start)"""
        v = self.view
        n = v.input_panel.input_n_single.value()
        d = v.input_panel.input_discard_single.value()
        total = n + d
        v.input_panel.lbl_total_rounds_single.setText(f"{total} ครั้ง  (ทิ้ง {d} + วัด{n})")

    def update_list_total(self):
        """คำนวณและแสดงรวมรอบวัดทั้งหมดต่อความถี่ของโหมด LIST
        รวมรอบ/ความถี่ = Discard First + Samples per Sweep
        (จำนวนครั้งที่เครื่องวัดต่อ 1 ความถี่ ก่อนขยับไปความถี่ถัดไป)"""
        v = self.view
        s = v.input_panel.input_samples.value()
        d = v.input_panel.input_discard_first.value()
        total = s + d
        v.input_panel.lbl_total_rounds_list.setText(f"{total} ครั้ง/ความถี่ \n (ทิ้ง {d} + วัด {s})")

    def update_sweep_total(self):
        """คำนวณและแสดงรวมรอบวัดทั้งหมดต่อความถี่ของโหมด SWEEP
        รวมรอบ/ความถี่ = Discard First + Samples per Sweep
        (เหมือน LIST — ใช้ widget แยกกันเพราะ SWEEP กับ LIST แสดงพร้อมกันไม่ได้อยู่แล้ว)"""
        v = self.view
        s = v.input_panel.input_samples_sweep.value()
        d = v.input_panel.input_discard_first_sweep.value()
        total = s + d
        v.input_panel.lbl_total_rounds_sweep.setText(f"{total} ครั้ง/ความถี่ \n (ทิ้ง {d} + วัด {s})")

    def update_hardware_limits(self):
        """อัปเดตเพดานสูงสุดของกล่องกรอกระดับสัญญาณ ตามโหมด V/I ที่ผู้ใช้เลือก"""
        v = self.view
        level_mode = v.input_panel.combo_level_mode.currentData()
        
        # สมมติฐาน: เป็นเครื่องรุ่นมาตรฐาน (ไม่มี Option 001)
        if level_mode == "Voltage":
            v.input_panel.input_volt.setMaximum(2.0)
            v.input_panel.input_volt.setToolTip("โหมดแรงดัน: จ่ายสัญญาณได้สูงสุด 2.0 Vrms (เครื่องรุ่นมาตรฐาน)")
        else: # โหมด Current (Arms)
            v.input_panel.input_volt.setMaximum(0.02) # 20 mArms
            v.input_panel.input_volt.setToolTip("โหมดกระแส: จ่ายสัญญาณได้สูงสุด 0.02 Arms หรือ 20 mArms (เครื่องรุ่นมาตรฐาน)")
            
            # ป้องกันกรณีผู้ใช้กรอก 1.0 Vrms ทิ้งไว้ พอสลับเป็น Arms ค่าจะเกินสเปค
            # ให้ปัดตัวเลขลงมาที่ 0.02 อัตโนมัติ
            if v.input_panel.input_volt.value() > 0.02:
                v.input_panel.input_volt.setValue(0.02)

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
        """
        ล็อก/ปลดล็อก UI ระหว่างการวัด เพื่อป้องกันผู้ใช้เปลี่ยนค่าจนโปรแกรมพัง

        ล็อกระหว่างวัด (locked=True):
          - conn_panel  : VISA dropdown + ปุ่ม Refresh (ห้ามเปลี่ยนเครื่องกลางวัด)
          - input_panel : ทุก widget (Meas mode, ความถี่, Signal Level,
                          Hardware/Timing, Freq List, Run mode)
          - adv_panel   : Correction buttons + Deviation inputs/checkboxes
                          (ห้ามทำ Correction หรือเปลี่ยน Ref กลางวัด)
          - ctrl_panel  : ปุ่ม Verify & Apply + ปุ่ม Clear Data
        ไม่ล็อก:
          - btn_stop    : ต้องกดหยุดได้เสมอ
          - log_display : ผู้ใช้ต้องอ่าน log ระหว่างวัดได้

        เมื่อปลดล็อก (locked=False):
          - คืนสถานะ Start button ตาม error flags ปัจจุบัน
          - คืนสถานะ session lock ตามโหมดและข้อมูลในกราฟ
        """
        v = self.view

        # --- Connection Panel ---
        # [แก้ไข] ตอน lock (กำลังวัด/Correction/Verify) ต้องล็อกปุ่ม Connect/Disconnect ด้วย
        # เพื่อป้องกันผู้ใช้ตัดการเชื่อมต่อกลางคัน — ตอนปลดล็อกค่อยคืนสถานะตาม self.lcr.is_connected จริง
        v.conn_panel.btn_connect.setEnabled(not locked and not self.lcr.is_connected)
        v.conn_panel.btn_disconnect.setEnabled(not locked and self.lcr.is_connected)
        v.conn_panel.combo_visa.setEnabled(not locked and not self.lcr.is_connected)
        v.conn_panel.btn_refresh.setEnabled(not locked and not self.lcr.is_connected)

        # --- Input Panel (ทุก group) ---
        # ล็อก group ระดับบนด้วย setEnabled ครอบคลุมทุก widget ใน group นั้นทันที
        v.input_panel.group_prop.setEnabled(not locked)   # Meas mode group
        v.input_panel.group_mode.setEnabled(not locked)   # ความถี่ / Sweep / List group
        v.input_panel.group_signal.setEnabled(not locked) # Signal Level + ALC
        v.input_panel.group_hw.setEnabled(not locked)     # Hardware & Timing
        v.input_panel.combo_run_mode.setEnabled(not locked)

        # --- Advanced Panel ---
        v.adv_panel.btn_open_corr.setEnabled(not locked)
        v.adv_panel.btn_short_corr.setEnabled(not locked)
        v.adv_panel.chk_dev_ppm_enable.setEnabled(not locked)
        v.adv_panel.widget_dev_inner.setEnabled(not locked)

        # --- Control Panel ---
        v.ctrl_panel.btn_verify.setEnabled(not locked)
        v.ctrl_panel.btn_clear.setEnabled(not locked)
        v.ctrl_panel.btn_stop.setEnabled(locked)   # ต้องกดได้เสมอตอนวัด

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
        if not self.lcr.is_connected:
            QMessageBox.warning(v, "ตรวจสอบล้มเหลว", "กรุณากด CONNECT เพื่อเชื่อมต่อเครื่อง LCR Meter ก่อนทำการตรวจสอบการตั้งค่า")
            return

        # [จุดที่ 4] Verify & Apply ส่งความถี่จาก input_freq (Single Point) เสมอ
        # ถ้าผู้ใช้อยู่ใน SWEEP/LIST mode ความถี่ที่ส่งไปอาจไม่ตรงกับที่ใช้วัดจริง
        # แจ้งเตือนเพื่อให้รับทราบก่อนดำเนินการ (ไม่บล็อก เพราะยังมีประโยชน์สำหรับ
        # เช็คค่าตั้งอื่นๆ เช่น Signal Level, Aperture, Cable ที่ใช้ร่วมกันทุกโหมด)
        run_mode = self.get_current_run_mode()
        if run_mode in ("SWEEP", "LIST"):
            mode_name = "Sweep" if run_mode == "SWEEP" else "List"
            reply = QMessageBox.question(
                v,
                "แจ้งเตือน — โหมด Verify ในขณะอยู่โหมด " + mode_name,
                f"ขณะนี้อยู่ในโหมด {mode_name} ซึ่งวัดหลายความถี่\n\n"
                f"Verify & Apply จะส่งและเช็คค่าที่ความถี่ {v.input_panel.input_freq.value():.2f} Hz\n"
                f"(จาก Single Point Frequency ไม่ใช่ช่วงความถี่ใน {mode_name})\n\n"
                "ต้องการดำเนินการ Verify & Apply ต่อหรือไม่?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        settings = {
            'visa_resource': v.conn_panel.combo_visa.currentText(),
            'freq': v.input_panel.input_freq.value(),
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'level_mode': v.input_panel.combo_level_mode.currentData(),
            'alc_enabled': v.input_panel.chk_alc.isChecked(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentData(),
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
        self.verify_worker = VerifyWorker(self.lcr, settings)
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
        if not self.lcr.is_connected:
            QMessageBox.warning(v, "เชื่อมต่อล้มเหลว", "กรุณากด CONNECT เพื่อเชื่อมต่อเครื่อง LCR Meter ก่อนทำการชดเชยค่า")
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

        # [แก้ไข] ส่งค่า Cable Length ปัจจุบันจาก GUI ไปด้วย เพื่อตั้งที่เครื่องก่อนทำ Correction เสมอ
        cable_text = v.input_panel.combo_cable.currentText()
        self.corr_worker = CorrectionWorker(self.lcr, corr_type, cable_text)
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

    def _reset_correction_status(self):
        """
        รีเซ็ตปุ่ม OPEN/SHORT Correction กลับสู่สถานะเริ่มต้น (สีเทา / ไม่มี OK)
        เรียกอัตโนมัติเมื่อผู้ใช้เปลี่ยนค่าที่ทำให้ Correction data ที่ทำไว้ไม่ valid อีกต่อไป
        ได้แก่: Cable Length, Meas Mode, Signal Level, Signal Level Unit
        (อ้างอิงคู่มือ E4980A หน้า 117)

        หมายเหตุ: method นี้รีเซ็ตเฉพาะ label/style บนปุ่ม GUI เพื่อแจ้งเตือนผู้ใช้
        ข้อมูล Correction ที่อยู่ในตัวเครื่อง (hardware) ไม่ถูกลบ — ผู้ใช้ต้องกด
        OPEN/SHORT Correction ใหม่เองเพื่อให้ข้อมูลตรงกับการตั้งค่าปัจจุบัน
        """
        adv = self.view.adv_panel
        default_style = ""  # คืน stylesheet เป็นค่าว่าง -> ใช้ style จาก QSS ของโปรแกรม

        open_is_ok  = adv.btn_open_corr.text()  == "OPEN Correction (OK)"
        short_is_ok = adv.btn_short_corr.text() == "SHORT Correction (OK)"

        if open_is_ok:
            adv.btn_open_corr.setStyleSheet(default_style)
            adv.btn_open_corr.setText("OPEN Correction")
            self.log.warning(
                "⚠️ การตั้งค่าเปลี่ยน — OPEN Correction อาจไม่ valid แล้ว กรุณาทำ Correction ใหม่"
            )

        if short_is_ok:
            adv.btn_short_corr.setStyleSheet(default_style)
            adv.btn_short_corr.setText("SHORT Correction")
            self.log.warning(
                "⚠️ การตั้งค่าเปลี่ยน — SHORT Correction อาจไม่ valid แล้ว กรุณาทำ Correction ใหม่"
            )

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
        elif scpi_mode.startswith("Y"):
            pri_label = "Admittance, Y (S)"
        elif scpi_mode == "GB":
            pri_label = "Conductance, G (S)"

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

        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        is_list   = (run_mode == "LIST")
        is_sweep  = (run_mode == "SWEEP")

        # LIST และ SWEEP ใช้แกน X เป็นลำดับจุดเหมือน SINGLE (กันกราฟซิกแซกเมื่อ samples > 1)
        x_label = "Measurement Count (Points)" if (is_single or is_list or is_sweep) else "Frequency (Hz)"

        v.graph_display.set_axis_labels(
            x_label=x_label,
            pri_y_label=pri_label,
            sec_y_label=sec_label,
            is_single_mode=(is_single or is_list or is_sweep)
        )
        v.freq_summary_graph.set_axis_labels(pri_label=pri_label, sec_label=sec_label)
        v.ppm_summary_graph.set_axis_labels(pri_label=pri_label, sec_label=sec_label)

    def _refresh_graph_labels(self):
        """
        อัปเดตชื่อแกนกราฟแบบ real-time เมื่อผู้ใช้เปลี่ยน scpi_mode หรือ run_mode
        เรียกเฉพาะตอนยังไม่มีข้อมูลในกราฟ เพื่อป้องกันชื่อแกนเปลี่ยนกลางคันขณะวัด
        (ถ้ามีข้อมูลแล้ว ชื่อแกนจะถูกล็อกตามที่ตั้งไว้ตอนกด Start)
        """
        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

    def _refresh_raw_table_headers(self):
        """อัปเดตชื่อคอลัมน์ Primary/Secondary ใน Raw Data Table
        เมื่อผู้ใช้เปลี่ยน SCPI Mode เช่น CPD → Cp, D หรือ ZTD → Z, θd"""
        self.view.raw_table.update_headers(
            self.view.input_panel.combo_scpi_mode.currentData()
        )

    def start_measurement(self):
        # ป้องกัน edge case ที่ปุ่ม Start เปิดได้ทั้งที่มี error ค้างอยู่
        # (เช่น state ไม่ sync กัน หรือ race condition ระหว่าง signal)
        # เป็น safety net ชั้นที่ 2 ถัดจาก update_start_button_state() ที่ disable ปุ่มไว้
        if self.is_ppm_error or self.is_visa_error or self.is_freqlist_error:
            self.log.warning("⚠️ ไม่สามารถเริ่มวัดได้ — ยังมีข้อผิดพลาดค้างอยู่ กรุณาตรวจสอบและแก้ไขก่อน")
            return

        v = self.view
        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")

        # [NEW] เตรียมตาราง Raw Data ก่อนเริ่มวัด
        v.raw_table.set_mode(run_mode)
        v.raw_table.update_headers(v.input_panel.combo_scpi_mode.currentData())

        if not is_single:
            self.graph_x_data = []
            self.graph_pri_y = []
            self.graph_sec_y = []
            self.graph_raw_pri_y = []
            self.graph_raw_sec_y = []
            v.graph_display.clear_plots()
            v.freq_summary_graph.clear()
            v.ppm_summary_graph.clear()
            v.raw_table.clear_table()  # ล้างข้อมูลดิบเก่าเมื่อเริ่มวัดใหม่

        if len(self.graph_x_data) == 0:
            self.setup_graph_labels()

        # SWEEP และ LIST มีช่องกรอก Samples/Discard แยกกันคนละ widget
        # (ใช้ค่าตาม widget ของโหมดที่กำลังทำงานอยู่จริง)
        if run_mode == "SWEEP":
            samples_val = v.input_panel.input_samples_sweep.value()
            discard_val = v.input_panel.input_discard_first_sweep.value()
        else:
            samples_val = v.input_panel.input_samples.value()
            discard_val = v.input_panel.input_discard_first.value()

        settings = {
            'run_mode': run_mode,  # 'SINGLE' / 'SWEEP' / 'LIST'
            'visa_resource': v.conn_panel.combo_visa.currentText(),
            'freq': v.input_panel.input_freq.value(),
            'start_freq': v.input_panel.input_start_freq.value(),
            'stop_freq': v.input_panel.input_stop_freq.value(),
            'step_freq': v.input_panel.input_step_freq.value(),
            'freq_list_raw': v.input_panel.input_freq_list.text(),
            'samples_per_freq': samples_val,
            'discard_first': discard_val,
            # _run_single_measurement() ใช้ทั้ง 3 ค่านี้ — ถ้าไม่ส่งมา
            # จะ fallback เป็น n=1, discard=0 ทำให้การตั้งค่าใน UI ไม่มีผลเลย
            'n_single':               v.input_panel.input_n_single.value(),
            'discard_single':         v.input_panel.input_discard_single.value(),
            'is_first_single_session': len(self.graph_x_data) == 0,
            'scpi_mode': v.input_panel.combo_scpi_mode.currentData(),
            'volt': v.input_panel.input_volt.value(),
            'level_mode': v.input_panel.combo_level_mode.currentData(),
            'alc_enabled': v.input_panel.chk_alc.isChecked(),
            'time_mode': v.input_panel.combo_time.currentText(),
            'avg': v.input_panel.input_avg.value(),
            'cable': v.input_panel.combo_cable.currentText(),
            'imp_range': v.input_panel.combo_range.currentData(),
        }

        self.worker = MeasurementWorker(self.lcr, settings)
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
        status  = data.get('status', 'SUCCESS')  #รับค่า status ที่มาจาก Thread

        # เก็บค่าดิบลง Array ไว้คำนวณ Type A Uncertainty
        self.graph_raw_pri_y.append(raw_pri)
        self.graph_raw_sec_y.append(raw_sec)

        # กราฟและ LCD แสดงค่าดิบเสมอ (ไม่มี Graph Deviation แล้ว)
        v.lcd_display.lbl_pri_val.setText(f"{raw_pri:.5e}")
        v.lcd_display.lbl_sec_val.setText(f"{raw_sec:.5e}")

        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        is_list = (run_mode == "LIST")
        is_sweep = (run_mode == "SWEEP")

        # --- [NEW] ลอจิกเตรียมข้อมูลให้ Raw Data Table ---
        no_val = len(self.graph_x_data) + 1  # ลำดับที่ของการวัด (1, 2, 3...)
        current_freq = data.get('freq', 0)

        # จัดรูปแบบข้อความ "Samples (N)" ให้ตรงกับโหมด
        if is_single:
            n_single = v.input_panel.input_n_single.value()
            sample_text = f"{no_val}/{n_single}"  # ตัวอย่าง: 1/5, 2/5
            freq_val = v.input_panel.input_freq.value()
        elif is_list:
            n_samples = v.input_panel.input_samples.value()
            current_sample = data.get('sample_index', 1)
            sample_text = f"{current_sample}/{n_samples}"  # ตัวอย่าง: 1/3, 2/3
            freq_val = current_freq
        else:  # SWEEP (เหมือน LIST — วัดซ้ำได้หลายครั้งต่อความถี่)
            n_samples = v.input_panel.input_samples_sweep.value()
            current_sample = data.get('sample_index', 1)
            sample_text = f"{current_sample}/{n_samples}"
            freq_val = current_freq

        # ส่งให้ Raw Data Table แสดงผล
        v.raw_table.append_row({
            'no': no_val,
            'freq': freq_val,
            'sample_text': sample_text,
            'primary': raw_pri,
            'secondary': raw_sec,
            'status': status
        })
        # ----------------------------------------

        if is_single:
            self.graph_x_data.append(len(self.graph_x_data) + 1)
        else:
            self.graph_x_data.append(current_freq)

        self.graph_pri_y.append(raw_pri)
        self.graph_sec_y.append(raw_sec)

        # ถ้าเป็น LIST หรือ SWEEP mode ให้ส่งแกน X เป็นลำดับ 1, 2, 3... ไปวาดกราฟ
        # (กันกราฟซิกแซกเมื่อ samples > 1 ต่อความถี่ — สอดคล้องกับ label แกน X
        # ที่ตั้งไว้ใน setup_graph_labels ว่าเป็น "Measurement Count (Points)")
        if is_list or is_sweep:
            plot_x = list(range(1, len(self.graph_x_data) + 1))
        else:
            plot_x = self.graph_x_data

        v.graph_display.update_plots(plot_x, self.graph_pri_y, self.graph_sec_y)
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

        # ส่ง Ref เฉพาะตอน checkbox PPM เปิด — ใช้ได้ทั้ง SINGLE, SWEEP และ LIST
        ppm_enabled = v.adv_panel.chk_dev_ppm_enable.isChecked()
        pri_ref = self._safe_float(v.adv_panel.input_dev_pri.text()) if ppm_enabled else None
        sec_ref = self._safe_float(v.adv_panel.input_dev_sec.text()) if ppm_enabled else None

        v.stats_table.update_table(raw_records, pri_ref=pri_ref, sec_ref=sec_ref, mode=run_mode)

        # กราฟ "vs Frequency" มีความหมายเฉพาะ LIST/SWEEP เท่านั้น
        # (SINGLE มีความถี่เดียว ไม่มีเส้นแนวโน้มให้ลาก)
        if run_mode in ("LIST", "SWEEP") and raw_records:
            freq_stats = calculate_frequency_stats(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
            v.freq_summary_graph.update_data(
                freqs=[s['freq'] for s in freq_stats],
                pri_mean=[s['pri_mean'] for s in freq_stats],
                pri_sd=[s['pri_sd'] or 0.0 for s in freq_stats],
                sec_mean=[s['sec_mean'] for s in freq_stats],
                sec_sd=[s['sec_sd'] or 0.0 for s in freq_stats],
            )
            v.ppm_summary_graph.update_data(
                freqs=[s['freq'] for s in freq_stats],
                pri_ppm=[s['pri_ppm'] for s in freq_stats],
                pri_err=[self._sd_to_ppm(s['pri_sd'], pri_ref) for s in freq_stats],
                sec_ppm=[s['sec_ppm'] for s in freq_stats],
                sec_err=[self._sd_to_ppm(s['sec_sd'], sec_ref) for s in freq_stats],
            )
        else:
            v.freq_summary_graph.clear()
            v.ppm_summary_graph.clear()

    @staticmethod
    def _safe_float(text: str):
        try:
            text = text.strip()
            return float(text) if text else None
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _sd_to_ppm(sd, ref):
        """SD Error Bar (Stability, ppm) = SD / |Ref| × 1,000,000
        ต่างจาก Type A ppm (SD/√N/|Ref|×1e6) ตรงที่ไม่หารด้วย √N —
        สะท้อนความกระจายตัว/เสถียรภาพของการวัดซ้ำจริงๆ ไม่ใช่ความเชื่อมั่นในค่าเฉลี่ย
        คืน None ถ้าไม่มี SD หรือไม่มีค่าอ้างอิง (ยังไม่เปิด PPM Reference)"""
        if sd is None or ref is None:
            return None
        try:
            ref = float(ref)
        except (TypeError, ValueError):
            return None
        if ref == 0:
            return None
        return (sd / abs(ref)) * 1_000_000

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

        # จำเวลาที่วัดเสร็จไว้ ณ ตอนนี้ — นี่คือเวลาที่จะใช้ตอน Save Result จริงๆ
        # (ไม่ใช่เวลาที่ผู้ใช้กดปุ่ม Save Result ซึ่งอาจกดทีหลังก็ได้)
        self.last_measurement_time_iso = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last_measurement_time = time.strftime("%d/%m/%Y %H:%M:%S")

    def clear_graph_data(self):
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []
        self.graph_raw_pri_y = []
        self.graph_raw_sec_y = []
        self.view.graph_display.clear_plots()
        self.view.freq_summary_graph.clear()
        self.view.ppm_summary_graph.clear()
        self.view.stats_table.clear_table()
        self.view.raw_table.clear_table()
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

        v.adv_panel.chk_dev_ppm_enable.setEnabled(not should_lock)
        ppm_inner_enabled = v.adv_panel.chk_dev_ppm_enable.isChecked() and not should_lock
        v.adv_panel.widget_dev_inner.setEnabled(ppm_inner_enabled)

        if not should_lock:
            v.input_panel.input_start_freq.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_stop_freq.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_step_freq.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_samples_sweep.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_discard_first_sweep.setEnabled(run_mode == "SWEEP")
            v.input_panel.input_freq_list.setEnabled(run_mode == "LIST")
            v.input_panel.input_samples.setEnabled(run_mode == "LIST")
            v.input_panel.input_discard_first.setEnabled(run_mode == "LIST")
        else:
            v.input_panel.input_start_freq.setEnabled(False)
            v.input_panel.input_stop_freq.setEnabled(False)
            v.input_panel.input_step_freq.setEnabled(False)
            v.input_panel.input_samples_sweep.setEnabled(False)
            v.input_panel.input_discard_first_sweep.setEnabled(False)
            v.input_panel.input_freq_list.setEnabled(False)
            v.input_panel.input_samples.setEnabled(False)
            v.input_panel.input_discard_first.setEnabled(False)

        # [restored] เช็คใหม่ทุกครั้งที่ session lock เปลี่ยน (เผื่อ mode เปลี่ยนระหว่างล็อก/ปลดล็อก)
        self.validate_freq_list()

    def validate_visa(self):
        """[แก้ไข] ปุ่ม Start ต้องรอ 'เชื่อมต่อจริง' (self.lcr.is_connected) ไม่ใช่แค่มีรายการใน Dropdown
        ฟังก์ชันนี้ยังคงเรียกตอนเปลี่ยน Dropdown เพื่อ refresh สถานะปุ่ม Connect เท่านั้น"""
        self.is_visa_error = not self.lcr.is_connected
        self.update_start_button_state()

    def handle_connect(self):
        """[NEW] เชื่อมต่อกับเครื่อง LCR Meter ค้างไว้ (ใช้ instance เดียวตลอด session)"""
        v = self.view
        visa_address = v.conn_panel.combo_visa.currentText()

        if not visa_address or visa_address == "No Device Found":
            QMessageBox.warning(v, "เชื่อมต่อล้มเหลว", "ไม่พบ VISA Resource ที่ถูกต้อง กรุณากด REFRESH แล้วเลือกพอร์ตก่อน")
            return

        if self.lcr.is_connected:
            return  # ป้องกันกดซ้ำ (ปกติปุ่มจะถูก disable อยู่แล้ว)

        self.log.info(f"🔌 กำลังเชื่อมต่อ {visa_address} ...")
        success, msg = self.lcr.connect(visa_address)

        if success:
            v.conn_panel.set_connected_ui(True, visa_address)
            self.log.info(f"✅ เชื่อมต่อสำเร็จ: {msg}")
        else:
            v.conn_panel.set_connected_ui(False)
            self.log.error(f"❌ เชื่อมต่อล้มเหลว: {msg}")
            QMessageBox.critical(v, "เชื่อมต่อล้มเหลว", msg)

        self.validate_visa()

    def handle_disconnect(self):
        """[NEW] ตัดการเชื่อมต่อกับเครื่อง LCR Meter"""
        v = self.view

        if self.worker is not None or self.corr_worker is not None or self.verify_worker is not None:
            QMessageBox.warning(v, "กำลังทำงานอยู่", "กรุณารอให้การวัด/Correction/Verify ปัจจุบันเสร็จสิ้นก่อน แล้วค่อย Disconnect")
            return

        self.lcr.disconnect()
        v.conn_panel.set_connected_ui(False)
        self.log.info("🔌 ตัดการเชื่อมต่อเครื่อง LCR Meter เรียบร้อยแล้ว")
        self.validate_visa()

    def update_scpi_modes(self):
        self.view.input_panel.combo_scpi_mode.clear()
        selected_group = self.view.input_panel.combo_prop_group.currentText()
        modes = self.meas_options.get(selected_group, [])
        for display_text, scpi_code in modes:
            self.view.input_panel.combo_scpi_mode.addItem(f"{scpi_code} ({display_text})", userData=scpi_code)

    def update_start_button_state(self):
        v = self.view
        is_blocked = self.is_ppm_error or self.is_visa_error or self.is_freqlist_error
        v.ctrl_panel.lbl_warn_visa.setVisible(self.is_visa_error)
        v.ctrl_panel.lbl_warn_dev_start.setVisible(self.is_ppm_error)
        v.ctrl_panel.lbl_warn_freqlist_start.setVisible(self.is_freqlist_error)

        if is_blocked:
            v.ctrl_panel.btn_start.setText("🔒 START")
            v.ctrl_panel.btn_start.setEnabled(False)
        else:
            v.ctrl_panel.btn_start.setText("START")
            v.ctrl_panel.btn_start.setEnabled(True)

    def validate_freq_list(self):
        """
        เช็คว่ารายการความถี่ (Frequency List) ถูกกรอกและ parse ได้จริงหรือไม่
        มีผลเฉพาะตอนอยู่โหมด LIST เท่านั้น — ใช้ parser ตัวเดียวกับที่
        measurement_thread.py ใช้จริงตอนวัด (MeasurementWorker._parse_freq_list)
        เพื่อไม่ให้ผลการเช็คที่นี่กับตอนวัดจริงไม่ตรงกัน

        เงื่อนไขที่บล็อกปุ่ม Start:
        1. parse แล้วได้ความถี่ 0 จุด (ว่างหรือกรอกผิดทั้งหมด)
        2. FrequencyListWidget.is_valid() ไม่ผ่าน (กรอกไม่ครบ / เกินสเปค)
        3. [จุดที่ 3] มีความถี่ซ้ำกัน — calculate_frequency_stats() จะรวม record
           ของสองความถี่นั้นเป็นกลุ่มเดียว ทำให้ผลสถิติและจำนวน n_samples ผิดเพี้ยน
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

        # ตรวจสอบความถี่ซ้ำ โดยปัดเศษ 6 ตำแหน่งเหมือนกับที่
        # calculate_frequency_stats() ใช้จัดกลุ่ม (round(freq, 6) เป็น key)
        # เพื่อให้ผลการเช็คตรงกับพฤติกรรมจริงตอนประมวลผลสถิติ
        has_duplicate = len(frequencies) != len(set(round(f, 6) for f in frequencies))
        if has_duplicate:
            # แสดงข้อความเตือนซ้อนทับใน FrequencyListWidget โดยตรง
            # (ใช้ lbl_incomplete ที่มีอยู่แล้ว ไม่ต้องเพิ่ม widget ใหม่)
            v.input_panel.input_freq_list.lbl_incomplete.setText(
                "⚠️ มีความถี่ซ้ำกันในรายการ — กรุณาแก้ไขให้แต่ละความถี่ไม่ซ้ำกัน\n"
                "(ความถี่ซ้ำจะทำให้ผลสถิติของกลุ่มนั้นรวมกัน จำนวน n_samples ผิด)"
            )
            v.input_panel.input_freq_list.lbl_incomplete.setVisible(True)

        self.is_freqlist_error = (len(frequencies) == 0) or (not list_widget_ok) or has_duplicate
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
        v.input_panel.input_samples_sweep.setEnabled(is_sweep)
        v.input_panel.input_discard_first_sweep.setEnabled(is_sweep)
        v.input_panel.input_freq_list.setEnabled(is_list)
        v.input_panel.input_samples.setEnabled(is_list)
        v.input_panel.input_discard_first.setEnabled(is_list)

        # Tab "กราฟสรุปตามความถี่" และ "กราฟ PPM" มีความหมายเฉพาะ SWEEP/LIST
        # (SINGLE มีความถี่เดียว ไม่มีเส้นแนวโน้มให้ดู) — ซ่อน Tab ไปเลยกันผู้ใช้สับสน
        v.right_tabs.setTabVisible(v.freq_graph_tab_index, is_sweep or is_list)
        v.right_tabs.setTabVisible(v.ppm_graph_tab_index, is_sweep or is_list)

        # PPM Reference ใช้ได้ทุกโหมด (SINGLE, SWEEP, LIST)
        # เพราะทุกโหมดวัดซ้ำได้แล้ว (SWEEP มี Samples per Sweep + Discard First เหมือน LIST)
        # จึงมี Mean ให้คำนวณ PPM Deviation ได้เสมอ — ไม่ต้องซ่อน group นี้อีกต่อไป

        # Sync สถานะ widget_dev_inner หลังเปลี่ยน visibility/checked state
        self.toggle_ppm()

        self.update_hardware_limits()
        self.validate_freq_list()
        self.update_start_button_state()
        self.view.stats_table.set_mode(run_mode)
        # อัปเดตหัวคอลัมน์ Raw Data Table แบบ real-time เมื่อเปลี่ยนโหมด
        # set_mode() ปรับหัวคอลัมน์ตามโหมด (ทุกโหมดตอนนี้ใช้ "Samples (N)" เหมือนกัน)
        self.view.raw_table.set_mode(run_mode)
        self.view.raw_table.update_headers(
            self.view.input_panel.combo_scpi_mode.currentData()
        )

    def toggle_ppm(self):
        """เปิด/ปิด widget กรอก PPM Reference ตาม checkbox สถานะ"""
        v = self.view
        is_enabled = v.adv_panel.chk_dev_ppm_enable.isChecked()
        v.adv_panel.widget_dev_inner.setEnabled(is_enabled)

        if is_enabled:
            self.validate_ppm_ref()
        else:
            v.adv_panel.lbl_dev_warning.setText("")
            self.is_ppm_error = False
            self.update_start_button_state()

    def validate_ppm_ref(self):
        """
        ตรวจสอบว่ากรอก Primary Ref หรือ Secondary Ref อย่างน้อย 1 ค่าเมื่อเปิด PPM
        ถ้าเปิด PPM แล้วไม่กรอกค่าใดเลย จะบล็อกปุ่ม Start เพราะผล PPM Dev จะเป็น '-' ทั้งหมด
        """
        v = self.view
        if not v.adv_panel.chk_dev_ppm_enable.isChecked():
            self.is_ppm_error = False
            self.update_start_button_state()
            return

        pri_has_value = self._safe_float(v.adv_panel.input_dev_pri.text()) is not None
        sec_has_value = self._safe_float(v.adv_panel.input_dev_sec.text()) is not None

        if not pri_has_value and not sec_has_value:
            v.adv_panel.lbl_dev_warning.setText(
                "⚠️ ต้องระบุ Primary Ref หรือ Secondary Ref อย่างน้อย 1 ค่า ก่อนเริ่มวัด"
            )
            self.is_ppm_error = True
        else:
            v.adv_panel.lbl_dev_warning.setText("")
            self.is_ppm_error = False
        self.update_start_button_state()

    # ========================================================
    # [NEW] ระบบ Save / View Save Result / Open Save
    # ========================================================
    def _build_save_snapshot(self) -> dict:
        """รวบรวม Input ทั้งหมด + ผลลัพธ์ ณ ปัจจุบันเป็น dict เดียว พร้อมบันทึกลงไฟล์
        เวลาที่บันทึกในไฟล์ (meta.measurement_time) คือเวลาที่ "วัดเสร็จ" ล่าสุด
        (self.last_measurement_time) ไม่ใช่เวลาที่ผู้ใช้กดปุ่ม Save Result"""
        v = self.view
        run_mode = self.get_current_run_mode()

        measurement_time = self.last_measurement_time or time.strftime("%d/%m/%Y %H:%M:%S")
        measurement_time_iso = self.last_measurement_time_iso or time.strftime("%Y-%m-%d %H:%M:%S")

        snapshot = {
            "meta": {
                "save_name": "",  # ใส่ค่าจริงตอนเรียก save_manager.save_result()
                "measurement_time": measurement_time,
                "measurement_time_iso": measurement_time_iso,
                "run_mode": run_mode,
            },
            "inputs": {
                "visa_resource": v.conn_panel.combo_visa.currentText(),
                "prop_group": v.input_panel.combo_prop_group.currentText(),
                "scpi_mode": v.input_panel.combo_scpi_mode.currentData(),
                "run_mode": run_mode,
                "freq": v.input_panel.input_freq.value(),
                "n_single": v.input_panel.input_n_single.value(),
                "discard_single": v.input_panel.input_discard_single.value(),
                "start_freq": v.input_panel.input_start_freq.value(),
                "stop_freq": v.input_panel.input_stop_freq.value(),
                "step_freq": v.input_panel.input_step_freq.value(),
                "samples_sweep": v.input_panel.input_samples_sweep.value(),
                "discard_first_sweep": v.input_panel.input_discard_first_sweep.value(),
                "freq_list": v.input_panel.input_freq_list.get_frequencies(),
                "samples_list": v.input_panel.input_samples.value(),
                "discard_first_list": v.input_panel.input_discard_first.value(),
                "volt": v.input_panel.input_volt.value(),
                "level_mode": v.input_panel.combo_level_mode.currentData(),
                "alc_enabled": v.input_panel.chk_alc.isChecked(),
                "time_mode": v.input_panel.combo_time.currentText(),
                "avg": v.input_panel.input_avg.value(),
                "cable": v.input_panel.combo_cable.currentText(),
                "imp_range": v.input_panel.combo_range.currentData(),
                "ppm_enabled": v.adv_panel.chk_dev_ppm_enable.isChecked(),
                "ppm_pri_ref": v.adv_panel.input_dev_pri.text(),
                "ppm_sec_ref": v.adv_panel.input_dev_sec.text(),
            },
            "results": {
                "graph_x_data": self.graph_x_data,
                "graph_pri_y": self.graph_pri_y,
                "graph_sec_y": self.graph_sec_y,
                "graph_raw_pri_y": self.graph_raw_pri_y,
                "graph_raw_sec_y": self.graph_raw_sec_y,
                "raw_table_rows": v.raw_table.get_rows(),
            },
        }
        return snapshot

    def handle_save_result(self):
        """เมื่อกดปุ่ม 'Save Result' — เด้งป๊อปอัพให้ตั้งชื่อ แล้วบันทึก Input + ผลลัพธ์ปัจจุบันทั้งหมด"""
        if len(self.graph_x_data) == 0:
            QMessageBox.warning(
                self.view, "ไม่มีข้อมูลให้บันทึก",
                "ยังไม่มีผลลัพธ์การวัด กรุณากด START เพื่อวัดข้อมูลก่อน แล้วค่อย Save Result"
            )
            return

        from gui.dialogs.save_name_dialog import SaveNameDialog
        dialog = SaveNameDialog(self.view)
        if dialog.exec() != SaveNameDialog.DialogCode.Accepted:
            return

        save_name = dialog.get_name()
        if not save_name:
            return

        snapshot = self._build_save_snapshot()
        snapshot["meta"]["save_name"] = save_name

        try:
            path = save_manager.save_result(save_name, snapshot)
        except OSError as e:
            self.log.error(f"❌ บันทึก Save ล้มเหลว: {e}")
            QMessageBox.critical(self.view, "บันทึกล้มเหลว", f"ไม่สามารถบันทึกไฟล์ Save ได้:\n{e}")
            return

        self.log.info(f"💾 บันทึกผลลัพธ์ '{save_name}' เรียบร้อย ({path.name})")
        QMessageBox.information(self.view, "บันทึกสำเร็จ", f"บันทึกผลลัพธ์ \"{save_name}\" เรียบร้อยแล้ว")

    def handle_view_save_result(self):
        """เมื่อกดปุ่ม 'View Save Result' — เปิดหน้าต่างรายชื่อ Save ทั้งหมด"""
        from gui.dialogs.view_save_dialog import ViewSaveDialog
        dialog = ViewSaveDialog(self.view)
        dialog.open_save_requested.connect(self.open_save)
        dialog.exec()

    def open_save(self, path: str):
        """โหลด Input + ผลลัพธ์จากไฟล์ Save ที่เลือก กลับมาแสดงในโปรแกรมทั้งหมด"""
        if self.worker is not None:
            QMessageBox.warning(self.view, "กำลังวัดอยู่", "กรุณากด STOP เพื่อหยุดการวัดก่อน แล้วค่อยเปิด Save")
            return

        try:
            data = save_manager.load_save(path)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self.view, "เปิดไฟล์ล้มเหลว", f"ไม่สามารถเปิดไฟล์ Save นี้ได้:\n{e}")
            return

        reply = QMessageBox.question(
            self.view, "ยืนยันการเปิด Save",
            "การเปิด Save จะแทนที่ค่า Input และผลลัพธ์ปัจจุบันทั้งหมดในโปรแกรม\n"
            "ต้องการดำเนินการต่อหรือไม่?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        v = self.view
        meta = data.get("meta", {})
        inputs = data.get("inputs", {})
        results = data.get("results", {})
        run_mode = inputs.get("run_mode", "SINGLE")

        # --- คืนค่า Input ทั้งหมด ---
        if inputs.get("prop_group"):
            v.input_panel.combo_prop_group.setCurrentText(inputs["prop_group"])  # จะ trigger update_scpi_modes เอง
        self._set_combo_by_data(v.input_panel.combo_scpi_mode, inputs.get("scpi_mode"))
        self._set_combo_by_data(v.input_panel.combo_run_mode, run_mode)  # trigger toggle_run_mode เอง

        v.input_panel.input_freq.setValue(inputs.get("freq", v.input_panel.input_freq.value()))
        v.input_panel.input_n_single.setValue(inputs.get("n_single", v.input_panel.input_n_single.value()))
        v.input_panel.input_discard_single.setValue(inputs.get("discard_single", v.input_panel.input_discard_single.value()))
        v.input_panel.input_start_freq.setValue(inputs.get("start_freq", v.input_panel.input_start_freq.value()))
        v.input_panel.input_stop_freq.setValue(inputs.get("stop_freq", v.input_panel.input_stop_freq.value()))
        v.input_panel.input_step_freq.setValue(inputs.get("step_freq", v.input_panel.input_step_freq.value()))
        v.input_panel.input_samples_sweep.setValue(inputs.get("samples_sweep", v.input_panel.input_samples_sweep.value()))
        v.input_panel.input_discard_first_sweep.setValue(
            inputs.get("discard_first_sweep", v.input_panel.input_discard_first_sweep.value())
        )
        v.input_panel.input_freq_list.set_frequencies(inputs.get("freq_list", []))
        v.input_panel.input_samples.setValue(inputs.get("samples_list", v.input_panel.input_samples.value()))
        v.input_panel.input_discard_first.setValue(
            inputs.get("discard_first_list", v.input_panel.input_discard_first.value())
        )
        v.input_panel.input_volt.setValue(inputs.get("volt", v.input_panel.input_volt.value()))
        self._set_combo_by_data(v.input_panel.combo_level_mode, inputs.get("level_mode"))
        v.input_panel.chk_alc.setChecked(inputs.get("alc_enabled", False))
        if inputs.get("time_mode"):
            v.input_panel.combo_time.setCurrentText(inputs["time_mode"])
        v.input_panel.input_avg.setValue(inputs.get("avg", v.input_panel.input_avg.value()))
        if inputs.get("cable"):
            v.input_panel.combo_cable.setCurrentText(inputs["cable"])
        self._set_combo_by_data(v.input_panel.combo_range, inputs.get("imp_range"))

        v.adv_panel.chk_dev_ppm_enable.setChecked(inputs.get("ppm_enabled", False))
        v.adv_panel.input_dev_pri.setText(inputs.get("ppm_pri_ref") or "")
        v.adv_panel.input_dev_sec.setText(inputs.get("ppm_sec_ref") or "")

        visa_saved = inputs.get("visa_resource")
        if visa_saved:
            idx = v.conn_panel.combo_visa.findText(visa_saved)
            if idx >= 0:
                v.conn_panel.combo_visa.setCurrentIndex(idx)

        # --- คืนค่าผลลัพธ์ (กราฟ/ตารางสถิติ/ข้อมูลดิบ) ---
        self.graph_x_data = list(results.get("graph_x_data", []))
        self.graph_pri_y = list(results.get("graph_pri_y", []))
        self.graph_sec_y = list(results.get("graph_sec_y", []))
        self.graph_raw_pri_y = list(results.get("graph_raw_pri_y", []))
        self.graph_raw_sec_y = list(results.get("graph_raw_sec_y", []))

        self.setup_graph_labels()
        is_list_or_sweep = run_mode in ("LIST", "SWEEP")
        plot_x = list(range(1, len(self.graph_x_data) + 1)) if is_list_or_sweep else self.graph_x_data
        v.graph_display.clear_plots()
        v.graph_display.update_plots(plot_x, self.graph_pri_y, self.graph_sec_y)

        v.raw_table.set_mode(run_mode)
        v.raw_table.update_headers(inputs.get("scpi_mode"))
        v.raw_table.clear_table()
        for row in results.get("raw_table_rows", []):
            v.raw_table.append_row(row)

        self.update_statistics_table()
        self.update_session_lock()

        self.last_measurement_time = meta.get("measurement_time")
        self.last_measurement_time_iso = meta.get("measurement_time_iso")

        self.log.info(f"📂 เปิดผลลัพธ์ที่บันทึกไว้: \"{meta.get('save_name', '-')}\" ({meta.get('measurement_time', '-')})")

    @staticmethod
    def _set_combo_by_data(combo, value):
        """หา index ของ QComboBox ที่ userData ตรงกับ value ที่ระบุ แล้วเลือก index นั้น
        (ใช้กับ combo ที่ผูก currentData ไว้ เช่น scpi_mode, run_mode, level_mode, imp_range)"""
        if value is None:
            return
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)