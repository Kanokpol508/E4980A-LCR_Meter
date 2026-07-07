# ตัวทำงานเบื้องหลัง ทำหน้าที่คุยกับเครื่อง E4980A ส่งค่าไปตั้ง (Apply) แล้วถามค่ากลับมา (Verify) โดยไม่ให้หน้าจอหลักค้าง

from PyQt6.QtCore import QThread, pyqtSignal
from hardware.lcr_meter import E4980A

class VerifyWorker(QThread):
    # ส่งสัญญาณกลับเมื่อเสร็จ: (สำเร็จทั้งหมดหรือไม่, List ของผลลัพธ์ตาราง, ข้อความ Error รวม)
    finished_signal = pyqtSignal(bool, list, str)

    def __init__(self, visa_address: str, settings: dict):
        super().__init__()
        self.visa_address = visa_address
        self.settings = settings
        self.TOLERANCE = 0.001          # 0.1%

    def check_float_match(self, expected, actual):
        """เช็คค่าทศนิยมโดยใช้ Tolerance แทนการ == ตรงๆ"""
        try:
            exp_val = float(expected)
            act_val = float(actual)
            if exp_val == 0:
                return abs(act_val) < self.TOLERANCE
            return abs(act_val - exp_val) / abs(exp_val) < self.TOLERANCE
        except ValueError:
            return False

    def run(self):
        lcr = E4980A()
        results = []
        all_passed = True
        error_msg = ""

        try:
            success, msg = lcr.connect(self.visa_address)
            if not success:
                self.finished_signal.emit(False, [], f"เชื่อมต่อล้มเหลว: {msg}")
                return

            inst = lcr.inst
            
            # ==========================================
            # 1. APPLY (ตั้งค่าไปที่เครื่อง)
            # ==========================================
            s = self.settings
            inst.write(f":FUNCtion:IMPedance:TYPE {s['scpi_mode']}")
            inst.write(f":FREQuency:CW {s['freq']}")
            inst.write(f":VOLTage:LEVel {s['volt']}")
            
            avg_count = max(1, min(256, int(s['avg'])))
            inst.write(f":APERture {s['time_mode']},{avg_count}")
                
            cable_val = s['cable'].replace("m", "").strip()
            inst.write(f":CORRection:LENGth {cable_val}")

            lcr.set_impedance_range(s['imp_range'])
            
            if s.get('dc_bias_enabled', False):
                inst.write(":BIAS:STAT ON")
                if s.get('dc_is_voltage', True):
                    inst.write(f":BIAS:VOLTage:LEVel {s['dc_bias_level']}")
                else:
                    inst.write(f":BIAS:CURRent:LEVel {s['dc_bias_level']}")
            else:
                inst.write(":BIAS:STAT OFF")
            
            inst.query("*OPC?")

            # ==========================================
            # 2. VERIFY (ถามค่ากลับมาเช็ค)
            # ==========================================
            def add_res(param, exp, act, passed):
                nonlocal all_passed
                if not passed: all_passed = False
                status_text = "✅ PASS" if passed else "❌ FAIL"
                results.append({"param": param, "expected": exp, "actual": act, "status": status_text})

            act_mode = inst.query(":FUNCtion:IMPedance:TYPE?").strip()
            add_res("Measurement Mode", s['scpi_mode'], act_mode, s['scpi_mode'].upper() in act_mode.upper())

            act_freq = inst.query(":FREQuency:CW?").strip()
            add_res("Frequency (Hz)", s['freq'], act_freq, self.check_float_match(s['freq'], act_freq))

            act_volt = inst.query(":VOLTage:LEVel?").strip()
            add_res("Voltage (Vrms)", s['volt'], act_volt, self.check_float_match(s['volt'], act_volt))

            act_aper_raw = inst.query(":APERture?").strip()
            act_aper_parts = act_aper_raw.split(',')
            act_time = act_aper_parts[0]
            act_avg = act_aper_parts[1] if len(act_aper_parts) > 1 else "1"

            # การตรวจสอบเวลา (Time Mode) ให้รองรับคำว่า SHORT, MEDIUM, LONG
            # โดยเช็คว่าคำเต็มจาก GUI ขึ้นต้นด้วย Short-form จากเครื่องหรือไม่ (เช่น "MEDIUM".startswith("MED") -> True)
            add_res("Measurement Time", s['time_mode'], act_time, str(s['time_mode']).upper().startswith(act_time.upper()))
            
            add_res("Averaging", avg_count, act_avg, self.check_float_match(avg_count, act_avg))

            act_cable = inst.query(":CORRection:LENGth?").strip()
            add_res("Cable Length (m)", cable_val, act_cable, self.check_float_match(cable_val, act_cable))

            # เช็ค Range ตามโหมด AUTO / HOLD
            if str(s['imp_range']) == "AUTO":
                act_range_auto = inst.query(":FUNCtion:IMPedance:RANGe:AUTO?").strip()
                add_res("Range Mode", "AUTO", "AUTO" if act_range_auto == "1" else "HOLD", act_range_auto == "1")
            else:
                act_range_val = inst.query(":FUNCtion:IMPedance:RANGe?").strip()
                add_res("Range Mode", f"{s['imp_range']} Ω (HOLD)", f"{act_range_val} Ω", self.check_float_match(s['imp_range'], act_range_val))

            if s.get('dc_bias_enabled', False):
                act_bias_stat = inst.query(":BIAS:STAT?").strip()
                add_res("DC Bias State", "1", act_bias_stat, act_bias_stat == "1")
                
                if s.get('dc_is_voltage', True):
                    act_bias_level = inst.query(":BIAS:VOLTage:LEVel?").strip()
                    add_res("DC Bias Voltage (V)", s['dc_bias_level'], act_bias_level, self.check_float_match(s['dc_bias_level'], act_bias_level))
                else:
                    act_bias_level = inst.query(":BIAS:CURRent:LEVel?").strip()
                    add_res("DC Bias Current (A)", s['dc_bias_level'], act_bias_level, self.check_float_match(s['dc_bias_level'], act_bias_level))
            else:
                act_bias_stat = inst.query(":BIAS:STAT?").strip()
                add_res("DC Bias State", "0", act_bias_stat, act_bias_stat == "0")

            # ==========================================
            # 3. CHECK ERROR QUEUE
            # ==========================================
            err_res = inst.query(":SYSTem:ERRor?").strip()
            has_error = '"No error"' not in err_res
            if has_error:
                error_msg = f"System Error Detected: {err_res}"
                all_passed = False

            self.finished_signal.emit(all_passed, results, error_msg)

        except Exception as e:
            self.finished_signal.emit(False, [], f"เกิดข้อผิดพลาดในการตรวจสอบ: {str(e)}")
            
        finally:
            lcr.disconnect()