# ฟังก์ชันจิปาถะ

from PyQt6.QtWidgets import QComboBox


class NoScrollComboBox(QComboBox):
    """QComboBox ธรรมดาทุกอย่าง ยกเว้นปิดพฤติกรรม "เลื่อนลูกกลิ้งเมาส์ (scroll wheel)
    แล้วเปลี่ยนตัวเลือก" ทิ้ง — ใช้แทน QComboBox ทุกจุดในโปรแกรมนี้

    เหตุผล: พฤติกรรมเริ่มต้นของ Qt คือถ้าเมาส์อยู่เหนือ Dropdown แล้วหมุนล้อเมาส์
    (เช่น ตอนผู้ใช้กำลัง scroll หน้าจอผ่านๆ โดยไม่ได้ตั้งใจจะคลิก dropdown) จะตีความ
    เป็นการเปลี่ยนค่าที่เลือกไว้ทันที ทำให้ค่าที่ตั้งไว้เปลี่ยนไปโดยไม่รู้ตัว

    วิธีแก้: override wheelEvent() แล้วเรียก event.ignore() แทนที่จะประมวลผลเปลี่ยนค่า
    (ไม่เรียก super().wheelEvent()) — เมื่อ widget "ignore" event ไป Qt จะส่ง event
    เดียวกันนี้ต่อขึ้นไปให้ widget แม่ (parent) จัดการเองโดยอัตโนมัติ ผลคือถ้า dropdown
    อยู่ใน QScrollArea การ scroll หน้าจอผ่าน dropdown ยังทำงานได้ปกติ เปลี่ยนแค่ค่าใน
    dropdown จะไม่เปลี่ยนตามอีกต่อไป (ต้องคลิกเลือกเองเท่านั้น)
    """

    def wheelEvent(self, event):
        event.ignore()