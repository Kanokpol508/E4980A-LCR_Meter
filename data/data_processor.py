# คำนวณสถิติสำหรับทุกโหมดการวัด (SINGLE / SWEEP / LIST)
# statistics_table.py เรียกใช้ฟังก์ชันเหล่านี้โดยตรง — ไม่มีสูตรในฝั่ง GUI

import math
import statistics


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
    sd    = statistics.stdev(values) if len(values) > 1 else 0.0

    return {
        'mean':       mean,
        'sd':         sd,
        'min':        min(values),
        'max':        max(values),
        'rsd_pct':    (sd / abs(mean) * 100) if mean != 0 else None,
        'ppm':        _calc_ppm(mean, ref),
        'type_a_ppm': _calc_type_a_ppm(values),
    }


# ==========================================================
# ฟังก์ชัน format (Private helper)
# ==========================================================

def _fmt(val, sci: bool = True) -> str:
    if val is None:
        return "-"
    return f"{val:.5e}" if sci else f"{val:.4f}"


def _fmt_ppm(val) -> str:
    if val is None:
        return "-"
    return f"{val:+.2f}"


# ==========================================================
# SINGLE mode
# ==========================================================

def calculate_single_stats(raw_records: list) -> dict | None:
    """
    SINGLE mode — คำนวณสถิติ Overall ของทั้ง session
    raw_records: [{'freq': <fixed Hz>, 'primary': float, 'secondary': float}, ...]

    คืน dict เดี่ยว (1 session = 1 แถว) หรือ None ถ้าไม่มีข้อมูล
    รวม Frequency ที่ใช้วัดด้วย (ดึงจาก record แรก)

    Keys ที่คืน:
        freq, n,
        pri_mean, pri_sd, pri_min, pri_max, pri_rsd_pct, pri_type_a_ppm,
        sec_mean, sec_sd, sec_min, sec_max, sec_rsd_pct, sec_type_a_ppm
    """
    if not raw_records:
        return None

    pri_vals = [r['primary']   for r in raw_records if r.get('primary')   is not None]
    sec_vals = [r['secondary'] for r in raw_records if r.get('secondary') is not None]

    if not pri_vals:
        return None

    pri = _calc_stats_block(pri_vals)
    sec = _calc_stats_block(sec_vals)

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
        'pri_type_a_ppm': pri['type_a_ppm'],

        'sec_mean':       sec['mean'],
        'sec_sd':         sec['sd'],
        'sec_min':        sec['min'],
        'sec_max':        sec['max'],
        'sec_rsd_pct':    sec['rsd_pct'],
        'sec_type_a_ppm': sec['type_a_ppm'],
    }


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
        'pri_type_a_ppm': _fmt_ppm(stat['pri_type_a_ppm']),
        'sec_mean':       _fmt(stat['sec_mean']),
        'sec_sd':         _fmt(stat['sec_sd']),
        'sec_min':        _fmt(stat['sec_min']),
        'sec_max':        _fmt(stat['sec_max']),
        'sec_rsd_pct':    _fmt(stat['sec_rsd_pct'],    sci=False),
        'sec_type_a_ppm': _fmt_ppm(stat['sec_type_a_ppm']),
    }


# ==========================================================
# SWEEP mode
# ==========================================================

def calculate_sweep_rows(raw_records: list) -> list:
    """
    SWEEP mode — ไม่มีการวัดซ้ำ แต่ละ record คือ 1 ความถี่ × 1 ครั้ง
    คืน list ของ dict เรียงตามลำดับที่วัด พร้อมแสดงเป็น row ในตาราง

    Keys ที่คืน: freq, primary, secondary
    """
    return [
        {
            'freq':      r.get('freq', 0),
            'primary':   r.get('primary'),
            'secondary': r.get('secondary'),
        }
        for r in raw_records
    ]


def format_sweep_row_for_table(row: dict) -> dict:
    """แปลงผลจาก calculate_sweep_rows() เป็น string"""
    return {
        'freq':      f"{row['freq']:.2f}",
        'primary':   _fmt(row['primary']),
        'secondary': _fmt(row['secondary']),
    }


# ==========================================================
# LIST mode
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