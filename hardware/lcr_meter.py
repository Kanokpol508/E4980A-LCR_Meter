# Class หลักสำหรับสั่งการ E4980A (แปลงคำสั่งเป็น SCPI)


import pyvisa
import time

class E4980A:
    def __init__(self):
        """กำหนดค่าเริ่มต้นของเครื่อง"""
        self.rm = pyvisa.ResourceManager()
        self.inst = None
        self.is_connected = False
        self.OVERLOAD_LIMIT = 9.0e37                # ค่าคงที่สำหรับตรวจสอบสถานะท่วมย่านวัด


    # ==========================================
    # ระบบเชื่อมต่อ (Connection Management)
    # ==========================================
    def connect(self, resource_address):
        """เชื่อมต่อกับเครื่อง LCR Meter"""
        try:
            self.inst = self.rm.open_resource(resource_address)
            self.inst.timeout = 5000                # ตั้งเวลารอ (มิลลิวินาที)
            
            # เคลียร์ Error ค้างเก่าและดึงชื่อเครื่อง
            self.inst.write("*CLS")
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
            self.inst.close()
            self.is_connected = False
            print("ปิดการเชื่อมต่อเรียบร้อยแล้ว")


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


    def set_voltage_level(self, voltage: float):
        """ตั้งแรงดันสัญญาณทดสอบ AC (Vrms)"""
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        self.inst.write(f":VOLTage:LEVel {voltage}")


    def trigger(self):
        """บังคับ Trigger 1 ครั้ง"""
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        self.inst.write("*TRG")


    # ==========================================
    # ระบบอ่านค่า (Measurement Methods)
    # ==========================================
    def fetch_measurement(self):
        """
        สั่งทริกเกอร์และอ่านค่าวัด คืนค่าเป็น (primary, secondary, status)
        """
        if not self.is_connected:
            raise ConnectionError("⚠️ ยังไม่ได้เชื่อมต่อเครื่องมือวัด")
        
        try:
            # ใช้ FETCh? เพื่อดึงข้อมูลที่เครื่องวัดเสร็จแล้ว (ให้ทำงานร่วมกับ *TRG หรือระบบ Trigger อัตโนมัติ)
            raw_data = self.inst.query(":FETCh?")
            parts = raw_data.strip().split(',')
            
            if len(parts) != 3:
                return None, None, f"PARSE_ERROR: ข้อมูลผิดรูปแบบ ({raw_data})"
                
            primary = float(parts[0])
            secondary = float(parts[1])
            status = int(parts[2])
            
            # ตรวจสอบ Overload จากค่าตัวเลขที่ท่วมย่านวัด
            if primary >= self.OVERLOAD_LIMIT or secondary >= self.OVERLOAD_LIMIT:
                return None, None, "OVERLOAD"
            
            # ตรวจสอบสถานะขัดข้องอื่นๆ จาก Status Code
            if status == 2:
                return None, None, "NO_CONTACT"
            elif status != 0:
                return None, None, f"HARDWARE_ERROR_{status}"
                
            return primary, secondary, "SUCCESS"
            
        except pyvisa.errors.VisaIOError as e:
            return None, None, f"TIMEOUT/IO_ERROR: {str(e)}"


# ======================================================
# ส่วนทดสอบการทำงานแบบ Manual (รันไฟล์นี้ตรงๆ เพื่อทดสอบ)
# พิมพ์คำสั่ง py hardware/lcr_meter.py ใน Terminal
# ======================================================
if __name__ == "__main__":
    lcr = E4980A()
    
    print("🔍 กำลังสแกนหาอุปกรณ์...")
    resources = lcr.rm.list_resources()
    
    if resources:
        address = resources[0] 
        print(f"🔗 กำลังพยายามเชื่อมต่อกับ: {address}")
        
        success, msg = lcr.connect(address)
        
        if success:
            try:
                print("⚙️ กำลังส่งคำสั่งตั้งค่า: CPD, 100kHz, 1.0V")
                lcr.set_measurement_mode("CPD")
                lcr.set_frequency(100000)
                lcr.set_voltage_level(1.0)
                
                # รอให้วงจรในเครื่องปรับตัวก่อนวัด
                time.sleep(0.5) 
                
                print("📐 กำลังวัดค่า...")
                # บังคับ Trigger 1 ครั้ง (จำลองกรณีไม่ได้ตั้งค่า Trigger เป็น Continuous)
                lcr.trigger()
                
                pri, sec, stat = lcr.fetch_measurement()
                print("-" * 30)
                print(f"พารามิเตอร์หลัก (Cp): {pri:.5e}" if pri else "พารามิเตอร์หลัก: None")
                print(f"พารามิเตอร์รอง (D): {sec:.5e}" if sec else "พารามิเตอร์รอง: None")
                print(f"สถานะ: {stat}")
                print("-" * 30)
                
            except Exception as e:
                print(f"❌ เกิดข้อผิดพลาดระหว่างทำงาน: {e}")
            finally:
                lcr.disconnect()
    else:
        print("⚠️ ไม่พบเครื่องมือวัดใดๆ กรุณาตรวจสอบสายเชื่อมต่อ")