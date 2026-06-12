# **สำคัญมาก** ทำงานเบื้องหลัง (QThread) เพื่อสแกน Sweep โดยไม่ให้ UI ค้าง


import time
from PyQt6.QtCore import QThread, pyqtSignal

# นำเข้า Class เครื่องมือวัด (เตรียมไว้ใช้ของจริง)
# from hardware.lcr_meter import E4980A 

class MeasurementWorker(QThread):
    """
    คลาสลูกน้องหลังบ้าน ทำหน้าที่สื่อสารกับฮาร์ดแวร์ (LCR Meter)
    เพื่อให้หน้าต่างโปรแกรม (UI) ไม่ค้างระหว่างรอเครื่องทำงาน
    """
    # ========================================================
    # 1. กำหนด Signals (ท่อส่งสัญญาณ) ไว้คุยกับหน้าต่าง UI
    # ========================================================
    # ส่ง dict กลับไป เช่น {'freq': 1000, 'primary': 1.2e-9, 'secondary': 0.001}
    data_ready = pyqtSignal(dict)   
    
    # ส่งข้อความ Error (str) ไปให้ UI แจ้งเตือนผู้ใช้
    error_occurred = pyqtSignal(str) 
    
    # ส่งตัวเลข % (int) ไปอัปเดต Progress Bar (ถ้ามี)
    progress_updated = pyqtSignal(int) 
    
    # ส่งสัญญาณบอก UI ว่าทำงานเสร็จแล้ว (ให้ UI ปลดล็อกปุ่มต่างๆ)
    finished = pyqtSignal()          

    def __init__(self, settings: dict):
        super().__init__()
        # รับการตั้งค่าทั้งหมดที่ผู้ใช้กรอกหน้า UI มาเก็บไว้
        self.settings = settings
        
        # ธง (Flag) สำหรับควบคุมการหยุดทำงาน ถ้าโดนกดปุ่ม STOP จะกลายเป็น False
        self.is_running = True

    def run(self):
        """
        ฟังก์ชันนี้คือ "สมองของลูกน้อง" มันจะทำงานอัตโนมัติเมื่อเราสั่ง worker.start()
        โค้ดในนี้จะไม่ทำให้ UI ค้างแน่นอน
        """
        lcr = None  # ประกาศตัวแปรไว้ก่อนเพื่อใช้เช็กสถานะตอนจบการทำงาน (finally)
        
        try:
            # ----------------------------------------------------
            # TODO: สร้าง Object ติดต่อเครื่องมือวัดของจริงตรงนี้
            # visa_address = self.settings.get('visa_resource')
            # lcr = E4980A()
            # success, msg = lcr.connect(visa_address)
            # if not success:
            #     raise ConnectionError(msg)
            # 
            # lcr.setup_measurement(self.settings) # เตรียมตั้งค่าเครื่อง
            # ----------------------------------------------------

            run_mode = self.settings.get('run_mode', 'SINGLE')

            if run_mode == 'SINGLE':
                self._run_single_measurement(lcr)
            elif run_mode == 'SWEEP':
                self._run_sweep_measurement(lcr)

        except Exception as e:
            # ถ้าเกิด Error (เช่น สายหลุด, เครื่องไม่ตอบสนอง) ให้ส่งข้อความไปหา UI
            self.error_occurred.emit(f"เกิดข้อผิดพลาดในการเชื่อมต่อฮาร์ดแวร์:\n{str(e)}")
        finally:
            # ต้องตัดการเชื่อมต่อเสมอ ป้องกันพอร์ต VISA ค้าง
            # ถ้าไม่ทำตรงนี้ หากมี Error เกิดขึ้นระหว่างทาง จะทำให้เครื่อง Lock ทันที
            if lcr:
                # lcr.disconnect()
                pass
                
            # ส่งสัญญาณบอก UI ให้รู้ว่า "ทำงานเสร็จสิ้นแล้ว/หยุดแล้ว" เสมอ
            self.finished.emit()

    def _run_single_measurement(self, lcr):
        """ลอจิกการวัดแบบ จุดเดียว (Single Point)"""
        
        # จำลองดีเลย์การรอเครื่องมือวัดทำงาน (เช่น 0.5 วินาที)
        time.sleep(0.5)
        
        # ถ้าผู้ใช้กดปุ่ม STOP ไปแล้ว ให้ออกจากฟังก์ชันทันที
        if not self.is_running:
            return

        # ----------------------------------------------------
        # TODO: ส่งคำสั่ง SCPI ไปถามค่าจากเครื่องจริง
        # result = lcr.fetch_measurement()
        # ----------------------------------------------------

        # จำลองการส่งข้อมูลที่วัดได้กลับไปที่ UI
        mock_result = {
            'freq': self.settings.get('freq', 1000.0),
            'primary': 1.05e-9,  # สมมติได้ค่า 1.05 nF
            'secondary': 0.0012  # สมมติได้ค่า D เป็น 0.0012
        }
        
        self.data_ready.emit(mock_result)
        
        # แจ้งเตือน Progress 100% เพื่อบอกว่าวัดเสร็จเรียบร้อย
        self.progress_updated.emit(100)

    def _run_sweep_measurement(self, lcr):
        """ลอจิกการวัดแบบ สแกนความถี่ (List Sweep)"""
        
        points = self.settings.get('sweep_points', 50)
        
        for i in range(points):
            # ตรวจสอบทุกๆ รอบที่กำลัง Sweep ว่าผู้ใช้กดปุ่ม STOP หรือไม่?
            if not self.is_running:
                break 

            # ----------------------------------------------------
            # TODO: ส่งคำสั่งให้เครื่องวัดจุดถัดไป
            # ⚠️ ข้อควรระวัง: 
            # ควรตั้งค่า Timeout ของ VISA (lcr.inst.timeout) ให้สัมพันธ์กับเวลาในการวัด (Averaging / Time Mode)
            # ไม่อย่างนั้นถ้าตั้ง Averaging ไว้สูงมากๆ Thread นี้จะไปติดแหง็กอยู่ที่บรรทัด fetch_measurement() 
            # ทำให้กด STOP ไม่ได้จนกว่ามันจะ Timeout
            #
            # pri, sec, stat = lcr.fetch_measurement()
            # ----------------------------------------------------
            time.sleep(0.1) # จำลองดีเลย์ของเครื่องต่อ 1 จุด

            # คำนวณความคืบหน้าเป็น % แล้วส่งให้ UI
            percent = int(((i + 1) / points) * 100)
            self.progress_updated.emit(percent)

            # ส่งข้อมูลทีละจุดกลับไปให้ UI (เพื่อนำไปพล็อตกราฟแบบ Real-Time)
            mock_result = {
                'freq': 100.0 + (i * 1000.0),
                'primary': 1.0e-9 + (i * 1e-11), 
                'secondary': 0.001 + (i * 0.0001)
            }
            self.data_ready.emit(mock_result)

    def stop(self):
        """
        ฟังก์ชันฉุกเฉิน: UI จะเรียกใช้ฟังก์ชันนี้เมื่อผู้ใช้คลิกปุ่ม "STOP"
        แค่เปลี่ยนสถานะ flag ให้หลุดออกจาก loop ถัดไป (ปลอดภัยกว่าการ force kill thread)
        """
        self.is_running = False