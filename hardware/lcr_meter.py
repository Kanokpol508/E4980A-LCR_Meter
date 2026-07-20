# Class หลักสำหรับสั่งการ E4980A (แปลงคำสั่งเป็น SCPI)

import pyvisa
import time

class E4980A:
    def __init__(self):
        """กำหนดค่าเริ่มต้นของเครื่อง"""
        self.rm = pyvisa.ResourceManager()
        self.inst = None
        self.is_connected = False
        self.OVERLOAD_LIMIT = 9.9e37                # ค่าคงที่สำหรับตรวจสอบสถานะท่วมย่านวัด

    @staticmethod
    def scan_ports() -> list:
        """สแกนหาพอร์ต VISA ทั้งหมดที่เชื่อมต่ออยู่ (ใช้ร่วมกับหน้าต่าง GUI)"""
        try:
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()
            return list(resources)
        except Exception as e:
            print(f"VISA Scan Error: {e}")
            return []

    # ==========================================
    # ระบบเชื่อมต่อ (Connection Management)
    # ==========================================
    def connect(self, resource_address):
        """เชื่อมต่อกับเครื่อง LCR Meter"""
        try:
            self.inst = self.rm.open_resource(resource_address)
            self.inst.timeout = 5000                # ค่า timeout เริ่มต้น (ms) — จะถูกปรับโดย set_measurement_timeout() ก่อนวัดจริง

            # เคลียร์ Error ค้างเก่า
            self.inst.write("*CLS")

            # ป้องกัน Trigger หลุด: ตั้ง Source เป็น BUS และเปิดโหมดรับ Trigger ต่อเนื่อง
            self.inst.write(":TRIGger:SOURce BUS")
            self.inst.write(":INITiate:CONTinuous ON")

            idn = self.inst.query("*IDN?")

            self.is_connected = True
            print(f"✅ เชื่อมต่อสำเร็จ: {idn.strip()}")
            return True, idn.strip()

        except Exception as e:
            self.is_connected = False
            error_msg = f"❌ ไม่สามารถเชื่อมต่อได้: {str(e)}"
            print(error_msg)
            return False, error_msg

    def disconnect(self):
        """ตัดการเชื่อมต่อเพื่อคืนทรัพยากรให้ระบบ"""
        if self.inst:
            try:
                # คืนค่า Trigger กลับสู่สถานะมาตรฐาน (Preset)
                self.inst.write(":INITiate:CONTinuous OFF")
                self.inst.write(":TRIGger:SOURce INTernal")
            except:
                pass
            self.inst.close()
            self.is_connected = False
            print("ปิดการเชื่อมต่อเรียบร้อยแล้ว")

    # ==========================================
    # ระบบความปลอดภัยและจัดการจังหวะเวลา (Timing & Safety)
    # ==========================================
    def wait_until_ready(self):
        """รอจนกว่าเครื่องจะประมวลผลคำสั่งก่อนหน้าเสร็จ 100% ป้องกันคำสั่งชนกัน"""
        if not self.is_connected:
            return
        try:
            self.inst.query("*OPC?")
        except pyvisa.errors.VisaIOError:
            pass

    # ตาราง base time (ms) ต่อ 1 reading สำหรับแต่ละ time_mode
    # อ้างอิงจาก Keysight E4980A Datasheet (Measurement Speed):
    #   SHORT  ≈   7 ms/reading
    #   MEDIUM ≈  20 ms/reading
    #   LONG   ≈  80 ms/reading
    _BASE_TIME_MS = {
        "SHORT": 7,
        "SHOR":  7,
        "MED":   20,
        "MEDIUM":20,
        "LONG":  80,
    }
    # overhead ของ VISA I/O + jitter + processing บน host + margin ความปลอดภัย
    _OVERHEAD_MS = 2000   # 2 วินาที สำหรับ VISA roundtrip + UI overhead
    _MARGIN_MULT = 1.5    # คูณ safety factor 1.5× กันกรณีเครื่องช้ากว่า spec ทั่วไป

    def set_measurement_timeout(self, time_mode: str, averaging: int = 1):
        """
        ปรับ VISA timeout แบบไดนามิกให้เหมาะกับ time_mode และ averaging ที่ใช้จริง
        ป้องกัน VisaIOError: Timeout เมื่อใช้ LONG aperture ร่วมกับ averaging จำนวนมาก

        สูตร:  timeout = (_BASE_TIME_MS[mode] × avg × _MARGIN_MULT) + _OVERHEAD_MS
        ตัวอย่าง:
            LONG + avg=256 → (80 × 256 × 1.5) + 2000 ≈ 32,720 ms (~33 วินาที)
            SHORT + avg=1  → (7  × 1   × 1.5) + 2000 ≈  2,011 ms (~2 วินาที)

        เรียกหลัง connect() และหลัง set_aperture() เสมอ
        ค่า timeout ไม่ต่ำกว่า 5,000 ms (ค่าเริ่มต้น) เพื่อรองรับ overhead พื้นฐาน
        """
        if not self.is_connected:
            return

        avg_clamped = max(1, min(256, int(averaging)))
        mode_key    = str(time_mode).upper()
        base_ms     = self._BASE_TIME_MS.get(mode_key, 20)   # fallback เป็น MEDIUM ถ้า key ไม่พบ

        calculated  = int(base_ms * avg_clamped * self._MARGIN_MULT) + self._OVERHEAD_MS
        new_timeout = max(5000, calculated)

        self.inst.timeout = new_timeout
        print(f"⏱ Timeout ปรับเป็น {new_timeout} ms "
              f"(mode={mode_key}, avg={avg_clamped}, base={base_ms}ms/reading)")

    # ==========================================
    # ระบบชดเชยค่าสายวัด (Correction) - OPEN / SHORT
    # ==========================================
    def perform_correction(self, corr_type: str, cable_text: str = None) -> tuple[bool, str]:
        """สั่งเครื่องทำ OPEN หรือ SHORT Correction แบบเต็มรูปแบบ

        [แก้ไข] ต้องตั้งค่า Cable Length ให้ตรงกับสายวัดจริงก่อนทำ Correction เสมอ
        เพราะค่า OPEN/SHORT ที่วัดได้จะผูกกับ Cable Length ที่ตั้งไว้ ณ ขณะนั้น
        ถ้าไม่ส่ง cable_text (None) จะใช้ค่า Cable Length ที่ค้างอยู่ในเครื่องจากครั้งก่อนแทน
        (ควรหลีกเลี่ยง เพราะอาจไม่ตรงกับที่ผู้ใช้เลือกไว้ใน GUI)
        """
        if not self.is_connected:
            return False, "⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด"

        # ป้องกัน NameError ใน finally
        original_timeout = 5000

        try:
            # 1. การทำ Correction ใช้เวลานาน ต้องเพิ่ม Timeout
            original_timeout = self.inst.timeout
            self.inst.timeout = 180000

            # 1.1 [ใหม่] ตั้งค่า Cable Length ให้ตรงกับสายวัดจริงก่อนทำ Correction เสมอ
            if cable_text is not None:
                self.set_cable_length(cable_text)
                self.wait_until_ready()

            # 2. เปิดโหมด Correction ให้เป็น ON ก่อน แล้วสั่ง Execute
            if corr_type.upper() == "OPEN":
                self.inst.write(":CORR:OPEN:STAT ON")
                self.inst.write(":CORR:OPEN:EXEC")
            elif corr_type.upper() == "SHORT":
                self.inst.write(":CORR:SHOR:STAT ON")
                self.inst.write(":CORR:SHOR:EXEC")
            else:
                return False, "ประเภท Correction ไม่ถูกต้อง"

            # 3. ใช้ wait_until_ready รอสถานะ OPC แทนการใส่ ;*OPC? ต่อท้าย
            self.wait_until_ready()

            return True, f"ทำ {corr_type.upper()} Correction สำเร็จเรียบร้อย!"

        except pyvisa.errors.VisaIOError as e:
            return False, f"หมดเวลารอ (Timeout) เครื่องใช้เวลาประมวลผลนานเกินไป\n{str(e)}"
        except Exception as e:
            return False, f"เกิดข้อผิดพลาดในการส่งคำสั่ง: {str(e)}"
        finally:
            # 4. คืนค่า Timeout กลับสู่โหมดวัดปกติ อย่างปลอดภัย
            if self.is_connected and self.inst:
                try:
                    self.inst.timeout = original_timeout
                except:
                    pass

    # ==========================================
    # ระบบตั้งค่า (Configuration Methods)
    # ==========================================
    def set_measurement_mode(self, mode: str):
        """ตั้งโหมดวัด เช่น CPD, ZTD"""
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        self.inst.write(f":FUNCtion:IMPedance:TYPE {mode}")

    def set_frequency(self, freq: float):
        """ตั้งความถี่ทดสอบ (Hz)"""
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        self.inst.write(f":FREQuency:CW {freq}")

    def set_signal_level(self, level: float, mode: str = 'Voltage'):
        """
        ตั้งระดับสัญญาณทดสอบ (Test Signal Level)
        - mode = 'Voltage' -> ตั้งแรงดัน AC (หน่วย Vrms) ใช้กับ Capacitor
        - mode = 'Current' -> ตั้งกระแส AC (หน่วย Arms) ใช้กับ Inductor
        คำสั่ง SCPI: :VOLTage:LEVel หรือ :CURRent:LEVel ตามโหมด
        """
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        if mode == 'Current':
            self.inst.write(f":CURRent:LEVel {level}")
        else:
            self.inst.write(f":VOLTage:LEVel {level}")

    def set_alc(self, enabled: bool):
        """
        ตั้งค่า ALC (Automatic Level Control)
        - enabled = True  -> เปิด ALC ทำให้ระดับสัญญาณ ณ จุดชิ้นงานเท่ากับค่าที่ตั้ง
        - enabled = False -> ปิด ALC ระดับสัญญาณถูกตั้งที่ขั้วส่งออกของเครื่อง (ค่าเริ่มต้น)
        แนะนำเปิดเมื่อวัด Inductor ด้วย Current Mode เพื่อให้กระแสคงที่ตลอดการวัด
        """
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        self.inst.write(f":AMPLitude:ALC {'ON' if enabled else 'OFF'}")

    # ตาราง Map ชื่อที่ UI ใช้ → SCPI token ที่ :APERture รับได้จริง
    _TIME_MODE_MAP = {
        "SHORT":  "SHOR",
        "MEDIUM": "MED",
        "LONG":   "LONG",
        "SHOR":   "SHOR",   # fallback ถ้าส่งมาเป็น token ตรงๆ อยู่แล้ว
        "MED":    "MED",
    }

    def set_aperture(self, time_mode: str, averaging: int = 1):
        """
        ตั้งเวลาการวัดและค่าเฉลี่ย
        รับค่า 'SHORT' / 'MEDIUM' / 'LONG' จาก UI แล้ว map เป็น SCPI token
        (SCPI รับได้แค่ SHOR / MED / LONG — ไม่รับ MEDIUM)
        """
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")

        avg_factor = max(1, min(256, int(averaging)))
        scpi_token = self._TIME_MODE_MAP.get(time_mode.upper(), "MED")
        self.inst.write(f":APERture {scpi_token},{avg_factor}")

    def set_cable_length(self, cable_text: str):
        """
        [ใหม่] ตั้งค่าการชดเชยความยาวสายวัด (Cable Length Correction)
        รับค่าจาก GUI Combobox เช่น "0 m", "1 m", "2 m", "4 m"
        แล้วแปลงเป็นตัวเลข 0/1/2/4 ก่อนส่งคำสั่ง :CORRection:LENGth

        หมายเหตุ: คำสั่งนี้เป็นการตั้งค่าถาวร ไม่ต้องกด Execute เหมือน OPEN/SHORT
        Correction - มีผลกับการวัดทุกครั้งทันทีที่ตั้ง ไม่ว่าจะเคยทำ
        OPEN/SHORT Correction มาก่อนหรือไม่ก็ตาม จึงต้องตั้งให้ตรงกับสายที่ใช้จริงเสมอ
        """
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")

        try:
            cable_val = str(cable_text).replace("m", "").strip()
            cable_val = int(float(cable_val))
        except (ValueError, TypeError):
            cable_val = 0               # ค่า fallback ปลอดภัยหากแปลงไม่ได้

        self.inst.write(f":CORRection:LENGth {cable_val}")

    def set_impedance_range(self, imp_range):
        """
        ตั้งย่านวัดอิมพีแดนซ์ (Z Range)
        - imp_range = 'AUTO'  -> เปิดโหมด Auto Range
        - imp_range = ตัวเลข  -> ล็อค Range ที่ค่าที่กำหนด (หน่วย Ω) เช่น 100, 1000
        หมายเหตุ: เมื่อส่งคำสั่ง RANGe ตรงๆ เครื่องจะปิด AUTO ให้อัตโนมัติตามคู่มือ
        จึงไม่ต้องส่งคำสั่งปิด AUTO ก่อน
        """
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")

        if str(imp_range) == 'AUTO':
            self.inst.write(":FUNCtion:IMPedance:RANGe:AUTO ON")
        else:
            self.inst.write(f":FUNCtion:IMPedance:RANGe {imp_range}")

    def trigger(self):
        """บังคับ Trigger 1 ครั้ง"""
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        self.inst.write("*TRG")

    # ==========================================
    # ระบบอ่านค่า (Measurement Methods)
    # ==========================================
    def fetch_measurement(self):
        """สั่งทริกเกอร์และอ่านค่าวัด คืนค่าเป็น (primary, secondary, status)"""
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")

        try:
            raw_data = self.inst.query(":FETCh?")
            parts = raw_data.strip().split(',')

            # รองรับ 3 ค่า (ตอนปิด Comparator) หรือ 4 ค่า (ตอนเปิด Comparator)
            if len(parts) not in [3, 4]:
                return None, None, f"PARSE_ERROR: ข้อมูลผิดรูปแบบ ({raw_data})"

            primary   = float(parts[0])
            secondary = float(parts[1])
            status    = int(float(parts[2]))

            # ตรวจสอบ Status โค้ดตามคู่มือ
            if status == -1:
                return None, None, "NO_DATA"
            elif status == 1:
                return None, None, "OVERLOAD"
            elif status == 3:
                return None, None, "SIGNAL_SOURCE_OVERLOAD"
            elif status == 4:
                return None, None, "ALC_FAIL"
            elif status != 0:
                return None, None, f"UNKNOWN_ERROR_CODE_{status}"

            # ดักจับ Overload ทั้งบวก (+9.9e37) และลบ (-9.9e37)
            # กรณีลบเกิดเมื่อวัด C/L ที่ขาดหรือช็อตแบบมีขั้ว
            if abs(primary) >= self.OVERLOAD_LIMIT or abs(secondary) >= self.OVERLOAD_LIMIT:
                return None, None, "OVERLOAD"

            return primary, secondary, "SUCCESS"

        except pyvisa.errors.VisaIOError as e:
            return None, None, f"TIMEOUT/IO_ERROR: {str(e)}"