# ฟังก์ชันจิปาถะ

import math

from PyQt6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox, QAbstractSpinBox


def _to_decimal(value: float):
    """float -> Decimal ของ |value| โดยกรองสัญญาณรบกวนของ floating point (ระดับ 1e-16)
    ออกด้วยการเก็บ 15 หลักนัยสำคัญก่อน (ความละเอียดที่ float64 รับประกันได้) —
    เช่น ค่าเฉลี่ย 999.9361999999999 (ที่จริงคือ 999.9362) จะถูกอ่านเป็น 999.9362
    แทนที่จะโดนตัดเป็น ...1999"""
    from decimal import Decimal
    return Decimal(f"{abs(float(value)):.15g}")


def _trunc_decimal(value: float, places: int):
    """ตัดทิ้งทศนิยม (ไม่ปัดเศษ) ด้วยเลขฐานสิบแบบ exact — คืน Decimal
    ใช้ repr(value) (สตริงสั้นสุดที่แปลงกลับเป็น float ตัวเดิมได้พอดี) เป็นฐาน
    จึงไม่เกิดปัญหา floating point เช่น 999.89 กลายเป็น 999.8899999
    (วิธีเดิมใช้ epsilon 1e-9 ซึ่งเล็กกว่าความละเอียดของ float เมื่อ mantissa*10^decimals
    มีขนาดประมาณ 1e10) ใช้ได้กับทุกค่าของ places"""
    from decimal import Decimal, ROUND_DOWN
    d = _to_decimal(value)
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_DOWN)


def truncate_sci(value: float, decimals: int = 2) -> str:
    """แปลงเป็น scientific notation (เช่น '1.23e-09') โดย 'ตัดทิ้ง' ทศนิยมส่วนเกิน
    ไม่ปัดเศษ ต่างจาก f'{value:.2e}' ของ Python ที่ปัดเศษเสมอ (round-half-to-even)

    ใช้กับค่าทางฟิสิกส์ (Cp, Ls, D, Q, R, X ฯลฯ) ที่ผู้ใช้ต้องการเห็นค่าดิบที่วัดได้
    จริงแบบตรงไปตรงมา รองรับ decimals กี่หลักก็ได้ (ใช้ Decimal แบบ exact)
    """
    from decimal import Decimal
    if value is None or not math.isfinite(value):
        return "-"
    if value == 0:
        return f"{0:.{decimals}f}e+00"

    sign = "-" if value < 0 else ""
    d = _to_decimal(value)
    exponent = d.adjusted()                      # เลขชี้กำลังฐาน 10 แบบ exact
    mantissa = d.scaleb(-exponent)               # 1 <= mantissa < 10
    truncated = mantissa.quantize(Decimal(1).scaleb(-decimals), rounding="ROUND_DOWN")

    exp_sign = "+" if exponent >= 0 else "-"
    return f"{sign}{truncated:.{decimals}f}e{exp_sign}{abs(exponent):02d}"


def truncate_sig(value: float, sig: int = 9, min_decimals: int = 2, signed: bool = False) -> str:
    """แปลงเป็นทศนิยมคงที่โดยกำหนดจำนวน 'หลักนัยสำคัญ' (significant digits) แบบตัดทิ้ง
    ไม่ปัดเศษ — จำนวนตำแหน่งทศนิยมปรับตามขนาดของค่าอัตโนมัติ จึงรองรับทั้งค่า
    ใหญ่ (68881.62) และค่าเล็กมาก (0.0000527089) โดยความคลาดเคลื่อนสัมพัทธ์
    ไม่เกิน 10^-(sig-1) เสมอ (sig=9 -> < 1e-6 %)

    min_decimals: ทศนิยมขั้นต่ำ เพื่อให้ค่าปกติหน้าตาเดิม (เช่น PPM = 2 ตำแหน่ง)
    signed: True = ใส่ '+' นำหน้าค่าบวก
    """
    if value is None or not math.isfinite(value):
        return "-"
    if value == 0:
        text = f"{0:.{min_decimals}f}"
        return ("+" if signed else "") + text
    mag = _to_decimal(value).adjusted()
    places = max(min_decimals, sig - 1 - mag)
    q = _trunc_decimal(abs(value), places)
    prefix = "-" if value < 0 else ("+" if signed else "")
    return f"{prefix}{q:.{places}f}"


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


def format_short(value: float, acc_percent: float = 0.01, max_decimals: int = 4) -> str:
    """แปลงเป็นตัวเลขทศนิยมคงที่แบบสั้น อ่านง่าย (ไม่ใช้ scientific notation) โดย:
    1. ย่อหน่วยอัตโนมัติด้วยคำนำหน้า SI (k, M, G, m, µ, n, p) แบบเดียวกับแกนกราฟ
       (_EngAxisItem) เพื่อไม่ให้ค่าที่เล็กมากๆ อย่าง 1.23e-9 กลายเป็น 0.00000000123
    2. คำนวณจำนวนตำแหน่งทศนิยมจากสูตร resolution = |ค่าที่ย่อหน่วยแล้ว| x acc_percent
       (ตามที่อาจารย์แนะนำ เช่น 100 pF x 0.01% = 0.01 pF -> ควรโชว์ทศนิยม 2 ตำแหน่ง)
       เพื่อให้ตัวเลขที่โชว์มีความละเอียดพอดีกับค่า ไม่มาก (ยาวเกินจำเป็น) หรือน้อย
       (จนมองไม่เห็นแนวโน้ม) เกินไป
    3. ตัดทิ้ง (ไม่ปัดเศษ) เหมือน truncate_sci/truncate_fixed เพื่อโชว์ค่าที่วัดได้จริง

    ใช้แทน truncate_sci() สำหรับ Data Labels ของกราฟ Live Trend และ Frequency
    Summary — เดิมใช้ scientific notation (เช่น '10.00e-5') ซึ่งอ่านยากและดู
    เป็นตัวเลขที่ไม่คุ้นเคย จึงเปลี่ยนมาใช้ตัวเลขทศนิยมปกติ + หน่วยย่อแทน
    """
    if value is None or not math.isfinite(value):
        return "-"
    if value == 0:
        return "0"

    sign = "-" if value < 0 else ""
    abs_value = abs(value)

    factor, suffix = 1, ''
    for f, s in _ENG_SUFFIXES:
        if abs_value >= f:
            factor, suffix = f, s
            break

    scaled = abs_value / factor
    resolution = scaled * (acc_percent / 100.0)

    if resolution > 0 and math.isfinite(resolution):
        decimals = max(0, min(max_decimals, math.ceil(-math.log10(resolution))))
    else:
        decimals = max_decimals

    fmt_factor = 10 ** decimals
    truncated = math.trunc(scaled * fmt_factor + 1e-9) / fmt_factor

    if decimals == 0:
        return f"{sign}{truncated:.0f}{suffix}"
    return f"{sign}{truncated:.{decimals}f}{suffix}"


# คำนำหน้า SI ที่ใช้ทั้งใน format_short() และแกนกราฟ (_EngAxisItem ในไฟล์กราฟ)
_ENG_SUFFIXES = [
    (1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1, ''),
    (1e-3, 'm'), (1e-6, 'µ'), (1e-9, 'n'), (1e-12, 'p'),
]


def pick_series_unit(values, acc_percent: float = 0.01, max_decimals: int = 4):
    """เลือกหน่วย (SI suffix) + จำนวนทศนิยม 'ร่วมชุดเดียว' สำหรับข้อมูลทั้งเส้น
    (ต่างจาก format_short() ที่คำนวณแยกทีละจุด) เพื่อให้ Data Labels ทุกจุดในกราฟ
    เดียวกันแสดงหน่วยเดียวกันเสมอ สอดคล้องกับแกน Y (ที่เลือกหน่วยเดียวทั่วทั้งแกน
    ด้วย min-based hysteresis เช่นกัน) แทนที่จะกระโดดหน่วยไปมาต่อจุด เช่นเดิมจุดหนึ่ง
    โชว์ '999.96' อีกจุดถัดไปกลายเป็น '1.0000k' ทั้งที่อยู่กราฟเดียวกัน อ่านแล้วงง

    คืนค่า (factor, suffix, decimals) ไปใช้กับ format_with_unit() ต่อ
    """
    finite = [v for v in values if v is not None and math.isfinite(v)]
    nonzero = [abs(v) for v in finite if v != 0]
    if not nonzero:
        return 1, '', 2

    max_abs = max(nonzero)
    factor, suffix, tier_idx = 1, '', 3  # index 3 = (1, '') ในตาราง _ENG_SUFFIXES
    for i, (f, s) in enumerate(_ENG_SUFFIXES):
        if max_abs >= f:
            factor, suffix, tier_idx = f, s, i
            break

    # เหมือนแกน Y: ถ้าย่อหน่วยแล้วค่าที่เล็กที่สุดในชุดเหลือน้อยกว่า 1 (กลายเป็นเศษส่วน
    # อ่านยากแบบ '0.99998k') ให้ถอยกลับไปใช้หน่วยที่เล็กลงเรื่อยๆ จนทุกจุดแสดงเป็น
    # เลขเต็ม (>= 1) ในหน่วยนั้น
    min_abs = min(nonzero)
    while tier_idx < len(_ENG_SUFFIXES) - 1 and factor > 0 and (min_abs / factor) < 1:
        tier_idx += 1
        factor, suffix = _ENG_SUFFIXES[tier_idx]

    # จำนวนทศนิยมคิดจาก resolution ของค่าที่เล็กที่สุดในชุด (จุดที่ต้องการความละเอียด
    # มากที่สุดเพื่อให้ยังมองเห็นแนวโน้ม) ตามสูตร resolution = ค่าที่ย่อหน่วยแล้ว x acc_percent
    resolution = (min_abs / factor) * (acc_percent / 100.0)
    if resolution > 0 and math.isfinite(resolution):
        decimals = max(0, min(max_decimals, math.ceil(-math.log10(resolution))))
    else:
        decimals = max_decimals

    return factor, suffix, decimals


def format_with_unit(value: float, factor: float, suffix: str, decimals: int, show_suffix: bool = True) -> str:
    """แปลงค่าเดียวเป็น string โดยใช้ (factor, suffix, decimals) ที่คำนวณไว้ล่วงหน้า
    จาก pick_series_unit() (หน่วยเดียวกันทั้งชุดข้อมูล) ตัดเลขทิ้ง (ไม่ปัดเศษ) เหมือน
    format_short()/truncate_sci() เพื่อโชว์ค่าที่วัดได้จริง

    show_suffix=False: ไม่ต่อท้ายด้วยตัวอักษรหน่วย (k, m, µ, n, p ฯลฯ) เอาไว้ใช้กับ
    Data Labels ที่ต้องการโชว์แค่ตัวเลขล้วนๆ (ตัวเลขยังคงถูกย่อ/ปัดตามหน่วยเดิม
    เพื่อให้ความยาวสั้นสอดคล้องกับแกน Y เพียงแต่ไม่ต่อท้ายตัวอักษรหน่วยเฉยๆ)"""
    if value is None or not math.isfinite(value):
        return "-"
    display_suffix = suffix if show_suffix else ""
    if value == 0:
        return f"{0:.{decimals}f}{display_suffix}" if decimals else f"0{display_suffix}"

    sign = "-" if value < 0 else ""
    scaled = abs(value) / factor
    fmt_factor = 10 ** decimals
    truncated = math.trunc(scaled * fmt_factor + 1e-9) / fmt_factor

    if decimals == 0:
        return f"{sign}{truncated:.0f}{display_suffix}"
    return f"{sign}{truncated:.{decimals}f}{display_suffix}"


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


class NoScrollSpinBox(QSpinBox):
    """QSpinBox ธรรมดาทุกอย่าง ยกเว้น:
    1. ปิดพฤติกรรม "เลื่อนลูกกลิ้งเมาส์ (scroll wheel) แล้วเปลี่ยนค่าตัวเลข" ทิ้ง
    2. ซ่อนปุ่ม +/- (ลูกศรขึ้น-ลง) ทิ้ง — บังคับให้ผู้ใช้พิมพ์ค่าเองเท่านั้น
    ใช้แทน QSpinBox ทุกจุดในโปรแกรมนี้

    เหตุผลข้อ 1 และวิธีแก้เหมือนกับ NoScrollComboBox ด้านบน: override wheelEvent()
    แล้วเรียก event.ignore() แทนที่จะเพิ่ม/ลดค่า

    เหตุผลข้อ 2: ปุ่ม +/- กดทีละ 1 หน่วย ไม่เหมาะกับการตั้งค่าที่ต้องพิมพ์ตัวเลข
    เฉพาะเจาะจง (เช่น จำนวนครั้งวัด) — ตัดออกเพื่อให้ผู้ใช้พิมพ์ค่าที่ต้องการได้ตรงๆ
    ทันที ไม่ต้องกดปุ่มไล่ทีละ 1 (setButtonSymbols(NoButtons) ไม่ตัดความสามารถ
    พิมพ์ค่าเอง/ใช้ปุ่มลูกศรบนคีย์บอร์ดออก ยังใช้งานได้ปกติ)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def wheelEvent(self, event):
        event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox ธรรมดาทุกอย่าง ยกเว้นปิดพฤติกรรมเลื่อนลูกกลิ้งเมาส์แล้วเปลี่ยนค่า
    และซ่อนปุ่ม +/- ทิ้ง (เหตุผลและวิธีแก้เหมือนกับ NoScrollSpinBox ด้านบน)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    def wheelEvent(self, event):
        event.ignore()