# หน้าที่คุยกับเครื่อง LCR แบบ "ทำงานอยู่เบื้องหลัง (Background)" ปล่อยให้หน้าต่างโปรแกรมหลักยังคงตอบสนองได้ 
# และสามารถส่งสัญญาณกลับมาบอก GUI ได้ว่า "กำลังทำอยู่..." หรือ "เสร็จแล้ว"


from PyQt6.QtCore import QThread, pyqtSignal
from hardware.lcr_meter import E4980A

class CorrectionWorker(QThread):
    """
    Worker Thread สำหรับทำการชดเชยค่าสายวัด (OPEN/SHORT Correction)
    ออกแบบมาให้ทำงานเบื้องหลัง เพื่อป้องกันไม่ให้หน้าจอ GUI ค้าง (Freeze)
    เนื่องจากคำสั่ง Execution นี้อาจใช้เวลา 15 - 60 วินาที
    """
    
    # ส่งสัญญาณ (Signal) คืนค่ากลับเมื่อทำงานเสร็จ: (สถานะ True/False, ข้อความตอบกลับ)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, visa_address: str, corr_type: str):
        super().__init__()
        self.visa_address = visa_address
        self.corr_type = corr_type              # 'OPEN' หรือ 'SHORT'

    def run(self):
        lcr = None
        try:
            # 1. สร้างการเชื่อมต่อใหม่ใน Thread นี้
            lcr = E4980A()
            success, msg = lcr.connect(self.visa_address)
            
            if not success:
                self.finished_signal.emit(False, f"การเชื่อมต่อฮาร์ดแวร์ล้มเหลว:\n{msg}")
                return

            # 2. สั่งทำ Correction (ฟังก์ชันจะ Block ตัวเองจนกว่าเครื่องจะตอบกลับ *OPC?)
            succ, result_msg = lcr.perform_correction(self.corr_type)
            
            # 3. ส่งผลลัพธ์กลับไปยังหน้าจอหลัก
            self.finished_signal.emit(succ, result_msg)
            
        except Exception as e:
            self.finished_signal.emit(False, f"เกิดข้อผิดพลาดรุนแรง:\n{str(e)}")
            
        finally:
            if lcr:
                try:
                    lcr.disconnect()
                except:
                    pass