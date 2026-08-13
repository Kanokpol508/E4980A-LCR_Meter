# ตัวกลางรับ Event จาก GUI ไปสั่ง Hardware และส่งผลกลับมา GUI

import re
import time

from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt, QObject

from core.measurement_thread import MeasurementWorker
from core.correction_thread import CorrectionWorker
from hardware.lcr_meter import E4980A
from data.data_processor import calculate_frequency_stats
from utils.helpers import truncate_sci
from core import save_manager

class AppController(QObject):
    def __init__(self, view):
        super().__init__()
        self.view = view

        # ตัวแปรสถานะ
        self.is_ppm_error = False               # ป้องกัน AttributeError: เปิด PPM แต่ไม่กรอก Ref
        self.is_visa_error = True
        self.is_freqlist_error = False          # ป้องกัน AttributeError
        self.is_correction_error = True         # [NEW] บังคับให้ทำ OPEN + SHORT Correction ก่อนกด START ได้
        self._stopped_by_user = False           # [NEW] แยกกรณีวัดจบเองกับผู้ใช้กด Stop เอง (กันป๊อปอัพเด้งตอนกด Stop)

        self.worker = None
        self.corr_worker = None
        self.verify_worker = None
        self.progress_dialog = None
        self.current_corr_type = None

        # [NEW] Instance เดียวที่ถือ Connection ค้างไว้ตลอด session (ใช้ร่วมกับปุ่ม Connect/Disconnect)
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

        # [NEW] โหมด SINGLE: แต่ละครั้งที่กด Start = 1 "รอบ" (run) แยกกัน
        # self.single_runs = [[(pri, sec), ...], [(pri, sec), ...], ...] — แต่ละ sub-list
        # คือค่าดิบของรอบนั้นๆ ใช้แยกคำนวณสถิติทีละรอบใน Statistics Table (ไม่ปนกัน
        # แม้จะวัดที่ความถี่เดียวกัน) ส่วน Raw Data Table/กราฟยังคง "ต่อข้อมูล" กันทุกรอบ
        self.single_runs = []
        # [NEW] ตัวนับ Samples ของ "รอบปัจจุบัน" เท่านั้น (รีเซ็ตทุกครั้งที่กด Start ใหม่ในโหมด SINGLE)
        # แยกจาก no_val (ตัวนับสะสมทั้ง session ใช้กับคอลัมน์ No.) เพื่อไม่ให้เลข Samples
        # เพี้ยนเป็น 6/5, 7/5 ตอนกดวัดซ้ำรอบสอง
        self._single_run_sample_no = 0

        # [NEW] เวลาที่วัดเสร็จล่าสุด (ใช้เป็นเวลา Save จริงๆ ไม่ใช่เวลาที่กดปุ่ม Save)
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
        v.conn_panel.btn_refresh.clicked.connect(self.scan_visa_ports)
        v.conn_panel.combo_visa.currentTextChanged.connect(self.validate_visa)

        # [NEW] ปุ่ม Connect / Disconnect
        v.conn_panel.btn_connect.clicked.connect(self.handle_connect)
        v.conn_panel.btn_disconnect.clicked.connect(self.handle_disconnect)

        # [NEW] ผูกสัญญาณเมื่อผู้ใช้เปลี่ยนหน่วยจาก V เป็น A ให้ไปปรับเพดานตัวเลขทันที
        v.input_panel.combo_level_mode.currentIndexChanged.connect(self.update_hardware_limits)

        # [NEW] ผูกสัญญาณความถี่ทุกโหมด (SINGLE/SWEEP/LIST) + เปลี่ยนโหมดการรัน
        # ให้ไปเช็คเงื่อนไข Voltage max 15V/20V ใหม่ทุกครั้งที่ความถี่หรือโหมดเปลี่ยน
        # (ตามคู่มือ Table 3-12: Freq > 1 MHz จำกัด Voltage ไว้ที่ 15 Vrms)
        v.input_panel.combo_run_mode.currentIndexChanged.connect(self.update_hardware_limits)
        v.input_panel.input_freq.valueChanged.connect(self.update_hardware_limits)
        v.input_panel.input_stop_freq.valueChanged.connect(self.update_hardware_limits)
        v.input_panel.input_freq_list.freq_changed.connect(self.update_hardware_limits)

        # [NEW] เช็คเงื่อนไข Range 100mΩ ทุกครั้งที่ผู้ใช้เปลี่ยน Range เอง หรือพิมพ์ค่า Signal Level เอง
        # (แยกจาก update_hardware_limits เพื่อไม่ให้ setRange() ข้างในนั้น trigger ตัวเองซ้ำวนลูป)
        v.input_panel.combo_range.currentIndexChanged.connect(self.check_range_signal_level_conflict)
        v.input_panel.input_volt.valueChanged.connect(self.check_range_signal_level_conflict)

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

        # [NEW] ระบบ Save / View Save Result — ใช้ปุ่มเดิมที่อยู่ข้าง Measurement Result (lcd_display)
        v.lcd_display.btn_save.clicked.connect(self.handle_save_result)
        v.lcd_display.btn_view.clicked.connect(self.handle_view_save_result)
        v.lcd_display.btn_export_excel.clicked.connect(self.handle_export_excel)

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

        # รีเซ็ตสถานะปุ่ม Correction เมื่อเปลี่ยน "Cable Length" เท่านั้น
        # เหตุผล (อ้างอิงคู่มือ E4980A หน้า 116): OPEN/SHORT Correction แบบ "all frequency
        # points" ที่โปรแกรมนี้ใช้ (:CORR:OPEN:EXEC / :CORR:SHOR:EXEC) จะวัดค่าที่ 51 จุด
        # ความถี่คงที่เสมอ "regardless of the test frequency settings" และค่าที่ชดเชยคือ
        # stray admittance ในช่วงจาก "calibration plane" ซึ่งถูกกำหนดโดย Cable Length
        # ไปถึงจุดต่อ DUT (หน้า 115) — คือปัจจัยเดียวที่มีเอกสารระบุชัดว่ากระทบ correction
        # data ของโหมดนี้โดยตรง จึงเหลือ trigger รีเซ็ตไว้แค่ตัวเดียวคือ combo_cable
        #
        # ส่วน Meas Mode (SCPI mode) และ Signal Level ไม่รีเซ็ตอีกต่อไป เพราะ:
        # - Meas Mode (CPD/ZTD/...): เป็นแค่การแปลงค่า R-X ที่วัดได้ไปแสดงเป็นพารามิเตอร์
        #   ต่างกัน ไม่ได้เปลี่ยนตัว correction data ที่เก็บไว้ในเครื่อง
        # - Signal Level: คู่มือหน้า 117 มีคำเตือนทั่วไปว่า "settings of frequency/level
        #   is changed" อาจทำให้ correction ไม่ valid แต่คำเตือนนี้ครอบคลุมโหมด SPOT
        #   correction (วัดที่จุดเดียวตามความถี่/level ปัจจุบัน) เป็นหลัก ไม่ใช่โหมด
        #   "all frequency points" ที่โปรแกรมนี้ใช้ซึ่งสวีปคงที่ 51 จุดเสมอ
        v.input_panel.combo_cable.currentIndexChanged.connect(self._reset_correction_status)

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
        v.input_panel.lbl_calculated_points.setText(f"{n_points} Points")

    def update_single_total(self):
        """คำนวณและแสดงรวมรอบวัดทั้งหมดของโหมด SINGLE
        รวมรอบ = Discard First + Readings Count
        (จำนวนครั้งที่เครื่องจะวัดจริงทั้งหมดต่อ 1 ครั้งที่กด Start)"""
        v = self.view
        n = v.input_panel.input_n_single.value()
        d = v.input_panel.input_discard_single.value()
        total = n + d
        v.input_panel.lbl_total_rounds_single.setText(f"{total} Times (Discard {d} + Measure {n})")

    def update_list_total(self):
        """คำนวณและแสดงรวมรอบวัดทั้งหมดต่อความถี่ของโหมด LIST
        รวมรอบ/ความถี่ = Discard First + Samples per Sweep
        (จำนวนครั้งที่เครื่องวัดต่อ 1 ความถี่ ก่อนขยับไปความถี่ถัดไป)"""
        v = self.view
        s = v.input_panel.input_samples.value()
        d = v.input_panel.input_discard_first.value()
        total = s + d
        v.input_panel.lbl_total_rounds_list.setText(f"{total} Times/Frequency \n (Discard {d} + Measure {s})")

    def update_sweep_total(self):
        """คำนวณและแสดงรวมรอบวัดทั้งหมดต่อความถี่ของโหมด SWEEP
        รวมรอบ/ความถี่ = Discard First + Samples per Sweep
        (เหมือน LIST — ใช้ widget แยกกันเพราะ SWEEP กับ LIST แสดงพร้อมกันไม่ได้อยู่แล้ว)"""
        v = self.view
        s = v.input_panel.input_samples_sweep.value()
        d = v.input_panel.input_discard_first_sweep.value()
        total = s + d
        v.input_panel.lbl_total_rounds_sweep.setText(f"{total} Times/Frequency \n (Discard {d} + Measure {s})")

    def get_max_test_frequency(self) -> float:
        """คืนค่าความถี่สูงสุดที่ 'มีผลจริง' กับการวัดในโหมดปัจจุบัน (Hz)
        ใช้เช็คเงื่อนไข Voltage max 15V/20V ตามคู่มือ (Table 3-12 footnote 1: > 1 MHz -> 15 Vrms)
        - SINGLE: ใช้ความถี่จุดเดียวที่กรอก
        - SWEEP : ใช้ Stop Frequency (ค่าสูงสุดของช่วงสแกน)
        - LIST  : ใช้ค่าสูงสุดในรายการความถี่ทั้งหมด (ถ้ายังไม่กรอกเลย ใช้ 0)
        """
        v = self.view
        run_mode = v.input_panel.combo_run_mode.currentData()
        if run_mode == "SWEEP":
            return v.input_panel.input_stop_freq.value()
        elif run_mode == "LIST":
            freqs = v.input_panel.input_freq_list.get_frequencies()
            return max(freqs) if freqs else 0.0
        else:  # SINGLE
            return v.input_panel.input_freq.value()

    def update_hardware_limits(self):
        """อัปเดตเพดาน Min/Max ของกล่องกรอกระดับสัญญาณ ตามโหมด V/I และความถี่ที่ผู้ใช้ตั้งไว้
        อ้างอิงคู่มือ E4980A/AL User Guide (Option 001 - Power/DC Bias Enhance):
        - Table 3-12 (Voltage): 0.1 mVrms - 20 Vrms, แต่ถ้า Test Frequency > 1 MHz จะตั้งได้สูงสุดแค่ 15 Vrms
        - Table 3-13 (Current): 50 uArms - 100 mArms
        """
        v = self.view
        level_mode = v.input_panel.combo_level_mode.currentData()

        if level_mode == "Voltage":
            VOLT_MIN = 0.0001   # 0.1 mVrms (หน้า 2 Overview + Table 3-12)
            max_freq = self.get_max_test_frequency()
            if max_freq > 1_000_000.0:
                volt_max = 15.0
                tip = "โหมดแรงดัน: ความถี่ตั้งไว้เกิน 1 MHz จ่ายสัญญาณได้สูงสุด 15 V (Option 001, ตามคู่มือ Table 3-12)"
            else:
                volt_max = 20.0
                tip = "โหมดแรงดัน: จ่ายสัญญาณได้ 0.1 mV - 20 V (Option 001, ตามคู่มือ Table 3-12)"

            # ต้องตั้ง Decimals ก่อน setRange เสมอ ไม่งั้น Qt จะปัดค่า Min/Max ตามจำนวนทศนิยมเดิมก่อนหน้า
            # (Voltage ละเอียดสุด 100uVrms/1mVrms ตาม Table 3-12 -> 4 ตำแหน่งพอ)
            v.input_panel.input_volt.setDecimals(4)
            v.input_panel.input_volt.setRange(VOLT_MIN, volt_max)
            v.input_panel.input_volt.setToolTip(tip)

            # ถ้าค่าที่กรอกไว้เดิมเกินเพดานใหม่ (เช่น ลดความถี่จาก 15V กลับมาแล้วเกิน 15V) ให้ปัดลงอัตโนมัติ
            if v.input_panel.input_volt.value() > volt_max:
                v.input_panel.input_volt.setValue(volt_max)

        else:  # โหมด Current (A)
            CURR_MIN = 0.00005  # 50 uArms (หน้า 2 Overview)
            CURR_MAX = 0.1      # 100 mArms (Table 3-13 แถวสุดท้าย + ตรงกับ SCPI :CURRent:LEVel Range "0 to 100m")

            # BUGFIX: ต้องตั้ง Decimals เป็น 5 ตำแหน่งก่อน setRange เสมอ
            # เดิมใช้ decimals=4 ทำให้ Qt ปัด Min 0.00005 (50uA) ขึ้นเป็น 0.0001 (100uA) โดยไม่รู้ตัว
            # ทำให้ผู้ใช้กรอกค่าช่วง 50-99 uA ไม่ได้เลยทั้งที่เครื่องรองรับ (Table 3-13)
            v.input_panel.input_volt.setDecimals(5)
            v.input_panel.input_volt.setRange(CURR_MIN, CURR_MAX)
            v.input_panel.input_volt.setToolTip(
                "โหมดกระแส: จ่ายสัญญาณได้ 50 uA - 100 mA (Option 001, ตามคู่มือ Table 3-13)"
            )

            # ป้องกันกรณีผู้ใช้กรอกค่าฝั่ง Voltage ทิ้งไว้ (เช่น 1.0) พอสลับเป็น A ค่าจะเกินสเปค
            # ให้ปัดตัวเลขลงมาที่เพดานใหม่โดยอัตโนมัติ
            if v.input_panel.input_volt.value() > CURR_MAX:
                v.input_panel.input_volt.setValue(CURR_MAX)
            elif v.input_panel.input_volt.value() < CURR_MIN:
                v.input_panel.input_volt.setValue(CURR_MIN)

        # ตรวจสอบเงื่อนไข Range 0.1Ω ทุกครั้งที่ Level/Frequency เปลี่ยน เพราะเงื่อนไขนี้อิง Signal Level
        self.check_range_signal_level_conflict()

    def check_range_signal_level_conflict(self):
        """เช็คเงื่อนไข Range 0.1Ω ตามคู่มือหน้า 51 (footnote 1 ของ Available impedance range)
        และ Figure 3-4/3-5/3-6 (Effective measurement range) ซึ่งระบุเกณฑ์คู่กันเสมอว่า
        "Test signal level > 2 V or 0.02 A" กล่าวคือ 0.02 A คือค่าเทียบเท่าของ 2V ในโหมดกระแส
        ถ้าผู้ใช้เลือก Range = 0.1Ω พร้อมกับตั้ง Signal Level <= 2V (โหมด Voltage) หรือ <= 0.02 A
        (โหมด Current) ให้เตือนและดีดกลับเป็น AUTO เพื่อกันไม่ให้ส่ง SCPI ที่ขัดแย้งกันไปเครื่อง
        """
        v = self.view
        range_val = v.input_panel.combo_range.currentData()
        if range_val != 0.1:
            return  # ไม่ได้เลือก 0.1Ω ไม่ต้องเช็ค

        level_mode = v.input_panel.combo_level_mode.currentData()
        level_value = v.input_panel.input_volt.value()

        # โหมด Voltage: เกณฑ์ตรงตามคู่มือคือ <= 2 V
        # โหมด Current: เกณฑ์เทียบเท่าคือ <= 0.02 A ตามที่คู่มือระบุคู่กันเสมอในทุก figure
        is_conflict = (
            (level_mode == "Voltage" and level_value <= 2.0)
            or (level_mode == "Current" and level_value <= 0.02)
        )

        if is_conflict:
            unit = "V" if level_mode == "Voltage" else "A"
            threshold = "2 V" if level_mode == "Voltage" else "0.02 A"
            QMessageBox.warning(
                v,
                "Range ไม่ถูกต้อง",
                f"ไม่สามารถใช้ Range 0.1 Ω ได้ เมื่อ Test Signal Level <= {threshold}\n"
                "ระบบจะเปลี่ยน Range กลับเป็น AUTO ให้อัตโนมัติ"
            )
            self._set_combo_by_data(v.input_panel.combo_range, "AUTO")

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
            green_style = "background-color: #A8E6C1; color: #14532D; border: 1px solid #7FD9A0;"
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
        self.check_correction_status()  # [NEW] อัปเดตสถานะปุ่ม START ทุกครั้งที่ Correction เสร็จ (สำเร็จหรือล้มเหลว)

    def _reset_correction_status(self):
        """
        รีเซ็ตปุ่ม OPEN/SHORT Correction กลับสู่สถานะเริ่มต้น (สีเทา / ไม่มี OK)
        เรียกอัตโนมัติเมื่อผู้ใช้เปลี่ยน "Cable Length" เท่านั้น (ดูเหตุผลเต็มๆ ที่จุด
        connect สัญญาณใน _connect_signals ด้านบน) — Meas Mode และ Signal Level
        ไม่ทำให้ Correction data ที่ทำไว้ไม่ valid อีกต่อไปแล้ว จึงไม่ trigger reset นี้

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

        self.check_correction_status()  # [NEW] อัปเดตสถานะปุ่ม START ทันทีที่ Correction ถูก invalidate

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
        if self.is_ppm_error or self.is_visa_error or self.is_freqlist_error or self.is_correction_error:
            self.log.warning("⚠️ ไม่สามารถเริ่มวัดได้ — ยังมีข้อผิดพลาดค้างอยู่ กรุณาตรวจสอบและแก้ไขก่อน")
            return

        v = self.view
        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        # True เฉพาะรอบแรกของ session ใหม่ (ยังไม่มีข้อมูลค้างอยู่เลย) — ใช้แยกจาก
        # รอบต่อเนื่อง (accumulate) ที่กด Start ซ้ำในโหมด SINGLE ขณะมีข้อมูลเก่าอยู่แล้ว
        is_first_single_session = is_single and len(self.graph_x_data) == 0
        self._stopped_by_user = False  # [NEW] เริ่มวัดใหม่ทุกครั้ง ถือว่ายังไม่ได้ถูกกด Stop

        # [แก้ไข] เตรียมตาราง Raw Data ก่อนเริ่มวัด
        # เดิม: เรียก set_mode() (ซึ่งข้างในมี clear_table() ซ่อนอยู่) ทุกครั้งที่กด Start
        # ทำให้โหมด SINGLE ที่ตั้งใจ "ต่อข้อมูล" รอบใหม่ ถูกล้างตารางทิ้งไปด้วยทุกรอบ
        # ตอนนี้เรียก set_mode() (ซึ่งจะ clear ตาราง) เฉพาะตอนเปลี่ยนโหมดจริง หรือเป็น
        # SINGLE รอบแรกของ session ใหม่เท่านั้น — ถ้าเป็น SINGLE รอบต่อเนื่อง จะข้าม
        # การ clear ไปเลย (อัปเดตแค่ชื่อคอลัมน์ Primary/Secondary เผื่อ SCPI mode เปลี่ยน)
        if not is_single or is_first_single_session:
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

        if is_single:
            # [NEW] 1 ครั้งกด Start ในโหมด SINGLE = 1 "รอบ" (run) ใหม่เสมอ — ใช้แยกคำนวณ
            # สถิติทีละรอบใน Statistics Table (ไม่ปนกันแม้ freq จะเท่าเดิมทุกรอบ)
            if is_first_single_session:
                self.single_runs = []
            self.single_runs.append([])

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
            'is_first_single_session': is_first_single_session,
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
        level_unit = "A" if settings.get('level_mode') == 'Current' else "V"
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
            self._stopped_by_user = True  # [NEW] กันป๊อปอัพ "วัดเสร็จสมบูรณ์" เด้งตอนผู้ใช้ตั้งใจกด Stop เอง
            self.worker.stop()
            self.view.ctrl_panel.btn_stop.setText("STOPPING...")
            self.view.ctrl_panel.btn_stop.setEnabled(False)
            self.log.warning("⏹ ผู้ใช้กด STOP — กำลังหยุดการวัด...")
            run_mode = self.get_current_run_mode()
            if run_mode in ("LIST", "SWEEP"):
                self.view.freq_summary_graph.set_progress("Stopped")
                self.view.ppm_summary_graph.set_progress("Stopped")
                self.view.graph_display.set_progress("Stopped")

    # ========================================================
    # การคำนวณและแสดงผลข้อมูล (Data Handling & Math)
    # ========================================================
    def handle_data_ready(self, data):
        v = self.view

        # 1. ค่าดิบจากฮาร์ดแวร์
        raw_pri = data.get('primary', 0.0)
        raw_sec = data.get('secondary', 0.0)
        status  = data.get('status', 'SUCCESS')  # [NEW] รับค่า status ที่มาจาก Thread

        # เก็บค่าดิบลง Array ไว้คำนวณ Type A Uncertainty
        self.graph_raw_pri_y.append(raw_pri)
        self.graph_raw_sec_y.append(raw_sec)

        # กราฟและ LCD แสดงค่าดิบเสมอ (ไม่มี Graph Deviation แล้ว)
        # [แก้ไข] เดิม f"{raw_pri:.5e}" ปัดเศษ (round) เหลือ 5 ตำแหน่ง เปลี่ยนเป็น
        # truncate_sci() ตัดทิ้ง ไม่ปัดเศษ 9 ตำแหน่ง ให้หลักการเดียวกับ Raw Data Table
        v.lcd_display.lbl_pri_val.setText(truncate_sci(raw_pri, 9))
        v.lcd_display.lbl_sec_val.setText(truncate_sci(raw_sec, 9))

        run_mode = self.get_current_run_mode()
        is_single = (run_mode == "SINGLE")
        is_list = (run_mode == "LIST")
        is_sweep = (run_mode == "SWEEP")

        # --- [NEW] ลอจิกเตรียมข้อมูลให้ Raw Data Table ---
        no_val = len(self.graph_x_data) + 1  # ลำดับที่ของการวัด (1, 2, 3... สะสมทั้ง session)
        # [แก้ไข] current_freq มาจาก data['freq'] ซึ่งเป็นค่าความถี่ "ที่ใช้วัดจริง" ของรอบนี้
        # (worker ส่งมาจาก settings snapshot ตอนกด Start ไม่ใช่อ่าน UI สดๆ) — ใช้ค่านี้เป็น
        # หลักเสมอ แทนที่จะอ่าน v.input_panel.input_freq.value() ซ้ำ เพราะตอนนี้ input_freq
        # ปลดล็อกแล้ว ผู้ใช้อาจเปลี่ยนความถี่ระหว่างรอบได้ ถ้าอ่าน UI สดจะได้ค่าใหม่ผิดรอบ
        current_freq = data.get('freq', 0)

        # [NEW] เก็บค่าดิบ + ความถี่ที่ใช้จริงของรอบนี้ลงรอบปัจจุบัน (self.single_runs[-1])
        # ด้วย — ใช้แยกคำนวณสถิติทีละรอบใน Statistics Table โดยแต่ละรอบจะจำความถี่ของตัวเอง
        # ไว้ตรงตัว ไม่ต้องพึ่งค่า input_freq ปัจจุบันตอนคำนวณ (start_measurement() การันตี
        # ว่ามี sub-list พร้อมรออยู่แล้ว)
        if is_single and self.single_runs:
            self.single_runs[-1].append((raw_pri, raw_sec, current_freq))

        # จัดรูปแบบข้อความ "Samples (N)" ให้ตรงกับโหมด
        if is_single:
            n_single = v.input_panel.input_n_single.value()
            # [แก้ไข] เดิมใช้ no_val (เลขสะสมทั้ง session) หารกับ n_single ของรอบล่าสุด
            # ทำให้กด Start ซ้ำรอบ 2 แล้วเห็นเลขเพี้ยนเป็น 6/5, 7/5, 8/5 แทนที่จะเป็น 1/5, 2/5...
            # ตอนนี้ใช้ลำดับ "ภายในรอบปัจจุบัน" (len ของ self.single_runs[-1] หลัง append ไปแล้ว)
            run_no = len(self.single_runs[-1]) if self.single_runs else no_val
            sample_text = f"{run_no}/{n_single}"  # ตัวอย่าง: 1/5, 2/5 (รีเซ็ตใหม่ทุกครั้งที่กด Start)
            freq_val = current_freq  # [แก้ไข] ใช้ความถี่จริงของรอบนี้ ไม่ใช่ UI สดที่อาจเปลี่ยนไปแล้ว
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

        # --- [NEW] อัปเดต Progress / Current Reading ใต้กราฟสรุปตามความถี่ & กราฟ PPM ---
        # มีความหมายเฉพาะโหมด LIST/SWEEP (ที่วัดหลายความถี่ วนซ้ำหลายรอบต่อความถี่)
        if is_list or is_sweep:
            freq_display = self._format_freq_display(current_freq)
            progress_text = f"Sample {sample_text} | Freq: {freq_display}"

            # โชว์เฉพาะพารามิเตอร์ที่ผู้ใช้ติ๊กเปิดไว้บนกราฟ (Plot Primary/Secondary)
            # ให้ตรงกับสิ่งที่กำลังแสดงอยู่จริง — ไม่ใช่โชว์ครบทั้งคู่ตายตัว
            parts = []
            if v.freq_summary_graph.is_plot_primary_enabled():
                pri_name = self._format_param_display(v.freq_summary_graph.pri_name)
                parts.append(f"{pri_name}: {truncate_sci(raw_pri, 9)}")
            if v.freq_summary_graph.is_plot_secondary_enabled():
                sec_name = self._format_param_display(v.freq_summary_graph.sec_name)
                parts.append(f"{sec_name}: {truncate_sci(raw_sec, 9)}")

            if parts:
                reading_text = ", ".join(parts) + f" | Freq: {freq_display}"
            else:
                reading_text = f"(Plot Primary/Secondary ปิดอยู่ทั้งคู่) | Freq: {freq_display}"

            v.freq_summary_graph.set_progress(progress_text)
            v.freq_summary_graph.set_current_reading(reading_text)
            v.ppm_summary_graph.set_progress(progress_text)
            v.ppm_summary_graph.set_current_reading(reading_text)
            v.graph_display.set_progress(progress_text)
            v.graph_display.set_current_reading(reading_text)

    @staticmethod
    def _format_param_display(label: str) -> str:
        """แปลงชื่อพารามิเตอร์รูปแบบเต็ม 'Capacitance, Cp (F)' (ใช้กับแกนกราฟ/legend)
        ให้เป็นรูปแบบสั้น อ่านง่ายขึ้นสำหรับ Current Reading: 'Capacitance (Cp)'
        (ไม่แก้ pri_name/sec_name ต้นทาง เพราะที่อื่นในโปรแกรมยังใช้รูปแบบเดิมอยู่)"""
        text = label
        m = re.match(r"^(.*?)\s*\([^()]+\)\s*$", text)
        if m:
            text = m.group(1).strip()  # ตัดหน่วยท้ายวงเล็บออกก่อน เช่น '(F)', '(Ω)'
        if ',' in text:
            name, abbr = text.split(',', 1)
            return f"{name.strip()} ({abbr.strip()})"
        return text

    @staticmethod
    def _format_freq_display(freq: float) -> str:
        """แปลงความถี่ (Hz) ดิบให้อ่านง่าย เช่น 1000 -> '1 kHz', 1500000 -> '1.5 MHz'"""
        try:
            freq = float(freq)
        except (TypeError, ValueError):
            return str(freq)
        if freq >= 1e6:
            return f"{freq / 1e6:g} MHz"
        elif freq >= 1e3:
            return f"{freq / 1e3:g} kHz"
        else:
            return f"{freq:g} Hz"

    def update_statistics_table(self):
        """สร้าง raw_records จากข้อมูลที่เก็บไว้ แล้วส่งให้ StatisticsTable คำนวณ/แสดงผลใหม่
        รองรับทุกโหมด: SINGLE (แยกสถิติทีละรอบ/1 Start = 1 แถว) / SWEEP (per-freq raw) / LIST (per-freq stats)"""
        v = self.view
        run_mode = self.get_current_run_mode()

        if run_mode == "SINGLE":
            # [แก้ไข] เดิมดึง fixed_freq = v.input_panel.input_freq.value() ค่าเดียวมาแปะให้
            # ทุกรอบเท่ากันหมด ใช้ได้ตอน input_freq ยังถูกล็อกอยู่เท่านั้น — ตอนนี้ input_freq
            # ปลดล็อกแล้ว (ผู้ใช้เปลี่ยนความถี่วัดชิ้นงานเดิมระหว่าง session ได้) จึงต้องใช้
            # ความถี่ที่ถูก "stamp" ไว้กับข้อมูลดิบของแต่ละรอบเองแทน (self.single_runs เก็บเป็น
            # (pri, sec, freq) ต่อ sample — freq มาจาก settings snapshot ตอนกด Start ของรอบนั้น
            # ไม่ใช่อ่าน UI สด) แต่ละรอบจึงคงความถี่ที่วัดจริงไว้ถูกต้องแม้จะเปลี่ยน UI ไปแล้วก็ตาม
            #
            # [แก้ไข] ส่งเป็น "กลุ่มต่อรอบ" (list ของ list) แทนที่จะรวมทุกรอบเป็น flat list เดียว
            # เพื่อให้ Statistics Table คำนวณสถิติแยกทีละรอบ (1 ครั้งกด Start = 1 แถว) ไม่ปนกัน
            # แม้ freq จะเท่าเดิมทุกรอบก็ตาม (raw_data_table ยังคง "ต่อข้อมูล" ทุกแถวตามเดิม)
            raw_records = [
                [{'freq': f, 'primary': p, 'secondary': s} for p, s, f in run]
                for run in self.single_runs
            ]
        else:
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

    def _get_session_info_dict(self, measurement_time: str = None) -> dict:
        """[NEW] รวบรวมข้อมูล Session ปัจจุบัน (ค่าที่คงที่ตลอดการวัดครั้งนี้ ไม่เปลี่ยนต่อแถว)
        ใช้ 3 ที่: (1) แสดงใน Session Info Bar เหนือ Raw Data Table
        (2) บันทึกลง Save เพื่อโชว์ตอน Open Save (3) เตรียมไว้ให้ Export Excel ในอนาคต"""
        v = self.view

        level_mode = v.input_panel.combo_level_mode.currentData()
        unit = "A" if level_mode == "Current" else "V"
        volt = v.input_panel.input_volt.value()

        ppm_pri = v.adv_panel.input_dev_pri.text().strip()
        ppm_sec = v.adv_panel.input_dev_sec.text().strip()

        return {
            "mode": v.input_panel.combo_scpi_mode.currentText() or "-",
            "signal": f"{volt:g} {unit}",
            "measurement_time": measurement_time or "-",
            "meas_time": v.input_panel.combo_time.currentText() or "-",
            "avg": v.input_panel.input_avg.value(),
            "cable": v.input_panel.combo_cable.currentText(),
            "imp_range": v.input_panel.combo_range.currentText(),
            "ppm_pri_ref": ppm_pri if ppm_pri else "-",
            "ppm_sec_ref": ppm_sec if ppm_sec else "-",
        }

    def handle_worker_finished(self):
        self.log.info("✅ การวัดเสร็จสมบูรณ์")
        self.set_ui_locked(False)
        self.worker = None

        # [NEW] อัปเดต Progress ใต้กราฟสรุป/PPM ให้รู้ว่าวัดเสร็จแล้ว (เฉพาะถ้ามีการวัดจริง)
        run_mode = self.get_current_run_mode()
        if run_mode in ("LIST", "SWEEP"):
            self.view.freq_summary_graph.set_progress("Complete")
            self.view.ppm_summary_graph.set_progress("Complete")
            self.view.graph_display.set_progress("Complete")

        # [NEW] ป๊อปอัพแจ้งเตือนตอนวัดเสร็จ — เฉพาะกรณีวัดจบเองตามรอบจริงๆ เท่านั้น
        # ไม่เด้งตอนผู้ใช้ตั้งใจกด Stop เอง (กันความรำคาญ/สับสนว่า "จบ" ทั้งที่ตัวเองสั่งหยุด)
        if not self._stopped_by_user:
            QMessageBox.information(self.view, "วัดเสร็จสมบูรณ์", "การวัดเสร็จสมบูรณ์แล้ว ✅")
        self._stopped_by_user = False

        # [NEW] จำเวลาที่วัดเสร็จไว้ ณ ตอนนี้ — นี่คือเวลาที่จะใช้ตอน Save Result จริงๆ
        # (ไม่ใช่เวลาที่ผู้ใช้กดปุ่ม Save Result ซึ่งอาจกดทีหลังก็ได้)
        self.last_measurement_time_iso = time.strftime("%Y-%m-%d %H:%M:%S")
        self.last_measurement_time = time.strftime("%d/%m/%Y %H:%M:%S")

        # [NEW] อัปเดต Session Info Bar เหนือ Raw Data Table ด้วยค่าล่าสุดของ session นี้
        self.view.raw_table.update_session_info(self._get_session_info_dict(self.last_measurement_time))

    def clear_graph_data(self):
        self.graph_x_data = []
        self.graph_pri_y = []
        self.graph_sec_y = []
        self.graph_raw_pri_y = []
        self.graph_raw_sec_y = []
        self.single_runs = []  # [NEW] เคลียร์กลุ่มข้อมูลดิบแยกตามรอบด้วย
        self.view.graph_display.clear_plots()
        self.view.freq_summary_graph.clear()
        self.view.ppm_summary_graph.clear()
        self.view.stats_table.clear_table()
        self.view.raw_table.clear_table()  # [NEW] ล้างตารางข้อมูลดิบด้วย
        self.view.raw_table.clear_session_info()  # [NEW] รีเซ็ต Session Info Bar ด้วย
        self.log.info("🗑 ล้างข้อมูลกราฟและตารางสถิติเรียบร้อย")
        self.update_session_lock()

    # ข้อความ tooltip ที่ใส่ตอน field ถูกล็อกไว้ — บอกเหตุผล + วิธีปลดล็อกชัดเจน
    # กันผู้ใช้งงว่าทำไมกดแก้ค่าไม่ได้ (แค่ setEnabled(False) เฉยๆ ไม่บอกเหตุผลอะไรเลย)
    _LOCK_TOOLTIP = ("🔒 ค่านี้ถูกล็อกไว้ เพราะมีข้อมูลค้างอยู่ในโหมด SINGLE ที่กำลัง \"ต่อข้อมูล\" กันอยู่ "
                      "(เปลี่ยนค่านี้กลางคันจะทำให้ข้อมูลรอบเก่ากับรอบใหม่วัดภายใต้เงื่อนไขไม่เหมือนกัน)\n"
                      "กด Clear Graph ก่อน ถ้าต้องการแก้ไขค่านี้")

    def _set_locked(self, widget, should_lock: bool):
        """[NEW] setEnabled() + จัดการ tooltip ให้ในตัวเดียว — เก็บ tooltip เดิมไว้ใน
        property ของ widget เอง (ไม่ต้องมี dict แยกใน AppController) แล้วคืนค่ากลับตอนปลดล็อก"""
        if should_lock:
            if widget.property("_orig_tooltip") is None:
                widget.setProperty("_orig_tooltip", widget.toolTip())
            widget.setToolTip(self._LOCK_TOOLTIP)
        else:
            orig = widget.property("_orig_tooltip")
            if orig is not None:
                widget.setToolTip(orig)
        widget.setEnabled(not should_lock)

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

        # [NEW] ขยาย lock ให้ครอบคลุมทุกช่องที่มีผลต่อผลวัด/แสดงอยู่ใน Measurement Session
        # Info Bar (raw_data_table.py: SESSION_INFO_FIELDS) เดิมล็อกแค่ scpi_mode/run_mode/
        # freq-list ทำให้ยังแก้ signal level, avg, cable, range ระหว่างมีข้อมูลค้างอยู่ได้ —
        # พอกดวัดซ้ำ ค่าที่โชว์ใน Session Info Bar จะถูกเขียนทับด้วยค่าล่าสุดเงียบๆ ทำให้ข้อมูล
        # รอบเก่ากับ metadata ที่แสดงอยู่ไม่ตรงกันจริง (ดูรายละเอียดที่คุยกันไว้ก่อนหน้านี้)
        #
        # เพิ่ม input_freq (ความถี่คงที่ของโหมด SINGLE) เข้ามาด้วย แม้จะไม่ได้อยู่ใน
        # SESSION_INFO_FIELDS โดยตรง เพราะ update_statistics_table() ดึงค่านี้ "สด"
        # มาแปะให้ทุกรอบที่สะสมไว้เท่ากันหมดเสมอ (fixed_freq = input_freq.value()) ถ้าปล่อย
        # ให้เปลี่ยนได้ระหว่างมีข้อมูลค้าง รอบเก่าจะถูกเปลี่ยนป้ายความถี่ผิดตามไปด้วยทันที
        # [แก้ไข] ตามที่คุยกันไว้ — ปลดล็อก input_freq เพื่อให้ผู้ใช้เปลี่ยนความถี่วัดอุปกรณ์
        # ชิ้นเดิมได้ระหว่าง session (เช่น อยากดูค่าที่ 1kHz แล้ว 10kHz ของชิ้นงานเดียวกัน)
        # ทำได้ปลอดภัยเพราะตอนนี้แต่ละรอบ (self.single_runs[-1]) ถูก stamp ความถี่ที่ใช้จริง
        # ของรอบนั้นไว้กับข้อมูลดิบเลย (มาจาก settings snapshot ตอนกด Start ผ่าน worker ไม่ใช่
        # อ่านค่า UI ปัจจุบันสดๆ ตอนคำนวณสถิติ) รอบเก่าจึงไม่มีทางถูกเปลี่ยนป้ายความถี่ผิดอีก
        # แม้จะเปลี่ยน input_freq ก่อนกด Start รอบถัดไปก็ตาม — ดู update_statistics_table()
        for widget in (
            v.input_panel.input_volt,        # Signal Level (ตัวเลข)
            v.input_panel.combo_level_mode,  # Signal Level (V/A)
            v.input_panel.chk_alc,           # ALC
            v.input_panel.combo_time,        # Meas Time (Aperture: SHORT/MEDIUM/LONG)
            v.input_panel.input_avg,         # Averaging
            v.input_panel.combo_cable,       # Cable Length
            v.input_panel.combo_range,       # Range
        ):
            self._set_locked(widget, should_lock)

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

    def check_correction_status(self):
        """[NEW] เช็คว่าทำ OPEN Correction และ SHORT Correction ครบทั้งคู่หรือยัง
        ใช้ text บนปุ่มเป็นแหล่งข้อมูลจริง (single source of truth) เหมือนกับ
        _reset_correction_status() เพื่อไม่ให้ status สองที่ไม่ตรงกัน"""
        adv = self.view.adv_panel
        open_is_ok = adv.btn_open_corr.text() == "OPEN Correction (OK)"
        short_is_ok = adv.btn_short_corr.text() == "SHORT Correction (OK)"
        self.is_correction_error = not (open_is_ok and short_is_ok)
        self.update_start_button_state()

    def update_start_button_state(self):
        v = self.view
        is_blocked = (self.is_ppm_error or self.is_visa_error or self.is_freqlist_error
                      or self.is_correction_error)
        v.ctrl_panel.lbl_warn_visa.setVisible(self.is_visa_error)
        v.ctrl_panel.lbl_warn_dev_start.setVisible(self.is_ppm_error)
        v.ctrl_panel.lbl_warn_freqlist_start.setVisible(self.is_freqlist_error)
        # ไม่ต้องซ้ำเตือนถ้ายังต่อเครื่องไม่ได้ — โชว์เตือน Correction เฉพาะตอนต่อเครื่องแล้ว
        v.ctrl_panel.lbl_warn_correction_start.setVisible(
            self.is_correction_error and not self.is_visa_error
        )

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
        """เปิด/ปิด widget กรอก PPM Reference ตาม checkbox สถานะ
        [NEW] ล็อกทั้ง Tab "กราฟ PPM" ไปเลยเมื่อยังไม่เปิดใช้งาน PPM Deviation
        กันผู้ใช้กดเข้าไปเจอกราฟว่างเปล่าแล้วสับสนว่าทำไมไม่มีข้อมูล"""
        v = self.view
        is_enabled = v.adv_panel.chk_dev_ppm_enable.isChecked()
        v.adv_panel.widget_dev_inner.setEnabled(is_enabled)

        v.right_tabs.setTabEnabled(v.ppm_graph_tab_index, is_enabled)
        v.right_tabs.setTabToolTip(
            v.ppm_graph_tab_index,
            "" if is_enabled else
            "ต้องเปิด \"เปิดใช้งานการคำนวณ PPM Deviation\" ในแท็บ Advanced ก่อน จึงจะเข้าดูกราฟนี้ได้"
        )

        if is_enabled:
            self.validate_ppm_ref()
        else:
            v.adv_panel.lbl_dev_warning.setText("")
            self.is_ppm_error = False
            # [NEW] ปิด PPM ทั้งระบบ -> ล็อกตัวเลือก Plot Primary/Secondary ของกราฟ PPM ด้วย
            v.ppm_summary_graph.set_primary_option_enabled(False)
            v.ppm_summary_graph.set_secondary_option_enabled(False)
            self.update_start_button_state()

    def validate_ppm_ref(self):
        """
        ตรวจสอบว่ากรอก Primary Ref หรือ Secondary Ref อย่างน้อย 1 ค่าเมื่อเปิด PPM
        ถ้าเปิด PPM แล้วไม่กรอกค่าใดเลย จะบล็อกปุ่ม Start เพราะผล PPM Dev จะเป็น '-' ทั้งหมด

        [NEW] ล็อกตัวเลือก "Plot Primary"/"Plot Secondary" ใน Dropdown ของกราฟ PPM แยกตามว่า
        กรอก Ref ตัวนั้นไว้หรือยัง — แค่ disable เฉยๆ ไม่เปลี่ยนตัวเลือกที่กำลังเลือกอยู่ทิ้ง
        เพื่อรักษาสถานะที่ผู้ใช้ตั้งใจเลือกไว้แต่แรก พอกรอก Ref กลับมาใหม่ ตัวเลือกจะ enable
        กลับมาเหมือนเดิมทันที
        """
        v = self.view
        if not v.adv_panel.chk_dev_ppm_enable.isChecked():
            self.is_ppm_error = False
            v.ppm_summary_graph.set_primary_option_enabled(False)
            v.ppm_summary_graph.set_secondary_option_enabled(False)
            self.update_start_button_state()
            return

        pri_has_value = self._safe_float(v.adv_panel.input_dev_pri.text()) is not None
        sec_has_value = self._safe_float(v.adv_panel.input_dev_sec.text()) is not None

        v.ppm_summary_graph.set_primary_option_enabled(
            pri_has_value,
            "" if pri_has_value else "กรอก Primary Ref ในแท็บ Advanced ก่อน จึงจะเปิดดูเส้นนี้ได้"
        )
        v.ppm_summary_graph.set_secondary_option_enabled(
            sec_has_value,
            "" if sec_has_value else "กรอก Secondary Ref ในแท็บ Advanced ก่อน จึงจะเปิดดูเส้นนี้ได้"
        )

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
            # [NEW] ข้อมูล Session (ค่าคงที่ตลอดการวัดครั้งนี้) — เตรียมไว้ให้ Open Save
            # โชว์ใน Session Info Bar และให้ Export Excel ในอนาคตดึงไปใช้ได้ทันที
            "session_info": self._get_session_info_dict(measurement_time),
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
                # [NEW] เก็บกลุ่มข้อมูลดิบแยกตาม "รอบ" (1 ครั้งกด Start ในโหมด SINGLE = 1 รอบ)
                # ไว้ใช้คำนวณ Statistics Table แยกแถวต่อรอบ ตอน Open Save กลับมาดูทีหลัง
                "single_runs": self.single_runs,
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

    def handle_export_excel(self):
        """เมื่อกดปุ่ม 'Export Excel' — เปิดป๊อปอัพ 3 ขั้นตอน (เลือก Save -> Record details -> ตั้งค่าไฟล์)
        แล้ว export เป็นไฟล์ .xlsx ตามที่ผู้ใช้ตั้งค่าไว้"""
        from gui.dialogs.export_excel_dialog import ExportExcelDialog
        from data.file_exporter import export_measurements_to_excel

        default_run_mode = self.get_current_run_mode()
        dialog = ExportExcelDialog(self.view, default_run_mode=default_run_mode)
        if dialog.exec() != ExportExcelDialog.DialogCode.Accepted:
            return

        try:
            path = export_measurements_to_excel(
                save_paths=dialog.selected_saves,
                output_path=dialog.output_path,
                include_stats=dialog.include_stats,
                include_raw=dialog.include_raw,
                record_details=dialog.record_details,
            )
        except (OSError, ValueError, KeyError) as e:
            self.log.error(f"❌ Export Excel ล้มเหลว: {e}")
            QMessageBox.critical(self.view, "Export ล้มเหลว", f"ไม่สามารถ Export ไฟล์ Excel ได้:\n{e}")
            return

        self.log.info(f"📊 Export Excel สำเร็จ: {path}")
        QMessageBox.information(self.view, "Export สำเร็จ", f"Export ไฟล์ Excel เรียบร้อยแล้ว:\n{path}")

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
        # [NEW] คืนค่ากลุ่มข้อมูลดิบแยกตามรอบ (ใช้คำนวณ Statistics Table ต่อรอบใน SINGLE mode)
        # แต่ละ sample เก็บเป็น (pri, sec, freq) — freq ของรอบนั้นๆ โดยเฉพาะ (รองรับกรณี
        # เปลี่ยนความถี่ระหว่าง session ได้ตั้งแต่ input_freq ถูกปลดล็อก)
        # ไฟล์เก่าก่อนมีฟีเจอร์นี้จะไม่มี key "single_runs" เลย หรือมีแต่เป็น 2-tuple (pri, sec)
        # ไม่มี freq (เก็บตอนความถี่ยังล็อกคงที่ทั้ง session) -> เติม freq จากค่าที่ Save ไว้ใน
        # inputs["freq"] ให้ทุก sample เท่ากันหมด (พฤติกรรมเดิมตอนนั้นถูกอยู่แล้ว)
        saved_freq = inputs.get("freq", 0)
        raw_single_runs = results.get(
            "single_runs", [list(zip(self.graph_raw_pri_y, self.graph_raw_sec_y))]
        )
        self.single_runs = [
            [tuple(s) if len(s) == 3 else (s[0], s[1], saved_freq) for s in run]
            for run in raw_single_runs
        ]

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

        # [NEW] แสดง Session Info Bar ตามที่บันทึกไว้ในไฟล์ Save
        # (ถ้าเป็น Save เก่าก่อนมีฟีเจอร์นี้ จะไม่มี key "session_info" -> คำนวณสดจาก input ที่เพิ่ง restore แทน)
        session_info = data.get("session_info") or self._get_session_info_dict(self.last_measurement_time)
        v.raw_table.update_session_info(session_info)

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