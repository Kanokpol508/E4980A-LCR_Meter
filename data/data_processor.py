# คำนวณสถิติ (Mean/SD/Min/Max/PPM) จากข้อมูลดิบที่วัดได้ในโหมด List

import statistics


def calculate_frequency_stats(raw_records: list, pri_ref=None, sec_ref=None) -> list:
    """
    รับ raw_records ที่มาจากโหมด List (list ของ dict):
        [{'freq': 100.0, 'sample_index': 1, 'primary': 1.23e-9, 'secondary': 0.001}, ...]

    รวมกลุ่มตามความถี่ (freq) เดียวกัน แล้วคำนวณสถิติของแต่ละความถี่:
        - N (จำนวนตัวอย่าง)
        - Mean, Std Dev, Min, Max  (ของทั้ง Primary และ Secondary)
        - %RSD  (Std Dev / Mean * 100 -> ความเสถียรเชิงสัมพัทธ์)
        - PPM Deviation จาก pri_ref / sec_ref (ถ้าไม่ระบุ -> เป็น None แสดงเป็น "-")

    คืนค่าเป็น list ของ dict เรียงตามความถี่จากน้อยไปมาก พร้อมใช้แสดงในตาราง
    หรือส่งต่อให้ file_exporter.py เขียนเป็น Excel ได้ทันที
    """
    if not raw_records:
        return []

    # ==========================================================
    # 1. จัดกลุ่มข้อมูลดิบตามความถี่ (ปัดเศษเล็กน้อยกันปัญหา float ไม่เท่ากันเป๊ะ)
    # ==========================================================
    groups = {}
    for rec in raw_records:
        freq = rec.get('freq')
        if freq is None:
            continue
        freq_key = round(float(freq), 6)
        groups.setdefault(freq_key, []).append(rec)

    # ==========================================================
    # 2. คำนวณสถิติของแต่ละกลุ่มความถี่
    # ==========================================================
    results = []
    for freq_key in sorted(groups.keys()):
        records = groups[freq_key]

        pri_values = [r['primary'] for r in records if r.get('primary') is not None]
        sec_values = [r['secondary'] for r in records if r.get('secondary') is not None]

        stat_row = {
            'freq': freq_key,
            'n_samples': len(records),

            'pri_mean': None, 'pri_sd': None, 'pri_min': None, 'pri_max': None,
            'pri_rsd_pct': None, 'pri_ppm': None,

            'sec_mean': None, 'sec_sd': None, 'sec_min': None, 'sec_max': None,
            'sec_rsd_pct': None, 'sec_ppm': None,
        }

        if pri_values:
            p_mean = statistics.fmean(pri_values)
            p_sd = statistics.stdev(pri_values) if len(pri_values) > 1 else 0.0

            stat_row['pri_mean'] = p_mean
            stat_row['pri_sd'] = p_sd
            stat_row['pri_min'] = min(pri_values)
            stat_row['pri_max'] = max(pri_values)
            stat_row['pri_rsd_pct'] = (p_sd / abs(p_mean) * 100) if p_mean != 0 else None
            stat_row['pri_ppm'] = _calc_ppm(p_mean, pri_ref)

        if sec_values:
            s_mean = statistics.fmean(sec_values)
            s_sd = statistics.stdev(sec_values) if len(sec_values) > 1 else 0.0

            stat_row['sec_mean'] = s_mean
            stat_row['sec_sd'] = s_sd
            stat_row['sec_min'] = min(sec_values)
            stat_row['sec_max'] = max(sec_values)
            stat_row['sec_rsd_pct'] = (s_sd / abs(s_mean) * 100) if s_mean != 0 else None
            stat_row['sec_ppm'] = _calc_ppm(s_mean, sec_ref)

        results.append(stat_row)

    return results


def _calc_ppm(mean_value, ref_value):
    """คำนวณ PPM Deviation จากค่าเฉลี่ยเทียบกับค่าอ้างอิง คืนค่า None ถ้าไม่มีค่าอ้างอิง"""
    if ref_value is None:
        return None
    try:
        ref_value = float(ref_value)
    except (TypeError, ValueError):
        return None
    if ref_value == 0:
        return None
    return (mean_value - ref_value) / ref_value * 1_000_000


def format_stats_row_for_table(stat_row: dict) -> dict:
    """
    แปลงตัวเลขดิบจาก calculate_frequency_stats() เป็นข้อความพร้อมแสดงในตาราง UI
    (ทำให้ gui/displays อื่นๆ ไม่ต้องมานั่ง format ทีละที่)
    """
    def fmt(val, sci=True):
        if val is None:
            return "-"
        return f"{val:.5e}" if sci else f"{val:.2f}"

    def fmt_ppm(val):
        if val is None:
            return "-"
        return f"{val:+.1f}"

    return {
        'freq': f"{stat_row['freq']:.2f}",
        'n_samples': str(stat_row['n_samples']),

        'pri_mean': fmt(stat_row['pri_mean']),
        'pri_sd': fmt(stat_row['pri_sd']),
        'pri_min': fmt(stat_row['pri_min']),
        'pri_max': fmt(stat_row['pri_max']),
        'pri_rsd_pct': fmt(stat_row['pri_rsd_pct'], sci=False),
        'pri_ppm': fmt_ppm(stat_row['pri_ppm']),

        'sec_mean': fmt(stat_row['sec_mean']),
        'sec_sd': fmt(stat_row['sec_sd']),
        'sec_min': fmt(stat_row['sec_min']),
        'sec_max': fmt(stat_row['sec_max']),
        'sec_rsd_pct': fmt(stat_row['sec_rsd_pct'], sci=False),
        'sec_ppm': fmt_ppm(stat_row['sec_ppm']),
    }