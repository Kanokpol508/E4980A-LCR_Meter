# ไฟล์จุดเริ่มต้นรันโปรแกรม (Entry Point)


import sys
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow
from core.app_controller import AppController

def main():
    # 1. สร้างแอปพลิเคชัน PyQt
    app = QApplication(sys.argv)
    
    # 2. เพิ่มโค้ดโหลดไฟล์ QSS Theme ตรงนี้
    try:
        with open("assets/styles.qss", "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    except FileNotFoundError:
        print("⚠️ คำเตือน: ไม่พบไฟล์ assets/styles.qss โปรแกรมจะใช้ธีมพื้นฐานแทน")
    
    # 3. สร้างหน้าต่าง GUI เปล่าๆ ขึ้นมา (View)
    window = MainWindow()
    
    # 4. สร้าง Controller แล้วมอบหมายให้เข้าไปควบคุมหน้าต่าง (Controller -> View)
    controller = AppController(window)
    
    # 5. แสดงหน้าจอและรันโปรแกรม
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()