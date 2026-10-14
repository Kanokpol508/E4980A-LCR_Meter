# หน้าที่คุยกับเครื่อง LCR แบบ "ทำงานอยู่เบื้องหลัง (Background)" ปล่อยให้หน้าต่างโปรแกรมหลักยังคงตอบสนองได้ 
# และสามารถส่งสัญญาณกลับมาบอก GUI ได้ว่า "กำลังทำอยู่..." หรือ "เสร็จแล้ว"


from PyQt6.QtCore import QThread, pyqtSignal

class CorrectionWorker(QThread):
    """
    Worker Thread สำหรับทำการชดเชยค่าสายวัด (OPEN/SHORT Correction)
    ออกแบบมาให้ทำงานเบื้องหลัง เพื่อป้องกันไม่ให้หน้าจอ GUI ค้าง (Freeze)
    เนื่องจากคำสั่ง Execution นี้อาจใช้เวลา 15 - 60 วินาที
    """
    
    # ส่งสัญญาณ (Signal) คืนค่ากลับเมื่อทำงานเสร็จ: (สถานะ True/False, ข้อความตอบกลับ)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, lcr, corr_type: str, cable_text: str = "0 m"):
        super().__init__()
        # รับ instance ที่เชื่อมต่อไว้แล้วจากปุ่ม Connect แทนที่จะเปิด Connection ใหม่เอง
        self.lcr = lcr
        self.corr_type = corr_type              # 'OPEN' หรือ 'SHORT'
        # Cable Length ปัจจุบันจาก GUI — ต้องตั้งที่เครื่องก่อนทำ Correction เสมอ
        # เพื่อให้ค่า OPEN/SHORT ที่วัดได้ตรงกับสายวัดจริงที่ใช้งาน
        self.cable_text = cable_text

    def run(self):
        lcr = self.lcr
        try:
            if not lcr.is_connected:
                self.finished_signal.emit(False, "ยังไม่ได้เชื่อมต่อเครื่องมือวัด — กรุณากด CONNECT ก่อน")
                return

            # สั่งทำ Correction ผ่านฟังก์ชัน perform_correction ที่เซฟตี้แล้วใน lcr_meter
            # ส่ง cable_text เข้าไปด้วย เพื่อตั้ง Cable Length ให้ตรงกับ GUI ก่อน Execute เสมอ
            succ, result_msg = lcr.perform_correction(self.corr_type, self.cable_text)

            # ส่งผลลัพธ์กลับไปยังหน้าจอหลัก
            self.finished_signal.emit(succ, result_msg)

        except Exception as e:
            self.finished_signal.emit(False, f"เกิดข้อผิดพลาดรุนแรง:\n{str(e)}")
        # ไม่ disconnect() ที่นี่แล้ว — Connection ถูกจัดการโดยปุ่ม Connect/Disconnect ที่ผู้ใช้กดเอง