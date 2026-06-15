# ไฟล์จุดเริ่มต้นรันโปรแกรม (Entry Point)


import sys
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow
from core.app_controller import AppController

def main():
    # 1. สร้างแอปพลิเคชัน PyQt
    app = QApplication(sys.argv)
    
    # 2. สร้างหน้าต่าง GUI เปล่าๆ ขึ้นมา (View)
    window = MainWindow()
    
    # 3. สร้าง Controller แล้วมอบหมายให้เข้าไปควบคุมหน้าต่าง (Controller -> View)
    controller = AppController(window)
    
    # 4. แสดงหน้าจอและรันโปรแกรม
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()