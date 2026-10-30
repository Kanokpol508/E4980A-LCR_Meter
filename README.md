# LCR Metrology Project

โปรแกรมควบคุมเครื่อง **Keysight E4980A Precision LCR Meter (20 Hz – 2 MHz)** ผ่านคอมพิวเตอร์
เขียนด้วย Python + PyQt6 รองรับการวัดแบบ Single / Sweep / List, แสดงกราฟและตารางสถิติแบบเรียลไทม์,
บันทึกผลการวัด และส่งออกเป็นไฟล์ Excel

## สิ่งที่ต้องมี

| รายการ | รายละเอียด |
|---|---|
| Python | 3.12 (พัฒนาและทดสอบด้วย 3.12) |
| VISA driver | ต้องติดตั้ง VISA backend บนเครื่อง เช่น **NI-VISA** หรือ **Keysight IO Libraries Suite** (ใช้ติดต่อกับเครื่องผ่าน USB/GPIB/LAN) |
| ระบบปฏิบัติการ | Windows (พัฒนาและใช้งานบน Windows) |

> ถ้าไม่มี VISA driver โปรแกรมจะเปิดไม่ขึ้น และแสดงข้อความ `Could not locate a VISA implementation`

## ติดตั้ง

เปิด Command Prompt หรือ PowerShell ในโฟลเดอร์โปรเจกต์ แล้วรันทีละบรรทัด

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## รันโปรแกรม

```bash
python main.py
```

เมื่อเปิดโปรแกรมแล้ว ให้เลือกพอร์ตของเครื่อง E4980A ที่กล่อง Connection แล้วกด Connect

## ที่เก็บไฟล์ผลการวัด

ไฟล์ Save จะถูกเก็บอัตโนมัติที่

```
<โฟลเดอร์ Documents ของผู้ใช้>\LCR_Metrology_Saves
```

รูปแบบเป็นไฟล์ JSON ตั้งชื่อว่า `YYYYMMDD_HHMMSS_<ชื่อที่ตั้ง>.json`
ส่วนไฟล์ Excel เลือกตำแหน่งบันทึกเองได้ตอน Export

## โครงสร้างโปรเจกต์

```
main.py            จุดเริ่มต้นของโปรแกรม
requirements.txt   รายชื่อไลบรารีที่ต้องติดตั้ง
assets/            ไอคอนและไฟล์สไตล์ (styles.qss)
hardware/          lcr_meter.py  - คลาสสั่งงาน E4980A ผ่าน SCPI/VISA
core/              app_controller.py, measurement_thread.py, correction_thread.py,
                   verify_thread.py, save_manager.py - ตรรกะหลักและ thread การวัด
data/              data_processor.py (สถิติ), file_exporter.py (ส่งออก Excel)
gui/               main_window.py
  panels/          หน้าตั้งค่าและควบคุม (connection, input, advanced, control)
  displays/        กราฟ ตาราง LCD และ log
  dialogs/         หน้าต่างย่อย (save, view save, export Excel, verify)
utils/             helpers.py
```

## สร้างเป็นไฟล์ .exe (ถ้าต้องการ)

ตัวอย่างคำสั่ง (ยังไม่ได้ทดสอบ อาจต้องปรับตามเครื่อง)

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --icon assets/icon.ico --add-data "assets;assets" main.py
```

ไฟล์ที่ได้จะอยู่ในโฟลเดอร์ `dist/`

## หมายเหตุสำหรับผู้พัฒนาต่อ

- ค่าจำกัดต่างๆ (เช่น กระแสสูงสุด 100 mA, แรงดันสูงสุด 15 V เมื่อความถี่เกิน 1 MHz) อ้างอิงจากคู่มือเครื่อง E4980A
  ควรตรวจกับคู่มือก่อนแก้ค่าเหล่านี้
- การเชื่อมต่อ VISA ใช้ `ResourceManager` ตัวเดียวตลอดอายุโปรแกรม (ดูคำอธิบายใน `hardware/lcr_meter.py`)
  ไม่ควรสร้างหรือปิด `ResourceManager` เพิ่มเอง เพราะอาจทำให้ session เดิมใช้ไม่ได้
