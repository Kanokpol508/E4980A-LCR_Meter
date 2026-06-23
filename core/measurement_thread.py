# **สำคัญมาก** ทำงานเบื้องหลัง (QThread) เพื่อสแกน Sweep โดยไม่ให้ UI ค้าง

from PyQt6.QtCore import QThread, pyqtSignal
from hardware.lcr_meter import E4980A 

class MeasurementWorker(QThread):
    """คลาสลูกน้องหลังบ้าน ทำหน้าที่สื่อสารกับฮาร์ดแวร์ (LCR Meter) ของจริง"""
    data_ready = pyqtSignal(dict)               # ส่งข้อมูลผลการวัด
    error_occurred = pyqtSignal(str)            # ส่งข้อความ Error
    progress_updated = pyqtSignal(int)          # ส่งเลขเปอร์เซ็นต์
    finished = pyqtSignal()                     # ส่งสัญญาณจบการทำงาน

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings
        self.is_running = True

    def run(self):
        """ลอจิกหลักที่ทำงานใน Thread เบื้องหลัง"""
        lcr = None
        try:
            visa_address = self.settings.get('visa_resource')
            if not visa_address or visa_address == "No Device Found":
                raise ConnectionError("ไม่พบที่อยู่ VISA Resource ที่ถูกต้อง")

            # 1. สร้าง Object และเชื่อมต่อฮาร์ดแวร์ 
            lcr = E4980A()
            success, msg = lcr.connect(visa_address)
            
            if not success:
                raise ConnectionError(f"เชื่อมต่อเครื่องล้มเหลว: {msg}")

            # ========================================================
            # 2. ตั้งค่าเครื่องมือวัดก่อนเริ่มการวัด (Hardware Setup)
            # ========================================================
            scpi_mode = self.settings.get('scpi_mode', 'CPD')
            volt      = self.settings.get('volt', 1.0)
            freq      = self.settings.get('freq', 100000.0)
            time_mode = self.settings.get('time_mode', 'MED')
            avg       = self.settings.get('avg', 1)
            imp_range = self.settings.get('imp_range', 'AUTO')
            
            lcr.set_measurement_mode(scpi_mode)
            lcr.set_voltage_level(volt)
            lcr.set_frequency(freq)
            lcr.set_aperture(time_mode, avg)

            if str(imp_range) == 'AUTO':
                lcr.inst.write(":FUNCtion:IMPedance:RANGe:AUTO ON")
            else:
                lcr.inst.write(f":FUNCtion:IMPedance:RANGe {imp_range}")
            
            # --- ตั้งค่า DC Bias (แบบปลอดภัย) ---
            if 'dc_bias_enabled' in self.settings:
                lcr.apply_dc_bias(
                    enable=self.settings.get('dc_bias_enabled', False),
                    level=self.settings.get('dc_bias_level', 0.0),
                    is_voltage=self.settings.get('dc_is_voltage', True)
                )

            # รอให้ค่าที่เซ็ตเข้าไปทั้งหมดประมวลผลเสร็จสิ้น
            lcr.wait_until_ready()

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

        except Exception as e:
            self.error_occurred.emit(f"Hardware Error:\n{str(e)}")
        finally:
            if lcr:
                try:
                    lcr.disconnect()
                except:
                    pass
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
        """ตรรกะการวัดค่าแบบจุดเดียว (Single Point)"""
        if not self.is_running:
            return

        lcr.wait_until_ready() 
        lcr.trigger() 
        
        pri, sec, stat = lcr.fetch_measurement() 

        if stat == "SUCCESS":
            real_result = {
                'freq': self.settings.get('freq', 1000.0),
                'primary': float(pri),
                'secondary': float(sec)
            }
            self.data_ready.emit(real_result)
        else:
            self._handle_hardware_status(stat)

        self.progress_updated.emit(100)

    def _run_sweep_measurement(self, lcr):
        """ตรรกะการวัดค่าแบบสแกนความถี่ (Linear sweep ด้วย Step size)"""
        start_f = self.settings.get('start_freq', 100.0)
        stop_f = self.settings.get('stop_freq', 1000000.0)
        step_f = self.settings.get('step_freq', 20000.0)
        
        if step_f <= 0:
            step_f = 1.0  

        n_points = int((stop_f - start_f) / step_f) + 1
        n_points = max(2, min(201, n_points))  

        frequencies = [start_f + i * step_f for i in range(n_points)]
        frequencies = [min(f, stop_f) for f in frequencies]  

        points = len(frequencies)

        for i, current_freq in enumerate(frequencies):
            if not self.is_running:
                break 

            lcr.set_frequency(current_freq)
            lcr.wait_until_ready()  
            
            lcr.trigger()
            pri, sec, stat = lcr.fetch_measurement()

            percent = int(((i + 1) / points) * 100)
            self.progress_updated.emit(percent)

            if stat == "SUCCESS":
                real_result = {
                    'freq': current_freq,
                    'primary': float(pri), 
                    'secondary': float(sec)
                }
                self.data_ready.emit(real_result)
            else:
                self._handle_hardware_status(stat, current_freq)

    def stop(self):
        """ฟังก์ชันหยุดฉุกเฉิน"""
        self.is_running = False