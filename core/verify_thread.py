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
            inst.write(f":APERture {s['time_mode']}")
            
            # Averaging
            if s['avg'] > 1:
                inst.write(":AVER:STAT ON")
                inst.write(f":AVER:COUN {s['avg']}")
            else:
                inst.write(":AVER:STAT OFF")
                
            # Cable
            cable_val = s['cable'].replace("m", "").strip()             # แปลง "1 m" เป็น "1"
            inst.write(f":CORR:LENG {cable_val}")

            # Range
            if s['imp_range'] == "AUTO":
                inst.write(":FUNC:IMP:RANG:AUTO ON")
            else:
                inst.write(":FUNC:IMP:RANG:AUTO OFF")
            
            # DC Bias
            if s.get('dc_bias_enabled', False):
                inst.write(":BIAS:STAT ON")
                if s.get('dc_is_voltage', True):
                    inst.write(f":BIAS:VOLT:LEV {s['dc_bias_level']}")
                else:
                    inst.write(f":BIAS:CURR:LEV {s['dc_bias_level']}")
            else:
                inst.write(":BIAS:STAT OFF")
            
            # บังคับรอให้ตั้งค่าเสร็จ
            inst.query("*OPC?")

            # ==========================================
            # 2. VERIFY (ถามค่ากลับมาเช็ค)
            # ==========================================
            def add_res(param, exp, act, passed):
                nonlocal all_passed
                if not passed: all_passed = False
                results.append({"param": param, "expected": exp, "actual": act, "passed": passed})

            # เช็ค Mode
            act_mode = inst.query(":FUNC:IMP:TYPE?").strip()
            add_res("Measurement Mode", s['scpi_mode'], act_mode, act_mode == s['scpi_mode'])

            # เช็ค Freq (ใช้ Tolerance)
            act_freq = inst.query(":FREQuency:CW?").strip()
            add_res("Frequency (Hz)", s['freq'], act_freq, self.check_float_match(s['freq'], act_freq))

            # เช็ค Volt (ใช้ Tolerance)
            act_volt = inst.query(":VOLTage:LEVel?").strip()
            add_res("Voltage (Vrms)", s['volt'], act_volt, self.check_float_match(s['volt'], act_volt))

            # เช็ค Meas Time
            act_time = inst.query(":APERture?").strip().split(',')[0] # เครื่องอาจตอบ SHORT,1
            add_res("Measurement Time", s['time_mode'], act_time, act_time.startswith(s['time_mode'][:4]))

            # เช็ค Averaging
            act_avg_stat = inst.query(":AVER:STAT?").strip()
            if s['avg'] > 1:
                act_avg_coun = inst.query(":AVER:COUN?").strip()
                passed = (act_avg_stat == "1") and (str(s['avg']) == act_avg_coun)
                add_res("Averaging", f"ON ({s['avg']})", f"STAT:{act_avg_stat}, COUN:{act_avg_coun}", passed)
            else:
                add_res("Averaging", "OFF", "STAT:1" if act_avg_stat=="1" else "OFF", act_avg_stat == "0")

            # เช็ค Cable
            act_cable = inst.query(":CORR:LENG?").strip()
            add_res("Cable Length (m)", cable_val, act_cable, self.check_float_match(cable_val, act_cable))

            # เช็ค Range Auto
            act_range_auto = inst.query(":FUNC:IMP:RANG:AUTO?").strip()
            exp_range_auto = "1" if s['imp_range'] == "AUTO" else "0"
            add_res("Range AUTO Status", exp_range_auto, act_range_auto, act_range_auto == exp_range_auto)

            # เช็ค DC Bias
            if s.get('dc_bias_enabled', False):
                act_bias_stat = inst.query(":BIAS:STAT?").strip()
                add_res("DC Bias State", "1", act_bias_stat, act_bias_stat == "1")
                
                if s.get('dc_is_voltage', True):
                    act_bias_level = inst.query(":BIAS:VOLT:LEV?").strip()
                    add_res("DC Bias Voltage (V)", s['dc_bias_level'], act_bias_level, self.check_float_match(s['dc_bias_level'], act_bias_level))
                else:
                    act_bias_level = inst.query(":BIAS:CURR:LEV?").strip()
                    add_res("DC Bias Current (A)", s['dc_bias_level'], act_bias_level, self.check_float_match(s['dc_bias_level'], act_bias_level))
            else:
                act_bias_stat = inst.query(":BIAS:STAT?").strip()
                add_res("DC Bias State", "0", act_bias_stat, act_bias_stat == "0")

            # ==========================================
            # 3. CHECK ERROR QUEUE
            # ==========================================
            err_res = inst.query(":SYST:ERR?").strip()
            has_error = not ('+0,"No error"' in err_res or '0,"No error"' in err_res)
            if has_error:
                error_msg = f"System Error Detected: {err_res}"
                all_passed = False

            # สรุปผลส่งกลับไป
            self.finished_signal.emit(all_passed, results, error_msg)

        except Exception as e:
            self.finished_signal.emit(False, [], f"เกิดข้อผิดพลาดในการตรวจสอบ: {str(e)}")
            
        finally:
            lcr.disconnect()