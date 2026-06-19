# **สำคัญมาก** ทำงานเบื้องหลัง (QThread) เพื่อสแกน Sweep โดยไม่ให้ UI ค้าง

import math
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
            
            # ✅ คืนชีพโค้ดเก่าของคุณ: ใช้ Wrapper Methods สั่งงานอย่างเป็นระเบียบ
            lcr.set_measurement_mode(scpi_mode)
            lcr.set_voltage_level(volt)
            lcr.set_frequency(freq)            # ✅ คืนชีพ: ป้องกันบั๊กไม่อัปเดตความถี่ในโหมด Single
            lcr.set_aperture(time_mode)
            
            # --- ตั้งค่า DC Bias (แบบปลอดภัย) ---
            if 'dc_bias_enabled' in self.settings:
                lcr.apply_dc_bias(
                    enable=self.settings.get('dc_bias_enabled', False),
                    level=self.settings.get('dc_bias_level', 0.0),
                    is_voltage=self.settings.get('dc_is_voltage', True)
                )

            # รอให้ค่าที่เซ็ตเข้าไปทั้งหมดประมวลผลเสร็จสิ้น
            lcr.wait_until_ready()

            # 3. เริ่มทำการวัด
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

        lcr.wait_until_ready() # เซฟตี้ก่อนกด Trigger
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
        """ตรรกะการวัดค่าแบบสแกนความถี่ (List Sweep)"""
        start_f = self.settings.get('start_freq', 100.0)
        stop_f = self.settings.get('stop_freq', 1000000.0)
        points = self.settings.get('sweep_points', 50)
        scale = self.settings.get('sweep_scale', 'LOG')
        
        frequencies = []
        if points > 1:
            if scale == 'LOG':
                log_start = math.log10(start_f)
                log_stop = math.log10(stop_f)
                step = (log_stop - log_start) / (points - 1)
                frequencies = [10**(log_start + i * step) for i in range(points)]
            else:
                step = (stop_f - start_f) / (points - 1)
                frequencies = [start_f + i * step for i in range(points)]
        else:
            frequencies = [start_f]

        for i, current_freq in enumerate(frequencies):
            if not self.is_running:
                break 

            lcr.set_frequency(current_freq)
            lcr.wait_until_ready()  # รอให้เครื่องเปลี่ยนความถี่เสร็จสมบูรณ์ 100%
            
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