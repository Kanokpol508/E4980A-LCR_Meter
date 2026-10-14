import os
import sys
import ctypes

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from gui.main_window import MainWindow
from core.app_controller import AppController


def resource_path(rel_path: str) -> str:
    """หาพาธไฟล์ได้ทั้งตอนรันจากโค้ดและตอนเป็น exe (PyInstaller)"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel_path)


def main():
    # ให้ Taskbar แสดงไอคอนของโปรแกรม ไม่ใช่ไอคอน Python (เฉพาะ Windows)
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "lcr.e4980a.meter"
        )

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("assets/icon.ico")))

    # โหลดสไตล์ (ถ้าไฟล์เดิมของคุณโหลด styles.qss ที่อื่นอยู่แล้ว ให้ลบบล็อกนี้)
    qss_path = resource_path("assets/styles.qss")
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    controller = AppController(window)  # เก็บไว้ในตัวแปรไม่ให้ถูกเก็บขยะ
    window.showMaximized()              # เปิดหน้าต่างโปรแกรมแบบเต็มจอ

    sys.exit(app.exec())


if __name__ == "__main__":
    main()