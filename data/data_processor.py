# คำนวณสถิติสำหรับทุกโหมดการวัด (SINGLE / SWEEP / LIST)
# statistics_table.py เรียกใช้ฟังก์ชันเหล่านี้โดยตรง — ไม่มีสูตรในฝั่ง GUI

import math
import statistics

from utils.helpers import truncate_sci


# ==========================================================
# ฟังก์ชันช่วยคำนวณ (Private helpers)
# ==========================================================

def _calc_ppm(mean_value: float, ref_value) -> float | None:
    """
    PPM Deviation = (Mean - Ref) / |Ref| × 1,000,000
    คืน None ถ้าไม่มีค่าอ้างอิง หรือ Ref == 0
    """
    if ref_value is None:
        return None
    try:
        ref_value = float(ref_value)
    except (TypeError, ValueError):
        return None
    if ref_value == 0:
        return None
    return (mean_value - ref_value) / abs(ref_value) * 1_000_000


def _calc_type_a_ppm(values: list) -> float | None:
    """
    Type A Uncertainty (ppm) = (SD / √N) / |Mean| × 1,000,000
    วัดความไม่แน่นอนจากการวัดซ้ำ — ต้องการ N ≥ 2
    คืน None ถ้า N < 2 หรือ Mean == 0
    """
    n = len(values)
    if n < 2:
        return None
    try:
        sd   = statistics.stdev(values)     # sample SD (ddof=1)
        mean = statistics.fmean(values)
        if mean == 0:
            return None
        return (sd / math.sqrt(n)) / abs(mean) * 1_000_000
    except Exception:
        return None


def _calc_stats_block(values: list, ref=None) -> dict:
    """
    คำนวณ block สถิติมาตรฐานจาก list ของค่าดิบ
    คืน dict: mean, sd, min, max, rsd_pct, ppm, type_a_ppm
    ถ้า values ว่างจะคืน None ทุกฟิลด์
    """
    if not values:
        return {k: None for k in ('mean', 'sd', 'min', 'max', 'rsd_pct', 'ppm', 'type_a_ppm')}

    mean  = statistics.fmean(values)
    n     = len(values)
    sd    = statistics.stdev(values) if n > 1 else 0.0

    return {
        'mean':       mean,
        'sd':         sd,
        'min':        min(values),
        'max':        max(values),
        # N < 2: ไม่มีข้อมูลพอจะคำนวณการกระจายตัวจริง (SD ถูกบังคับ = 0.0 ด้านบน)
        # แสดง '-' แทน 0.00 ป้องกันเข้าใจผิดว่า "นิ่งมาก" ทั้งที่วัดครั้งเดียว
        'rsd_pct':    (sd / abs(mean) * 100) if (n > 1 and mean != 0) else None,
        'ppm':        _calc_ppm(mean, ref),
        'type_a_ppm': _calc_type_a_ppm(values),
    }


# ==========================================================
# ฟังก์ชัน format (Private helper)
# ==========================================================

def _fmt(val, sci: bool = True) -> str:
    if val is None:
        return "-"
    # [แก้ไข] เดิมใช้ f"{val:.5e}" ซึ่งปัดเศษ (round) และเก็บแค่ 5 ตำแหน่ง — ตอนนี้ใช้
    # truncate_sci() แทน (ตัดทิ้ง ไม่ปัดเศษ) พร้อมเพิ่มเป็น 9 ตำแหน่ง ให้เป็นหลักการ
    # เดียวกับ Raw Data Table (utils/helpers.RAW_VALUE_DECIMALS ใน raw_data_table.py)
    # เพราะค่าพวกนี้ (Mean, SD, Min, Max) ถูกใช้ทั้งในตารางสถิติบนหน้าจอ และ export
    # ออกไปเป็นรายงาน Excel จริง จึงควรแม่นยำ/สม่ำเสมอเท่ากับ Raw Data
    return truncate_sci(val, 9) if sci else f"{val:.4f}"


def _fmt_ppm(val) -> str:
    if val is None:
        return "-"
    return f"{val:+.2f}"


# ==========================================================
# SINGLE mode
# ==========================================================

def calculate_single_stats(raw_records: list, pri_ref=None, sec_ref=None) -> dict | None:
    """
    SINGLE mode — คำนวณสถิติ Overall ของทั้ง session
    raw_records: [{'freq': <fixed Hz>, 'primary': float, 'secondary': float}, ...]
    pri_ref / sec_ref: ค่าอ้างอิงสำหรับคำนวณ PPM Deviation (None = ไม่คำนวณ)

    คืน dict เดี่ยว (1 session = 1 แถว) หรือ None ถ้าไม่มีข้อมูล
    รวม Frequency ที่ใช้วัดด้วย (ดึงจาก record แรก)

    Keys ที่คืน:
        freq, n,
        pri_mean, pri_sd, pri_min, pri_max, pri_rsd_pct, pri_ppm, pri_type_a_ppm,
        sec_mean, sec_sd, sec_min, sec_max, sec_rsd_pct, sec_ppm, sec_type_a_ppm
    """
    if not raw_records:
        return None

    pri_vals = [r['primary']   for r in raw_records if r.get('primary')   is not None]
    sec_vals = [r['secondary'] for r in raw_records if r.get('secondary') is not None]

    if not pri_vals:
        return None

    pri = _calc_stats_block(pri_vals, ref=pri_ref)
    sec = _calc_stats_block(sec_vals, ref=sec_ref)

    # ดึงความถี่จาก record แรก (SINGLE ใช้ความถี่เดียวตลอด session)
    freq = raw_records[0].get('freq', None)

    return {
        'freq': freq,
        'n':    len(pri_vals),

        'pri_mean':       pri['mean'],
        'pri_sd':         pri['sd'],
        'pri_min':        pri['min'],
        'pri_max':        pri['max'],
        'pri_rsd_pct':    pri['rsd_pct'],
        'pri_ppm':        pri['ppm'],
        'pri_type_a_ppm': pri['type_a_ppm'],

        'sec_mean':       sec['mean'],
        'sec_sd':         sec['sd'],
        'sec_min':        sec['min'],
        'sec_max':        sec['max'],
        'sec_rsd_pct':    sec['rsd_pct'],
        'sec_ppm':        sec['ppm'],
        'sec_type_a_ppm': sec['type_a_ppm'],
    }


def calculate_single_stats_per_run(run_groups: list, pri_ref=None, sec_ref=None) -> list:
    """
    [NEW] SINGLE mode — คำนวณสถิติแยกทีละ "รอบ" (1 ครั้งกด Start = 1 รอบ = 1 แถวในตาราง)
    แทนที่จะรวมทุกรอบเป็นแถวเดียว (calculate_single_stats() เดิม) — เหตุผล: ถึงแม้ทุกรอบ
    จะวัดที่ความถี่/เงื่อนไขเดียวกัน (ถูกล็อกไว้ระหว่างมีข้อมูลค้าง) การแยกแถวช่วยให้เห็น
    ความคลาดเคลื่อนระหว่างรอบ (run-to-run) ที่การรวมกันเป็นก้อนเดียวจะกลบไป (เช่น SD
    ที่โชว์จะเป็น SD รวมของทุกรอบ ไม่ใช่ SD ภายในรอบเดียว)

    run_groups: [[{'freq':.., 'primary':.., 'secondary':..}, ...], ...]
                แต่ละ sub-list คือค่าดิบของ 1 รอบ (ตามลำดับที่วัดจริง)
    pri_ref / sec_ref: ค่าอ้างอิงสำหรับคำนวณ PPM Deviation (None = ไม่คำนวณ) — ใช้ค่าเดียวกัน
                        กับทุกรอบ เพราะ Reference ไม่ได้ผูกกับรอบใดรอบหนึ่งโดยเฉพาะ

    คืน list ของ dict (โครงสร้างเดียวกับ calculate_single_stats()) เรียงตามลำดับรอบที่วัดจริง
    รอบที่ไม่มีข้อมูล (list ว่าง) จะถูกข้ามไปเงียบๆ
    """
    results = []
    for recs in run_groups:
        stat = calculate_single_stats(recs, pri_ref=pri_ref, sec_ref=sec_ref)
        if stat is not None:
            results.append(stat)
    return results


def format_single_row_for_table(stat: dict) -> dict:
    """แปลงผลจาก calculate_single_stats() เป็น string พร้อมแสดงใน QTableWidget"""
    freq_val = stat.get('freq')
    freq_str = f"{freq_val:.2f}" if freq_val is not None else "-"

    return {
        'freq':           freq_str,
        'n':              str(stat['n']),
        'pri_mean':       _fmt(stat['pri_mean']),
        'pri_sd':         _fmt(stat['pri_sd']),
        'pri_min':        _fmt(stat['pri_min']),
        'pri_max':        _fmt(stat['pri_max']),
        'pri_rsd_pct':    _fmt(stat['pri_rsd_pct'],    sci=False),
        'pri_ppm':        _fmt_ppm(stat['pri_ppm']),
        'pri_type_a_ppm': _fmt_ppm(stat['pri_type_a_ppm']),
        'sec_mean':       _fmt(stat['sec_mean']),
        'sec_sd':         _fmt(stat['sec_sd']),
        'sec_min':        _fmt(stat['sec_min']),
        'sec_max':        _fmt(stat['sec_max']),
        'sec_rsd_pct':    _fmt(stat['sec_rsd_pct'],    sci=False),
        'sec_ppm':        _fmt_ppm(stat['sec_ppm']),
        'sec_type_a_ppm': _fmt_ppm(stat['sec_type_a_ppm']),
    }


# ==========================================================
# LIST mode (SWEEP ใช้ฟังก์ชันชุดเดียวกันนี้ทั้งหมด)
# ==========================================================

def calculate_frequency_stats(raw_records: list, pri_ref=None, sec_ref=None) -> list:
    """
    LIST mode — จัดกลุ่มตามความถี่ แล้วคำนวณสถิติเต็มรูปแบบต่อกลุ่ม
    raw_records: [{'freq': Hz, 'primary': float, 'secondary': float}, ...]

    คืน list ของ dict เรียงตาม freq จากน้อยไปมาก

    Keys ที่คืน:
        freq, n_samples,
        pri_mean, pri_sd, pri_min, pri_max, pri_rsd_pct, pri_ppm, pri_type_a_ppm,
        sec_mean, sec_sd, sec_min, sec_max, sec_rsd_pct, sec_ppm, sec_type_a_ppm
    """
    if not raw_records:
        return []

    # จัดกลุ่มตามความถี่ (ปัดเศษกัน float drift)
    groups: dict = {}
    for rec in raw_records:
        freq = rec.get('freq')
        if freq is None:
            continue
        key = round(float(freq), 6)
        groups.setdefault(key, []).append(rec)

    results = []
    for freq_key in sorted(groups.keys()):
        recs = groups[freq_key]
        pri_vals = [r['primary']   for r in recs if r.get('primary')   is not None]
        sec_vals = [r['secondary'] for r in recs if r.get('secondary') is not None]

        pri = _calc_stats_block(pri_vals, ref=pri_ref)
        sec = _calc_stats_block(sec_vals, ref=sec_ref)

        results.append({
            'freq':      freq_key,
            'n_samples': len(recs),

            'pri_mean':       pri['mean'],
            'pri_sd':         pri['sd'],
            'pri_min':        pri['min'],
            'pri_max':        pri['max'],
            'pri_rsd_pct':    pri['rsd_pct'],
            'pri_ppm':        pri['ppm'],
            'pri_type_a_ppm': pri['type_a_ppm'],

            'sec_mean':       sec['mean'],
            'sec_sd':         sec['sd'],
            'sec_min':        sec['min'],
            'sec_max':        sec['max'],
            'sec_rsd_pct':    sec['rsd_pct'],
            'sec_ppm':        sec['ppm'],
            'sec_type_a_ppm': sec['type_a_ppm'],
        })

    return results


# ==========================================================
# [NEW] Incremental accumulator สำหรับ LIST/SWEEP mode
# ==========================================================
#
# ปัญหาเดิม: calculate_frequency_stats() ต้องได้รับ raw_records ครบทุกจุดแล้ว "กวาดคำนวณ
# ใหม่ทั้งหมด" ทุกครั้งที่ถูกเรียก — ถ้าเรียกทุกครั้งที่มีจุดข้อมูลใหม่ 1 จุดเข้ามา (ตามที่
# core/app_controller.py เคยทำ) ต้นทุนต่อจุดจะโตขึ้นเรื่อยๆ ตามจำนวนจุดสะสม (O(n) ต่อจุด
# รวมทั้งสวีปเป็น O(n²)) ทำให้สวีปยาวๆ (หลายพัน/หมื่นจุด, วัดต่อเนื่องหลายชั่วโมง) โปรแกรมค้าง
#
# FrequencyStatsAccumulator แก้ปัญหานี้ด้วยการ "สะสม" mean/variance/min/max แบบ incremental
# ต่อความถี่ (Welford's online algorithm) — รับจุดข้อมูลใหม่ 1 จุดด้วยต้นทุนคงที่ O(1) แทนที่
# จะต้องมีค่าดิบทั้งหมดในมือแล้วคำนวณใหม่ ผลลัพธ์ที่ได้จาก get_stats() ตรงกับผลลัพธ์จาก
# calculate_frequency_stats(raw_records) ทุกประการ (สูตรคณิตศาสตร์เดียวกัน คนละวิธีคำนวณ)
# ไม่ใช่ค่าประมาณ — ใช้แทนกันได้อย่างปลอดภัย
class FrequencyStatsAccumulator:
    """สะสมสถิติ Mean/SD/Min/Max ต่อความถี่แบบ incremental (ดู docstring หัวข้อด้านบน)
    ใช้แทน calculate_frequency_stats() เมื่อต้องอัปเดตบ่อยๆ ระหว่างวัด (LIST/SWEEP mode)"""

    def __init__(self):
        self._groups: dict = {}   # freq_key(float, ปัดเศษ 6 ตำแหน่ง) -> dict สถานะสะสม

    def clear(self):
        """ล้างค่าสะสมทั้งหมด (เรียกตอนเริ่ม session ใหม่ / Clear Graph)"""
        self._groups.clear()

    def add(self, freq, primary, secondary):
        """เพิ่มจุดข้อมูลใหม่ 1 จุด — ต้นทุนคงที่ O(1) ไม่ขึ้นกับจำนวนจุดที่สะสมไว้ก่อนหน้า"""
        if freq is None:
            return
        key = round(float(freq), 6)   # ปัดเศษกัน float drift แบบเดียวกับ calculate_frequency_stats()
        g = self._groups.get(key)
        if g is None:
            g = {
                'pri_n': 0, 'pri_mean': 0.0, 'pri_m2': 0.0, 'pri_min': None, 'pri_max': None,
                'sec_n': 0, 'sec_mean': 0.0, 'sec_m2': 0.0, 'sec_min': None, 'sec_max': None,
                'n_samples': 0,
            }
            self._groups[key] = g

        g['n_samples'] += 1

        if primary is not None:
            g['pri_n'] += 1
            delta = primary - g['pri_mean']
            g['pri_mean'] += delta / g['pri_n']
            g['pri_m2'] += delta * (primary - g['pri_mean'])   # Welford's algorithm
            g['pri_min'] = primary if g['pri_min'] is None else min(g['pri_min'], primary)
            g['pri_max'] = primary if g['pri_max'] is None else max(g['pri_max'], primary)

        if secondary is not None:
            g['sec_n'] += 1
            delta = secondary - g['sec_mean']
            g['sec_mean'] += delta / g['sec_n']
            g['sec_m2'] += delta * (secondary - g['sec_mean'])
            g['sec_min'] = secondary if g['sec_min'] is None else min(g['sec_min'], secondary)
            g['sec_max'] = secondary if g['sec_max'] is None else max(g['sec_max'], secondary)

    @staticmethod
    def _block_from_accum(n: int, mean: float, m2: float, vmin, vmax, ref) -> dict:
        """แปลงสถานะสะสม (n, mean, M2) ของ 1 พารามิเตอร์ ให้เป็น block เดียวกับ
        _calc_stats_block() — สูตรเดียวกันทุกประการ (sample SD, ddof=1) แค่คำนวณจาก
        ตัวสะสมแทนการวนค่าดิบทั้งหมด"""
        if n == 0:
            return {k: None for k in ('mean', 'sd', 'min', 'max', 'rsd_pct', 'ppm', 'type_a_ppm')}
        sd = math.sqrt(m2 / (n - 1)) if n > 1 else 0.0
        return {
            'mean':       mean,
            'sd':         sd,
            'min':        vmin,
            'max':        vmax,
            'rsd_pct':    (sd / abs(mean) * 100) if (n > 1 and mean != 0) else None,
            'ppm':        _calc_ppm(mean, ref),
            'type_a_ppm': ((sd / math.sqrt(n)) / abs(mean) * 1_000_000) if (n >= 2 and mean != 0) else None,
        }

    def get_stats(self, pri_ref=None, sec_ref=None) -> list:
        """คืนผลลัพธ์รูปแบบเดียวกับ calculate_frequency_stats() ทุกประการ
        (list ของ dict เรียงตาม freq จากน้อยไปมาก)"""
        results = []
        for freq_key in sorted(self._groups.keys()):
            g = self._groups[freq_key]
            pri = self._block_from_accum(g['pri_n'], g['pri_mean'], g['pri_m2'], g['pri_min'], g['pri_max'], pri_ref)
            sec = self._block_from_accum(g['sec_n'], g['sec_mean'], g['sec_m2'], g['sec_min'], g['sec_max'], sec_ref)
            results.append({
                'freq':      freq_key,
                'n_samples': g['n_samples'],

                'pri_mean':       pri['mean'],
                'pri_sd':         pri['sd'],
                'pri_min':        pri['min'],
                'pri_max':        pri['max'],
                'pri_rsd_pct':    pri['rsd_pct'],
                'pri_ppm':        pri['ppm'],
                'pri_type_a_ppm': pri['type_a_ppm'],

                'sec_mean':       sec['mean'],
                'sec_sd':         sec['sd'],
                'sec_min':        sec['min'],
                'sec_max':        sec['max'],
                'sec_rsd_pct':    sec['rsd_pct'],
                'sec_ppm':        sec['ppm'],
                'sec_type_a_ppm': sec['type_a_ppm'],
            })
        return results

    def rebuild_from_records(self, raw_records: list):
        """ล้างค่าสะสมเดิมแล้วโหลดค่าดิบทั้งหมดเข้าสะสมใหม่ตั้งแต่ต้น — ใช้ตอนโหลด Session
        เก่าจากไฟล์ (view_save_dialog) ที่มีค่าดิบครบอยู่แล้วแต่ยังไม่เคยผ่านตัวสะสมนี้"""
        self.clear()
        for rec in raw_records:
            self.add(rec.get('freq'), rec.get('primary'), rec.get('secondary'))


def format_stats_row_for_table(stat_row: dict) -> dict:
    """แปลงผลจาก calculate_frequency_stats() เป็น string"""
    return {
        'freq':           f"{stat_row['freq']:.2f}",
        'n_samples':      str(stat_row['n_samples']),

        'pri_mean':       _fmt(stat_row['pri_mean']),
        'pri_sd':         _fmt(stat_row['pri_sd']),
        'pri_min':        _fmt(stat_row['pri_min']),
        'pri_max':        _fmt(stat_row['pri_max']),
        'pri_rsd_pct':    _fmt(stat_row['pri_rsd_pct'],    sci=False),
        'pri_ppm':        _fmt_ppm(stat_row['pri_ppm']),
        'pri_type_a_ppm': _fmt_ppm(stat_row['pri_type_a_ppm']),

        'sec_mean':       _fmt(stat_row['sec_mean']),
        'sec_sd':         _fmt(stat_row['sec_sd']),
        'sec_min':        _fmt(stat_row['sec_min']),
        'sec_max':        _fmt(stat_row['sec_max']),
        'sec_rsd_pct':    _fmt(stat_row['sec_rsd_pct'],    sci=False),
        'sec_ppm':        _fmt_ppm(stat_row['sec_ppm']),
        'sec_type_a_ppm': _fmt_ppm(stat_row['sec_type_a_ppm']),
    }