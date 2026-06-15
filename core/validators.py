# ลอจิกตรวจสอบความถูกต้อง ของค่าที่ผู้ใช้กรอกเข้ามา (Input Validation) อ้างอิงจากคู่มือ Keysight E4980A/AL Programmer's Guide


class E4980AValidator:
    # ==========================================
    # ข้อจำกัด (Limits) ของตัวเครื่อง E4980A 
    # (อ้างอิงตามสเปคมาตรฐาน)
    # ==========================================
    FREQ_MIN = 20.0        # 20 Hz
    
    # ขีดจำกัดความถี่สูงสุด แยกตามรุ่นย่อย
    FREQ_MAX_BY_MODEL = {
        "E4980A":       2_000_000.0,
        "E4980AL-102":  1_000_000.0,
        "E4980AL-052":    500_000.0,
        "E4980AL-032":    300_000.0,
    }

    VOLT_MIN = 0.0         # 0 Vrms

    AVG_MIN = 1            # ค่าเฉลี่ยต่ำสุด
    AVG_MAX = 256          # ค่าเฉลี่ยสูงสุด

    SWEEP_POINTS_MAX = 201 # จำนวนจุดสูงสุดในการทำ List Sweep

    @staticmethod
    def validate_frequency(freq_str: str, model: str = "E4980A") -> tuple[bool, str, float]:
        """
        ตรวจสอบความถี่ทดสอบ (Test Frequency)
        รองรับ: รุ่นย่อยตามพารามิเตอร์ model
        """
        try:
            freq = float(freq_str)
            freq_max = E4980AValidator.FREQ_MAX_BY_MODEL.get(model, 2_000_000.0)

            if freq < E4980AValidator.FREQ_MIN:
                return False, f"⚠️ ความถี่ต่ำสุด {E4980AValidator.FREQ_MIN} Hz", 0.0
            if freq > freq_max:
                return False, f"⚠️ รุ่น {model} รองรับสูงสุด {freq_max/1e6:.1f} MHz", 0.0
            
            return True, "", freq
        except ValueError:
            return False, "⚠️ กรุณากรอกความถี่เป็นตัวเลข", 0.0

    @staticmethod
    def validate_voltage(volt_str: str, has_opt001: bool = False, freq_hz: float = 0.0) -> tuple[bool, str, float]:
        """
        ตรวจสอบแรงดันสัญญาณทดสอบ (Test Signal Voltage Level)
        รองรับ Option 001 และเช็คขีดจำกัดจากระดับความถี่
        """
        try:
            volt = float(volt_str)
            if volt < E4980AValidator.VOLT_MIN:
                return False, "⚠️ แรงดัน AC ต้องไม่ติดลบ", 0.0

            if has_opt001:
                # ถ้ามี Option 001: ความถี่ > 1MHz ลิมิตคือ 15Vrms, ถ้าไม่เกินคือ 20Vrms
                v_max = 15.0 if freq_hz > 1_000_000.0 else 20.0
            else:
                # ถ้าไม่มี Option 001 เครื่องปกติจ่ายได้สูงสุด 2.0 Vrms
                v_max = 2.0

            if volt > v_max:
                return False, f"⚠️ แรงดัน AC สูงสุด {v_max} Vrms สำหรับการตั้งค่านี้", 0.0
            
            return True, "", volt
        except ValueError:
            return False, "⚠️ กรุณากรอกแรงดันเป็นตัวเลข", 0.0

    @staticmethod
    def validate_average(avg_str: str) -> tuple[bool, str, int]:
        """
        ตรวจสอบค่าเฉลี่ย (Averaging Factor)
        รองรับ: 1 ถึง 256
        """
        try:
            avg = int(avg_str)
            if avg < E4980AValidator.AVG_MIN or avg > E4980AValidator.AVG_MAX:
                return False, f"⚠️ ค่าเฉลี่ยต้องอยู่ระหว่าง {E4980AValidator.AVG_MIN} ถึง {E4980AValidator.AVG_MAX}", 1
            return True, "", avg
        except ValueError:
            return False, "⚠️ กรุณากรอกค่าเฉลี่ยเป็นจำนวนเต็ม", 1

    @staticmethod
    def validate_sweep_settings(start_str: str, stop_str: str, points_str: str, model: str = "E4980A") -> tuple[bool, str, dict]:
        """
        ตรวจสอบการตั้งค่า List Sweep
        - Start Freq ต้องน้อยกว่า Stop Freq
        - ความถี่ต้องอยู่ในสเปคของเครื่องแต่ละรุ่น
        - Points ต้องไม่เกิน 201 จุด
        """
        # 1. ตรวจสอบ Points ก่อน
        try:
            points = int(points_str)
            if points < 2 or points > E4980AValidator.SWEEP_POINTS_MAX:
                return False, f"⚠️ จำนวนจุด (Points) ต้องอยู่ระหว่าง 2 ถึง {E4980AValidator.SWEEP_POINTS_MAX}", {}
        except ValueError:
            return False, "⚠️ กรุณากรอกจำนวนจุดเป็นจำนวนเต็ม", {}

        # 2. ตรวจสอบ Start / Stop Freq โดยใช้ Model Parameter
        start_valid, start_msg, start_freq = E4980AValidator.validate_frequency(start_str, model)
        if not start_valid:
            return False, f"Start Freq: {start_msg}", {}

        stop_valid, stop_msg, stop_freq = E4980AValidator.validate_frequency(stop_str, model)
        if not stop_valid:
            return False, f"Stop Freq: {stop_msg}", {}

        # 3. ตรวจสอบเงื่อนไข Start ต้องน้อยกว่า Stop
        if start_freq >= stop_freq:
            return False, "⚠️ Start Freq ต้องมีค่าน้อยกว่า Stop Freq", {}

        # ถ้าผ่านทั้งหมด ส่งค่าที่แปลงเป็นตัวเลขกลับไปให้ใช้งานต่อได้เลย
        return True, "", {
            "start": start_freq,
            "stop": stop_freq,
            "points": points
        }

    @staticmethod
    def validate_dc_bias(level_str: str, is_voltage: bool, has_opt001: bool) -> tuple[bool, str, float]:
        """
        ตรวจสอบค่า DC Bias Level ครอบคลุมทั้งโหมดแรงดันและกระแส
        """
        try:
            level = float(level_str)

            if is_voltage:
                if has_opt001:
                    if not (-40.0 <= level <= 40.0):
                        return False, "⚠️ Option 001: แรงดัน Bias ต้องอยู่ระหว่าง -40V ถึง +40V", 0.0
                else:
                    DISCRETE = [0.0, 1.5, 2.0]
                    TOLERANCE = 1e-9
                    if not any(abs(level - v) < TOLERANCE for v in DISCRETE):
                        return False, "⚠️ เครื่องปกติรับได้เฉพาะ 0V, 1.5V, 2.0V เท่านั้น", 0.0
            else:  # Current
                if not has_opt001:
                    return False, "⚠️ Current Bias ต้องการ Option 001", 0.0
                if not (-0.1 <= level <= 0.1):
                    return False, "⚠️ กระแส Bias ต้องอยู่ระหว่าง -100mA ถึง +100mA", 0.0

            return True, "", level
        except ValueError:
            return False, "⚠️ กรุณากรอกค่าเป็นตัวเลข", 0.0

    @staticmethod
    def validate_deviation_ref(ref_str: str) -> tuple[bool, str, float]:
        """
        ตรวจสอบค่า Primary Ref ของระบบ Deviation (ห้ามว่างและห้ามเป็น 0)
        """
        if not ref_str.strip():
            return False, "⚠️ กรุณากรอก Reference Value", 0.0
        try:
            ref = float(ref_str)
            if ref == 0.0:
                return False, "⚠️ Reference Value ต้องไม่เป็น 0 (ป้องกันหารศูนย์)", 0.0
            return True, "", ref
        except ValueError:
            return False, "⚠️ กรุณากรอกค่าเป็นตัวเลข", 0.0