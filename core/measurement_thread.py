# **สำคัญมาก** ทำงานเบื้องหลัง (QThread) เพื่อสแกน Sweep โดยไม่ให้ UI ค้าง


import math
from PyQt6.QtCore import QThread, pyqtSignal

from hardware.lcr_meter import E4980A 

class MeasurementWorker(QThread):
    """
    คลาสลูกน้องหลังบ้าน ทำหน้าที่สื่อสารกับฮาร์ดแวร์ (LCR Meter) ของจริง
    """
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

            # 2. เริ่มทำการวัด
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

    def _run_single_measurement(self, lcr):
        """ตรรกะการวัดค่าแบบจุดเดียว (Single Point)"""
        if not self.is_running:
            return

        lcr.trigger() 
        
        pri, sec, stat = lcr.fetch_measurement() 

        if stat == 0 or str(stat).upper() == "SUCCESS":
            real_result = {
                'freq': self.settings.get('freq', 1000.0),
                'primary': float(pri),
                'secondary': float(sec)
            }
            self.data_ready.emit(real_result)
        else:
            self.error_occurred.emit(f"สถานะการวัดผิดปกติ (Status: {stat})")

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
            
            lcr.trigger()
            pri, sec, stat = lcr.fetch_measurement()

            percent = int(((i + 1) / points) * 100)
            self.progress_updated.emit(percent)

            if stat == 0 or str(stat).upper() == "SUCCESS":
                real_result = {
                    'freq': current_freq,
                    'primary': float(pri), 
                    'secondary': float(sec)
                }
                self.data_ready.emit(real_result)
            else:
                self.error_occurred.emit(f"จุดที่ {current_freq:.1f}Hz วัดล้มเหลว (Status: {stat})")

    def stop(self):
        """ฟังก์ชันหยุดฉุกเฉิน"""
        self.is_running = False