# **สำคัญมาก** ทำงานเบื้องหลัง (QThread) เพื่อสแกน Sweep โดยไม่ให้ UI ค้าง

from PyQt6.QtCore import QThread, pyqtSignal
from hardware.lcr_meter import E4980A

class MeasurementWorker(QThread):
    """คลาสลูกน้องหลังบ้าน ทำหน้าที่สื่อสารกับฮาร์ดแวร์ (LCR Meter) ของจริง"""
    data_ready       = pyqtSignal(dict)     # ส่งข้อมูลผลการวัด
    error_occurred   = pyqtSignal(str)      # ส่งข้อความ Error
    progress_updated = pyqtSignal(int)      # ส่งเลขเปอร์เซ็นต์
    finished         = pyqtSignal()         # ส่งสัญญาณจบการทำงาน

    def __init__(self, lcr, settings: dict):
        super().__init__()
        self.lcr        = lcr          # [แก้ไข] instance ที่เชื่อมต่อไว้แล้วจากปุ่ม Connect (ไม่ปิดเองตอนจบ)
        self.settings   = settings
        self.is_running = True

    def run(self):
        """ลอจิกหลักที่ทำงานใน Thread เบื้องหลัง"""
        lcr = self.lcr
        try:
            if not lcr.is_connected:
                raise ConnectionError("ยังไม่ได้เชื่อมต่อเครื่องมือวัด — กรุณากด CONNECT ก่อนเริ่มวัด")

            # ========================================================
            # 2. ตั้งค่าเครื่องมือวัดก่อนเริ่มการวัด (Hardware Setup)
            # ========================================================
            scpi_mode = self.settings.get('scpi_mode', 'CPD')
            volt      = self.settings.get('volt', 1.0)
            freq      = self.settings.get('freq', 100000.0)
            time_mode = self.settings.get('time_mode', 'MED')
            avg       = self.settings.get('avg', 1)
            imp_range = self.settings.get('imp_range', 'AUTO')

            level_mode  = self.settings.get('level_mode', 'Voltage')
            alc_enabled = self.settings.get('alc_enabled', False)

            lcr.set_measurement_mode(scpi_mode)
            lcr.set_signal_level(volt, level_mode)
            lcr.set_alc(alc_enabled)
            lcr.set_frequency(freq)
            lcr.set_aperture(time_mode, avg)

            # ปรับ VISA timeout ให้เหมาะกับ time_mode + averaging + imp_range ที่ใช้จริง
            # ต้องเรียกหลัง set_aperture() เสมอ เพราะ timeout ขึ้นกับค่าเหล่านี้
            # ป้องกัน VisaIOError: Timeout เมื่อใช้ LONG aperture + avg จำนวนมาก
            # หรือเมื่อใช้ AUTO range ที่ auto-ranging ใช้เวลานานกว่า base aperture time มาก
            lcr.set_measurement_timeout(time_mode, avg, imp_range)

            # ต้องตั้งค่านี้ก่อนวัดเสมอ เพราะมีผลกับทุกการวัดทันที (ไม่เกี่ยวกับ OPEN/SHORT Correction)
            cable_text = self.settings.get('cable', '0 m')
            lcr.set_cable_length(cable_text)

            lcr.set_impedance_range(imp_range)

            # รอให้ค่าที่เซ็ตเข้าไปทั้งหมดประมวลผลเสร็จสิ้น
            lcr.wait_until_ready()

            # [NEW] อ่านค่า Signal Level "จริง" ที่เครื่องยืนยันว่ากำลังตั้งอยู่ (query กลับ
            # จากเครื่องจริงๆ) แทนที่จะใช้แค่ค่าที่ผู้ใช้กรอกใน UI เฉยๆ — เก็บลงใน
            # self.settings ซึ่งเป็น dict object เดียวกับ _active_run_settings ใน
            # app_controller.py (ส่งมาโดยอ้างอิง ไม่ใช่ copy) ทำให้ raw_table อ่านค่านี้ได้ทันที
            try:
                self.settings['actual_volt'] = lcr.get_signal_level(level_mode)
            except Exception:
                # query ไม่สำเร็จ (เช่น เครื่องรุ่นนี้ไม่รองรับคำสั่งนี้) — ไม่ทำให้การวัดล้มเหลว
                # ไปด้วย ปล่อยให้ app_controller.py fallback ไปใช้ค่าที่ตั้งไว้แทน
                self.settings['actual_volt'] = None

            # SAFETY-NET: ตรวจสอบว่าเครื่องปฏิเสธการตั้งค่าด้านบนหรือไม่
            err_res = lcr.inst.query(":SYSTem:ERRor?").strip()
            if '"No error"' not in err_res:
                raise ValueError(f"เครื่องปฏิเสธการตั้งค่า (ค่าที่ระบุอาจเกินสเปคเครื่อง):\n{err_res}")

            # ========================================================
            # 3. เริ่มทำการวัด
            # ========================================================
            run_mode = self.settings.get('run_mode', 'SINGLE')

            if run_mode == 'SINGLE':
                self._run_single_measurement(lcr)
            elif run_mode == 'SWEEP':
                self._run_sweep_measurement(lcr)
            elif run_mode == 'LIST':
                self._run_list_measurement(lcr)

        except Exception as e:
            self.error_occurred.emit(f"Hardware Error:\n{str(e)}")
        finally:
            # [แก้ไข] ไม่ disconnect() ที่นี่แล้ว — Connection ถูกจัดการโดยปุ่ม Connect/Disconnect
            # ที่ผู้ใช้กดเอง ไม่ใช่เปิด-ปิดทุกครั้งที่วัดเสร็จเหมือนก่อนหน้านี้
            self.finished.emit()

    def _handle_hardware_status(self, stat: str, current_freq: float = None):
        """จัดการข้อความ Error แยกตามประเภทให้ผู้ใช้อ่านเข้าใจง่ายขึ้น"""
        freq_info = f" ที่ความถี่ {current_freq:.1f}Hz" if current_freq else ""

        if stat == "OVERLOAD":
            self.error_occurred.emit(f"⚠️ ค่าเกินย่านวัด (OVERLOAD){freq_info} ชิ้นงานอาจช็อต/ขาด หรือเลือกช่วงวัดผิด")
        elif stat == "NO_DATA":
            self.error_occurred.emit(f"⚠️ เครื่องไม่มีข้อมูลในบัฟเฟอร์ (NO DATA){freq_info}")
        elif stat == "SIGNAL_SOURCE_OVERLOAD":
            self.error_occurred.emit(f"⚠️ แหล่งจ่ายสัญญาณท่วม (Signal Source Overload){freq_info} ลองลดระดับแรงดัน (Volt)")
        elif stat == "ALC_FAIL":
            self.error_occurred.emit(f"⚠️ ระบบปรับระดับสัญญาณอัตโนมัติล้มเหลว (ALC Unable to Regulate){freq_info}")
        else:
            self.error_occurred.emit(f"การวัดขัดข้อง{freq_info} (Status: {stat})")

    def _run_single_measurement(self, lcr):
        """
        ตรรกะการวัดค่าแบบจุดเดียว (Single Point)
        - วัดซ้ำ n_single ครั้ง ตามที่ผู้ใช้กำหนด
        - Discard First: ทิ้งค่าแรก discard_single ครั้ง เฉพาะตอนเริ่ม session ใหม่
          (ตรวจจากการที่ยังไม่มีข้อมูลใน graph_x_data ก่อนกด Start ครั้งนี้)
        """
        n_single         = max(1, int(self.settings.get('n_single', 1)))
        discard_single   = max(0, int(self.settings.get('discard_single', 0)))
        is_first_session = self.settings.get('is_first_single_session', True)

        total_rounds = (discard_single if is_first_session else 0) + n_single
        freq = self.settings.get('freq', 1000.0)

        for round_idx in range(total_rounds):
            if not self.is_running:
                break

            is_discarded = is_first_session and (round_idx < discard_single)

            lcr.wait_until_ready()
            # [แก้ไข] ใช้ trigger_and_fetch() แทน trigger()+fetch_measurement() แยกกัน
            # ป้องกันบั๊ก response ค้างใน buffer ของเครื่อง (อ่านค่าเก่า+ใหม่ปนกัน)
            pri, sec, stat = lcr.trigger_and_fetch()

            if is_discarded:
                # วัดเพื่อทิ้ง — ไม่ emit data_ready
                continue

            usable_idx = round_idx - (discard_single if is_first_session else 0)
            percent = int(((usable_idx + 1) / n_single) * 100)
            self.progress_updated.emit(percent)

            if stat == "SUCCESS":
                self.data_ready.emit({
                    'freq':      freq,
                    'primary':   float(pri),
                    'secondary': float(sec),
                    'primary_raw':   lcr.last_raw_strings[0],
                    'secondary_raw': lcr.last_raw_strings[1],
                    'status':    stat
                })
            else:
                self._handle_hardware_status(stat, current_freq=freq)

    def _run_sweep_measurement(self, lcr):
        """
        ตรรกะการวัดค่าแบบสแกนความถี่ (Linear sweep ด้วย Step size)
        วัดซ้ำ N ครั้ง (samples_per_freq) ต่อความถี่ 1 จุดก่อนขยับไปความถี่ถัดไป
        เหมือนกับโหมด LIST ทุกประการ (รวม Discard First Reading)
        """
        start_f = self.settings.get('start_freq', 100.0)
        stop_f  = self.settings.get('stop_freq', 1000000.0)
        step_f  = self.settings.get('step_freq', 20000.0)

        samples       = max(1, int(self.settings.get('samples_per_freq', 1)))
        discard_first = max(0, int(self.settings.get('discard_first', 0)))
        total_rounds_per_freq = discard_first + samples

        if step_f <= 0:
            step_f = 1.0

        # [แก้ไข] ใช้ round() แทน int() เพื่อกัน floating-point error
        # เช่น (2000000 - 100) / 100 อาจได้ 19998.999999999998 แทนที่จะเป็น 19999.0 พอดี
        # ทำให้ int() ตัดเศษทิ้งผิดจุด จุดสุดท้ายที่วัดจริงคลาดจากที่ตั้งไว้ (เช่นได้ 1999900 แทน 2000000)
        n_points_calculated = round((stop_f - start_f) / step_f) + 1
        # [แก้ไข] เอาเพดาน 201 จุดออก — ค่านี้เดิมอ้างอิงผิดมาจากสเปค Hardware LIST Sweep
        # ของเครื่อง (:LIST:FREQ) ซึ่งจำกัดจริงแค่โหมด LIST บนตัวเครื่องเท่านั้น
        # แต่โหมด SWEEP นี้สั่งความถี่ทีละจุดผ่าน set_frequency() (SCPI :FREQ) ไม่ได้ใช้
        # ฟีเจอร์ LIST ของเครื่อง จึงไม่มีข้อจำกัด 201 จุดนี้ในทางเทคนิค
        n_points = max(2, n_points_calculated)

        frequencies = [start_f + i * step_f for i in range(n_points)]
        frequencies = [min(f, stop_f) for f in frequencies]

        total_points = len(frequencies) * total_rounds_per_freq
        done_points  = 0

        for current_freq in frequencies:
            if not self.is_running:
                break

            lcr.set_frequency(current_freq)
            lcr.wait_until_ready()

            for round_index in range(total_rounds_per_freq):
                if not self.is_running:
                    break

                # [แก้ไข] ใช้ trigger_and_fetch() แทน trigger()+fetch_measurement() แยกกัน
                pri, sec, stat = lcr.trigger_and_fetch()

                done_points += 1
                percent = int((done_points / total_points) * 100)
                self.progress_updated.emit(percent)

                # รอบแรกสุด (round_index < discard_first) คือรอบที่ "วัดเพิ่ม" เพื่อทิ้ง
                # ไม่นับเป็นส่วนหนึ่งของ samples_per_freq ที่ผู้ใช้ตั้งใจไว้
                is_discarded = round_index < discard_first

                if stat == "SUCCESS":
                    if not is_discarded:
                        usable_sample_index = round_index - discard_first + 1  # 1..samples
                        self.data_ready.emit({
                            'freq':         current_freq,
                            'sample_index': usable_sample_index,
                            'primary':      float(pri),
                            'secondary':    float(sec),
                            'primary_raw':   lcr.last_raw_strings[0],
                            'secondary_raw': lcr.last_raw_strings[1],
                            'status':       stat
                        })
                elif not is_discarded:
                    self._handle_hardware_status(stat, current_freq)

    # ========================================================
    # [ใหม่] โหมด Frequency List + Samples per Sweep
    # ========================================================
    @staticmethod
    def _parse_freq_list(raw_text: str) -> list:
        """
        แปลง string เช่น '100, 1k, 10k, 100k, 1M, 2M' เป็น list ของ float (หน่วย Hz)
        รองรับหน่วยย่อ k (x1e3) และ M (x1e6) ไม่สนตัวพิมพ์เล็ก/ใหญ่
        """
        frequencies = []
        if not raw_text:
            return frequencies

        parts = raw_text.replace(";", ",").split(",")
        for part in parts:
            token = part.strip()
            if not token:
                continue
            try:
                token_upper = token.upper()
                if token_upper.endswith("K"):
                    value = float(token_upper[:-1]) * 1e3
                elif token_upper.endswith("M"):
                    value = float(token_upper[:-1]) * 1e6
                elif token_upper.endswith("G"):
                    value = float(token_upper[:-1]) * 1e9
                else:
                    value = float(token_upper)
                frequencies.append(value)
            except ValueError:
                # ข้ามค่าที่แปลงไม่ได้ (กันไม่ให้ทั้งชุดพังเพราะพิมพ์ผิดจุดเดียว)
                continue

        return frequencies

    def _run_list_measurement(self, lcr):
        """
        ตรรกะการวัดตาม Frequency List ที่ผู้ใช้กำหนดเอง
        วัดซ้ำ N ครั้ง (samples_per_freq) ต่อความถี่ 1 จุด ก่อนขยับไปความถี่ถัดไป
        โครงสร้าง: for freq in freq_list: for sample in range(samples): วัด 1 ค่า

        [Discard First Reading] เป็นการ "วัดเพิ่ม" จากจำนวน samples_per_freq ปกติ
        ไม่ใช่การหักออกจากจำนวนที่ตั้งไว้ เช่น Samples=5 + Discard=3 -> วัดจริง
        ทั้งหมด 8 ครั้งต่อความถี่ แต่ 3 ครั้งแรกจะไม่ถูกส่ง data_ready ออกไป
        (ไม่นำไปคำนวณสถิติ/ไม่ขึ้นกราฟ) เหลือใช้คำนวณสถิติครบตามจำนวน samples
        ที่ผู้ใช้ตั้งใจไว้จริงๆ
        """
        raw_text      = self.settings.get('freq_list_raw', '')
        samples       = max(1, int(self.settings.get('samples_per_freq', 1)))
        discard_first = max(0, int(self.settings.get('discard_first', 0)))

        total_rounds_per_freq = discard_first + samples

        frequencies = self._parse_freq_list(raw_text)

        if not frequencies:
            self.error_occurred.emit("⚠️ รายการความถี่ไม่ถูกต้องหรือว่างเปล่า กรุณากรอกใหม่ เช่น 100, 1k, 10k")
            return

        total_points = len(frequencies) * total_rounds_per_freq
        done_points  = 0

        for current_freq in frequencies:
            if not self.is_running:
                break

            lcr.set_frequency(current_freq)
            lcr.wait_until_ready()

            for round_index in range(total_rounds_per_freq):
                if not self.is_running:
                    break

                # [แก้ไข] ใช้ trigger_and_fetch() แทน trigger()+fetch_measurement() แยกกัน
                pri, sec, stat = lcr.trigger_and_fetch()

                done_points += 1
                percent = int((done_points / total_points) * 100)
                self.progress_updated.emit(percent)

                # รอบแรกสุด (round_index < discard_first) คือรอบที่ "วัดเพิ่ม" เพื่อทิ้ง
                # ไม่นับเป็นส่วนหนึ่งของ samples_per_freq ที่ผู้ใช้ตั้งใจไว้
                is_discarded = round_index < discard_first

                if stat == "SUCCESS":
                    if not is_discarded:
                        usable_sample_index = round_index - discard_first + 1  # 1..samples
                        self.data_ready.emit({
                            'freq':         current_freq,
                            'sample_index': usable_sample_index,
                            'primary':      float(pri),
                            'secondary':    float(sec),
                            'primary_raw':   lcr.last_raw_strings[0],
                            'secondary_raw': lcr.last_raw_strings[1],
                            'status':       stat
                        })
                elif not is_discarded:
                    self._handle_hardware_status(stat, current_freq)

    def stop(self):
        """ฟังก์ชันหยุดฉุกเฉิน"""
        self.is_running = False