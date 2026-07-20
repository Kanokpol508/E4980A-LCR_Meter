# ไฟล์จุดเริ่มต้นรันโปรแกรม (Entry Point)

import sys
import os
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow
from core.app_controller import AppController

def main():
    # 1. สร้างแอปพลิเคชัน PyQt
    app = QApplication(sys.argv)
    
    # 2. โหลดไฟล์ QSS Theme โดยใช้ Path อ้างอิงจากตำแหน่งไฟล์ main.py (Absolute Path)
    # ป้องกันบั๊กหาไฟล์ไม่เจอเมื่อรันโปรแกรมจากโฟลเดอร์อื่น หรือเมื่อนำไปแพ็กเป็น .exe
    base_dir = os.path.dirname(os.path.abspath(__file__))
    qss_path = os.path.join(base_dir, "assets", "styles.qss")
    
    try:
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print(f"⚠️ คำเตือน: ไม่พบไฟล์ {qss_path} โปรแกรมจะใช้ธีมพื้นฐานแทน")
    
    # 3. สร้างหน้าต่าง GUI เปล่าๆ ขึ้นมา (View)
    window = MainWindow()
    
    # 4. สร้าง Controller แล้วมอบหมายให้เข้าไปควบคุมหน้าต่าง (Controller -> View)
    controller = AppController(window)
    
    # ตัดการเชื่อมต่อเครื่อง LCR Meter ให้เรียบร้อยก่อนโปรแกรมปิด
    # ป้องกัน VISA session ค้างที่เครื่องหลังปิดโปรแกรมกะทันหัน
    app.aboutToQuit.connect(lambda: controller.lcr.disconnect() if controller.lcr.is_connected else None)

    # 5. แสดงหน้าจอและรันโปรแกรม
    window.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()