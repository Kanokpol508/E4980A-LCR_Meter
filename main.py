# ไฟล์จุดเริ่มต้นรันโปรแกรม (Entry Point)


import sys
from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow

def main():
    # สร้างแอปพลิเคชัน PyQt6
    app = QApplication(sys.argv)
    
    # กำหนดสไตล์พื้นฐานให้ดูทันสมัยขึ้น (Fusion Style)
    app.setStyle("Fusion")
    
    # สร้างและแสดงหน้าต่างหลัก
    window = MainWindow()
    window.show()
    
    # รันลูปของแอปพลิเคชัน
    sys.exit(app.exec())

if __name__ == "__main__":
    main()