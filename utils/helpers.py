# ฟังก์ชันจิปาถะ

import math

from PyQt6.QtWidgets import QComboBox


def truncate_sci(value: float, decimals: int = 2) -> str:
    """แปลงเป็น scientific notation (เช่น '1.23e-09') โดย 'ตัดทิ้ง' ทศนิยมส่วนเกิน
    ไม่ปัดเศษ ต่างจาก f'{value:.2e}' ของ Python ที่ปัดเศษเสมอ (round-half-to-even)

    ใช้กับค่าทางฟิสิกส์ (Cp, Ls, D, Q ฯลฯ) ใน Data Labels ของกราฟ ที่ผู้ใช้ต้องการ
    เห็นค่าดิบที่วัดได้จริงแบบตรงไปตรงมา ไม่อยากให้ตัวเลขท้ายถูกปัดขึ้น/ลงจนดูเหมือน
    ค่าที่เครื่องไม่ได้วัดออกมาจริงๆ
    """
    if value is None or not math.isfinite(value):
        return "-"
    if value == 0:
        return f"{0:.{decimals}f}e+00"

    sign = "-" if value < 0 else ""
    value = abs(value)

    exponent = math.floor(math.log10(value))
    mantissa = value / (10 ** exponent)

    factor = 10 ** decimals
    # ตัดทิ้งตรงๆ (math.trunc) แทนการปัดเศษ — กันปัญหา floating point ด้วย
    # epsilon เล็กน้อยก่อนตัด ไม่งั้นค่าเช่น 1.999999999996 (ที่ควรเป็น 2.00 พอดี)
    # จะโดนตัดเหลือ 1.99 เพราะ floating point representation คลาดเคลื่อนเล็กน้อย
    truncated = math.trunc(mantissa * factor + 1e-9) / factor

    if truncated >= 10:  # เช่น mantissa ตัดแล้วกลายเป็น 10.00 -> ปรับ exponent ขึ้น 1
        truncated /= 10
        exponent += 1

    exp_sign = "+" if exponent >= 0 else "-"
    return f"{sign}{truncated:.{decimals}f}e{exp_sign}{abs(exponent):02d}"


def truncate_fixed(value: float, decimals: int = 2, signed: bool = True) -> str:
    """แปลงเป็นทศนิยมคงที่ (เช่น '+123.45') โดย 'ตัดทิ้ง' ไม่ปัดเศษ — ใช้กับค่า
    PPM Deviation ใน Data Labels ที่ต้องการทศนิยม 2 ตำแหน่งแบบไม่ปัดเศษ"""
    if value is None or not math.isfinite(value):
        return "-"
    factor = 10 ** decimals
    sign = "-" if value < 0 else ""
    truncated = math.trunc(abs(value) * factor + 1e-9) / factor
    prefix = ("+" if signed and value >= 0 else "") + sign
    return f"{prefix}{truncated:.{decimals}f}"


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