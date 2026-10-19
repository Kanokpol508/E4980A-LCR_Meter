# ฟังก์ชันเซฟไฟล์เป็น CSV, Excel หรือพิมพ์ Report


"""
file_exporter.py
=================
Export ไฟล์ Save (JSON) ที่ผู้ใช้เลือก -> ไฟล์ Excel (.xlsx) เดียว โดยใช้ openpyxl

โครงสร้างไฟล์ Excel ที่สร้าง:
    - แทบ "Data Record"      : (เฉพาะถ้าติ๊ก Add Record details) Model/Serial No./Description
                                + Export Date/Time + รายชื่อไฟล์ที่ Export
    - แทบ "Statistics Table" : (เฉพาะถ้าติ๊ก Statistics Table) หัวคอลัมน์เหมือนในโปรแกรม พร้อมสีกลุ่ม
                                คอลัมน์แบบเดียวกับตารางในแอป (เทา=Frequency/N, น้ำเงิน=Primary, ชมพู=Secondary)
                                ต่อข้อมูลเรียงตามลำดับเวลาที่วัด (เก่า -> ใหม่)
    - แทบ "Raw Data"          : (เฉพาะถ้าติ๊ก Raw Data Table)
                                * SINGLE + เลือกหลาย Save -> แยกแทบ "Raw Data 1", "Raw Data 2", ... เรียงตามเวลาที่วัด
                                * กรณีอื่น (SWEEP/LIST เลือกได้ทีละ 1 Save) -> แทบ "Raw Data" เดียว
                                แต่ละแทบมี: ชื่อ Save, Measurement Session Info (รวมวันเวลาที่วัด), หัวคอลัมน์แบบในโปรแกรม

สูตร/การคำนวณสถิติทั้งหมดอ้างอิงจาก data/data_processor.py (แหล่งเดียวกับที่ตารางในโปรแกรมใช้)
เพื่อให้ตัวเลขในไฟล์ Excel ตรงกับที่แสดงบนหน้าจอทุกประการ

หมายเหตุความเข้ากันได้กับ Save ไฟล์เก่า (ก่อนมี key "single_runs"/"graph_raw_pri_y"):
ถ้า save ไม่มีข้อมูลดิบแยกตามรอบ/ความถี่ (legacy save) จะ fallback ไปคำนวณจาก
results.raw_table_rows แทน (ข้อมูลชุดเดียวกับที่โชว์ใน Raw Data Table) เพื่อให้ Statistics
Table ยังคำนวณออกมาได้แทนที่จะว่างเปล่า
"""

import re
import time
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core import save_manager
from data.data_processor import (
    calculate_single_stats_per_run, format_single_row_for_table,
    calculate_frequency_stats, format_stats_row_for_table,
)

# ==========================================
# Column definitions — ต้องตรงกับ gui/displays/statistics_table.py (_COLS_SINGLE / _COLS_LIST)
# คัดลอกมาไว้ที่นี่แทนการ import จาก gui/ เพื่อไม่ให้ data/ (business logic) ผูกกับ gui/ (UI layer)
# group: 1 = Frequency/Samples, 2 = Primary, 3 = Secondary (สีตรงกับ statistics_table.py)
# ==========================================
_COLS_SINGLE = [
    ("nominal",        "Nominal Value",         1),
    ("freq",           "Frequency (Hz)",        1),
    ("n",              "Samples (N)",           1),
    ("pri_mean",       "Primary Mean",          2),
    ("pri_sd",         "Primary SD",            2),
    ("pri_min",        "Primary Min",           2),
    ("pri_max",        "Primary Max",           2),
    ("pri_rsd_pct",    "Primary %RSD",          2),
    ("pri_ppm",        "Primary PPM Dev",       2),
    ("pri_type_a_ppm", "Primary Type A (PPM)",  2),
    ("sec_mean",       "Secondary Mean",        3),
    ("sec_sd",         "Secondary SD",          3),
    ("sec_min",        "Secondary Min",         3),
    ("sec_max",        "Secondary Max",         3),
    ("sec_rsd_pct",    "Secondary %RSD",        3),
    ("sec_ppm",        "Secondary PPM Dev",     3),
    ("sec_type_a_ppm", "Secondary Type A (PPM)", 3),
]
_COLS_LIST = [
    ("nominal",        "Nominal Value",         1),
    ("freq",           "Frequency (Hz)",        1),
    ("n_samples",      "Samples (N)",           1),
    ("pri_mean",       "Primary Mean",          2),
    ("pri_sd",         "Primary SD",            2),
    ("pri_min",        "Primary Min",           2),
    ("pri_max",        "Primary Max",           2),
    ("pri_rsd_pct",    "Primary %RSD",          2),
    ("pri_ppm",        "Primary PPM Dev",       2),
    ("pri_type_a_ppm", "Primary Type A (PPM)",  2),
    ("sec_mean",       "Secondary Mean",        3),
    ("sec_sd",         "Secondary SD",          3),
    ("sec_min",        "Secondary Min",         3),
    ("sec_max",        "Secondary Max",         3),
    ("sec_rsd_pct",    "Secondary %RSD",        3),
    ("sec_ppm",        "Secondary PPM Dev",     3),
    ("sec_type_a_ppm", "Secondary Type A (PPM)", 3),
]

# ต้องตรงกับ gui/displays/raw_data_table.py (RawDataTable.SESSION_INFO_FIELDS)
_SESSION_INFO_FIELDS = [
    ("meas_time",        "Meas Time (Aperture)"),
    ("cable",            "Cable Length"),
    ("imp_range",        "Range"),
    ("ppm_pri_ref",      "PPM Ref (Primary)"),
    ("ppm_sec_ref",      "PPM Ref (Secondary)"),
]

# --- Style — ปรับให้เข้าธีมพาสเทลเดียวกับตัวโปรแกรม (assets/styles.qss) ---
# สีอ้างอิงตรงจากโปรแกรมจริง:
#   - หัวตาราง: ฟ้าเข้ม #789CCE (สีเดียวกับหัว QGroupBox#lcdGroup / ตัวหนังสือขาว)
#   - กล่อง Label: ม่วงพาสเทล #D9C4EC (สีเดียวกับหัวข้อ QGroupBox ทุกกล่องในโปรแกรม)
#   - สีตัวหนังสือหลัก: #2C3A5C, สีตัวหนังสือ label/หัวข้อรอง: #5B7FB5 (โทนเดียวกับ label
#     "Total Readings" ในหน้า Frequency Settings)
#   - สีกลุ่มคอลัมน์ Statistics/Raw Data: ใช้สีเดียวกับตาราง Statistics Table ในโปรแกรมทุกกลุ่มเป๊ะๆ
#     (อ้างอิงจาก gui/displays/statistics_table.py: _GROUP_COLORS / _GROUP_HEADER_COLORS)
#   - เส้นขอบตาราง: ฟ้าอ่อน #AACCE2 (สีเดียวกับขอบช่องกรอกข้อมูลทุกช่องในโปรแกรม)
_HEADER_BG = "789CCE"
_TEXT_NAVY = "2C3A5C"
_TEXT_BLUE_LABEL = "5B7FB5"
_LABEL_BG = "D9C4EC"
_GROUP_BODY_COLOR = {
    0: "C3D5E5",  # คอลัมน์ระบุตัวตน เช่น Save Name / No. — สีเดียวกับหัวคอลัมน์กลุ่ม Frequency ในแอป
    1: "F0F3F6",  # Frequency, Samples (N) — เทาอ่อนเป็นกลาง (ตรงกับ _GROUP_COLORS[1] ในแอป)
    2: "D9F1F1",  # Primary group — ฟ้าพาสเทล (ตรงกับ _GROUP_COLORS[2] ในแอป)
    3: "FADEE1",  # Secondary group — ชมพูพาสเทล (ตรงกับ _GROUP_COLORS[3] ในแอป)
}

_HEADER_FILL = PatternFill(start_color=_HEADER_BG, end_color=_HEADER_BG, fill_type="solid")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=12)
_LABEL_FILL = PatternFill(start_color=_LABEL_BG, end_color=_LABEL_BG, fill_type="solid")
_LABEL_FONT = Font(bold=True, color=_TEXT_NAVY)
_TITLE_FONT = Font(bold=True, size=13, color=_TEXT_NAVY)
_SUBTITLE_FONT = Font(bold=True, size=11, color=_TEXT_BLUE_LABEL)
_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_THIN_SIDE = Side(style="thin", color="AACCE2")
_THIN_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)
_DATA_FONT = Font(color=_TEXT_NAVY)  # สีตัวหนังสือข้อมูลทั่วไป — เดียวกับสีตัวหนังสือหลักของแอป


def _safe_float(text):
    try:
        text = str(text).strip()
        return float(text) if text and text != "-" else None
    except (ValueError, TypeError):
        return None


def _scpi_axis_labels(scpi_mode: str) -> tuple:
    """แปลง FUNC เป็นชื่อแกนแบบย่อ (ตรรกะเดียวกับ RawDataTable.update_headers)"""
    pri, sec = "Primary", "Secondary"
    if not scpi_mode:
        return pri, sec

    if scpi_mode.startswith("CP"): pri = "Cp"
    elif scpi_mode.startswith("CS"): pri = "Cs"
    elif scpi_mode.startswith("LP"): pri = "Lp"
    elif scpi_mode.startswith("LS"): pri = "Ls"
    elif scpi_mode.startswith("Z"): pri = "Z"
    elif scpi_mode.startswith("Y"): pri = "Y"
    elif scpi_mode.startswith("R"): pri = "R"
    elif scpi_mode == "GB": pri = "G"

    if scpi_mode.endswith("D") and not scpi_mode.endswith("TD"): sec = "D"
    elif scpi_mode.endswith("Q"): sec = "Q"
    elif scpi_mode.endswith("G"): sec = "G"
    elif scpi_mode.endswith("RS"): sec = "Rs"
    elif scpi_mode.endswith("RP"): sec = "Rp"
    elif scpi_mode.endswith("TD"): sec = "θd"
    elif scpi_mode.endswith("TR"): sec = "θr"
    elif scpi_mode.endswith("X"): sec = "X"
    elif scpi_mode == "GB": sec = "B"
    return pri, sec


def _raw_records_from_table_rows(raw_table_rows: list) -> list:
    """แปลง results.raw_table_rows (string ที่ format ไว้แสดงในตาราง) กลับเป็นตัวเลข
    ใช้เป็น fallback สำหรับ Save ไฟล์เก่าที่ยังไม่มี single_runs / graph_raw_pri_y เก็บไว้
    ข้ามแถวที่ status ไม่ใช่ SUCCESS หรือแปลงตัวเลขไม่ได้"""
    records = []
    for row in raw_table_rows:
        if str(row.get("status", "SUCCESS")).upper() != "SUCCESS":
            continue
        freq = _safe_float(row.get("freq"))
        primary = _safe_float(row.get("primary"))
        secondary = _safe_float(row.get("secondary"))
        if freq is None or primary is None:
            continue
        records.append({"freq": freq, "primary": primary, "secondary": secondary})
    return records


def _any_ppm_enabled(loaded_saves: list) -> bool:
    """True ถ้ามี Save ไฟล์ใดไฟล์หนึ่งที่เลือกมา Export เปิดใช้ PPM Deviation"""
    return any(item["data"].get("inputs", {}).get("ppm_enabled") for item in loaded_saves)


def _any_nominal_filled(loaded_saves: list) -> bool:
    """True ถ้ามี Save ไฟล์ใดไฟล์หนึ่งที่เลือกมา Export กรอก Nominal Value ไว้"""
    return any(
        str(item["data"].get("inputs", {}).get("nominal_value") or "").strip()
        for item in loaded_saves
    )


def _build_stats_rows(save_data: dict, exclude_cols: set = None):
    """คำนวณ Statistics Table จาก save_data (dict ที่โหลดจาก save_manager.load_save)
    คืน (mode, columns, rows) — rows เป็น list ของ list ค่าที่ format แล้ว (string)
    exclude_cols: set ของ key คอลัมน์ที่ต้องตัดออก (เช่น {'nominal'}, {'pri_ppm','sec_ppm'})"""
    inputs = save_data.get("inputs", {})
    results = save_data.get("results", {})
    mode = inputs.get("run_mode", "SINGLE")

    ppm_enabled = inputs.get("ppm_enabled", False)
    pri_ref = _safe_float(inputs.get("ppm_pri_ref")) if ppm_enabled else None
    sec_ref = _safe_float(inputs.get("ppm_sec_ref")) if ppm_enabled else None

    nominal_text = str(inputs.get("nominal_value") or "").strip() or "-"

    if mode == "SINGLE":
        saved_freq = inputs.get("freq", 0)
        raw_single_runs = results.get("single_runs", [])

        if raw_single_runs:
            single_runs = [
                [tuple(s) if len(s) == 3 else (s[0], s[1], saved_freq) for s in run]
                for run in raw_single_runs
            ]
            raw_records = [
                [{'freq': f, 'primary': p, 'secondary': s} for p, s, f in run]
                for run in single_runs
            ]
        else:
            # Fallback สำหรับ Save ไฟล์เก่าที่ไม่มี single_runs -> ใช้ raw_table_rows แทน
            # (รวมเป็น 1 รอบเดียว เพราะไม่มีข้อมูลแบ่งรอบเก็บไว้)
            fallback_records = _raw_records_from_table_rows(results.get("raw_table_rows", []))
            raw_records = [fallback_records] if fallback_records else []

        stats_list = calculate_single_stats_per_run(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
        columns = _COLS_SINGLE
        if exclude_cols:
            columns = [c for c in columns if c[0] not in exclude_cols]

        def _row_of(s):
            fmt = format_single_row_for_table(s)
            fmt['nominal'] = nominal_text
            return [fmt[key] for key, _, _ in columns]

        rows = [_row_of(s) for s in stats_list]
        stats_list_numeric = stats_list
    else:
        graph_x = results.get("graph_x_data", [])
        graph_raw_pri = results.get("graph_raw_pri_y", [])
        graph_raw_sec = results.get("graph_raw_sec_y", [])

        if graph_raw_pri:
            raw_records = [
                {'freq': f, 'primary': p, 'secondary': s}
                for f, p, s in zip(graph_x, graph_raw_pri, graph_raw_sec)
            ]
        else:
            # Fallback สำหรับ Save ไฟล์เก่าที่ไม่มี graph_raw_pri_y -> ใช้ raw_table_rows แทน
            raw_records = _raw_records_from_table_rows(results.get("raw_table_rows", []))

        stats = calculate_frequency_stats(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
        columns = _COLS_LIST
        if exclude_cols:
            columns = [c for c in columns if c[0] not in exclude_cols]

        def _row_of(s):
            fmt = format_stats_row_for_table(s)
            fmt['nominal'] = nominal_text
            return [fmt[key] for key, _, _ in columns]

        rows = [_row_of(s) for s in stats]
        stats_list_numeric = stats

    return mode, columns, rows, stats_list_numeric


def _sort_key(item: dict):
    """คีย์สำหรับเรียง Save จากเวลาที่วัด 'เก่าสุด -> ใหม่สุด' — ใช้ measurement_time_iso
    ถ้ามี (เรียงถูกต้องแม่นยำ) ไม่งั้น fallback ไปใช้ measurement_time แบบข้อความ"""
    meta = item["data"].get("meta", {})
    return meta.get("measurement_time_iso") or meta.get("measurement_time") or ""


_NUM_SCI = re.compile(r'^[+-]?\d+(\.\d+)?[eE][+-]?\d+$')
_NUM_FIX = re.compile(r'^[+-]?\d+(\.\d+)?$')


def _set_cell_value(cell, value):
    """เขียนค่าลงเซลล์ โดยถ้าเป็นข้อความตัวเลข (เช่น '9.998900000e+02', '+0.36', '100.00')
    จะแปลงเป็น 'ตัวเลขจริง' + number_format ให้หน้าตาเท่าเดิม เพื่อให้ Excel ใช้ฟังก์ชัน
    AVERAGE/STDEV ฯลฯ กับเซลล์ได้ (เดิมเก็บเป็น text ทำให้ได้ #DIV/0!)
    ข้อความอื่น (เช่น '1/10', '-', 'SUCCESS', '1 V') คงเป็นข้อความตามเดิม"""
    if isinstance(value, str):
        t = value.strip()
        if _NUM_SCI.match(t):
            mant = t.lower().split('e')[0]
            dec = len(mant.split('.')[1]) if '.' in mant else 0
            cell.value = float(t)
            cell.number_format = '0.' + '0' * dec + 'E+00' if dec else '0E+00'
            return
        if _NUM_FIX.match(t):
            dec = len(t.split('.')[1]) if '.' in t else 0
            num = float(t)
            cell.value = int(num) if dec == 0 else num
            base = '0.' + '0' * dec if dec else '0'
            cell.number_format = f'+{base};-{base};{base}' if t[0] in '+-' else base
            return
    cell.value = value



def _autosize(ws, min_width=12, max_width=42, start_row=1):
    for col_cells in ws.columns:
        cells = [c for c in col_cells if c.row >= start_row]
        length = max((len(str(c.value)) for c in cells if c.value is not None), default=0)
        col_letter = get_column_letter(col_cells[0].column)
        ws.column_dimensions[col_letter].width = max(min_width, min(length + 4, max_width))


def _write_grouped_header(ws, row_idx: int, headers: list, groups: list = None):
    """เขียนหัวตาราง — สี navy ล้วนทั้งแถวเสมอ (groups เก็บไว้เผื่อใช้อ้างอิงตำแหน่งกลุ่มคอลัมน์
    สำหรับระบายสีแถวข้อมูลด้านล่างเท่านั้น ไม่ได้ใช้แยกสีหัวตารางอีกต่อไป)
    ช่องที่ text เป็น None จะถูกข้าม ไม่ระบายสีทับ (ใช้เป็นคอลัมน์ spacer เว้นว่างได้)"""
    ws.row_dimensions[row_idx].height = 22
    for col_idx, text in enumerate(headers, start=1):
        if text is None:
            continue
        cell = ws.cell(row=row_idx, column=col_idx, value=text)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER


def _write_header_row(ws, row_idx: int, headers: list):
    _write_grouped_header(ws, row_idx, headers)


# ==========================================
# Raw-data layout / full-precision values / formula helpers
# ==========================================
_FULL_SCI_FMT = '0.000000000000000E+00'     # แสดง 16 หลักนัยสำคัญ (ค่าที่เก็บในเซลล์เป็น float เต็มเสมออยู่แล้ว)
_STAT_SCI_FMT = '0.000000000E+00'
_STAT_FIX_FMT = '0.000000000000'


def _raw_layout(exclude_ppm: bool, exclude_nominal: bool) -> dict:
    """ตำแหน่งในแท็บ Raw Data (ต้องตรงกับ _write_raw_data_tab): แถวแรกของข้อมูล + ตัวอักษรคอลัมน์ Primary/Secondary"""
    n_fields = len(_SESSION_INFO_FIELDS) - (2 if exclude_ppm else 0)
    header_row = 4 + 1 + n_fields + 1
    pri_idx = 7 if exclude_nominal else 8          # 1-based: No., [Nominal], SCPI, Freq, AVG, Signal, Samples, Primary, Secondary, Status
    return {
        "first_row": header_row + 1,
        "pri_col": get_column_letter(pri_idx),
        "sec_col": get_column_letter(pri_idx + 1),
    }


def _raw_sheet_name(idx: int, mode: str, n_saves: int) -> str:
    return f"Raw Data {idx}" if (mode == "SINGLE" and n_saves > 1) else "Raw Data"


def _full_raw_arrays(data: dict):
    """ค่าดิบ float เต็มความละเอียด (pri_list, sec_list) เรียงตามลำดับแถวใน raw_table_rows
    คืน None ถ้าไม่มี/จำนวนไม่ตรงกับแถวในตาราง (Save เก่าที่ข้อมูลไม่ครบ)"""
    inputs = data.get("inputs", {})
    results = data.get("results", {})
    n_rows = len(results.get("raw_table_rows", []))
    if inputs.get("run_mode", "SINGLE") == "SINGLE":
        runs = results.get("single_runs", [])
        pri = [s[0] for run in runs for s in run]
        sec = [s[1] for run in runs for s in run]
    else:
        pri = list(results.get("graph_raw_pri_y", []))
        sec = list(results.get("graph_raw_sec_y", []))
    if n_rows and len(pri) == n_rows and len(sec) == n_rows:
        return pri, sec
    return None


def _stat_row_spans(data: dict):
    """ช่วงแถว (0-based, inclusive) ของข้อมูลดิบที่ใช้คำนวณสถิติแต่ละแถว เรียงเหมือนแถวในตารางสถิติ
    คืน None ถ้าสร้างช่วงต่อเนื่องไม่ได้ (ความถี่ซ้ำไม่ติดกัน / ข้อมูลไม่ครบ) -> ใช้ค่าคงที่แทนสูตร"""
    inputs = data.get("inputs", {})
    results = data.get("results", {})
    if _full_raw_arrays(data) is None:
        return None
    if inputs.get("run_mode", "SINGLE") == "SINGLE":
        spans, start = [], 0
        for run in results.get("single_runs", []):
            if run:
                spans.append((start, start + len(run) - 1))
            start += len(run)
        return spans
    groups = {}
    for i, f in enumerate(results.get("graph_x_data", [])):
        groups.setdefault(round(float(f), 6), []).append(i)
    spans = []
    for key in sorted(groups):
        idx = groups[key]
        if idx[-1] - idx[0] + 1 != len(idx):
            return None
        spans.append((idx[0], idx[-1]))
    return spans


def _quote_sheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _stat_formula(key: str, static_text: str, n: int, pri_rng: str, sec_rng: str, pri_ref, sec_ref):
    """สูตร Excel ของช่องสถิติ (key เช่น 'pri_mean') หรือ None ถ้าให้คงค่าไว้ (เช่น '-' / N<2)
    คืน (formula, number_format)"""
    if key in ("nominal", "freq", "n", "n_samples") or static_text == "-":
        return None
    if key.startswith("pri_"):
        rng, ref, name = pri_rng, pri_ref, key[4:]
    elif key.startswith("sec_"):
        rng, ref, name = sec_rng, sec_ref, key[4:]
    else:
        return None
    if name == "mean":
        return f"=AVERAGE({rng})", _STAT_SCI_FMT
    if name == "min":
        return f"=MIN({rng})", _STAT_SCI_FMT
    if name == "max":
        return f"=MAX({rng})", _STAT_SCI_FMT
    if name == "sd":
        return (f"=STDEV({rng})", _STAT_SCI_FMT) if n > 1 else None
    if name == "rsd_pct":
        return f"=STDEV({rng})/ABS(AVERAGE({rng}))*100", _STAT_FIX_FMT
    if name == "ppm":
        if ref is None or ref == 0:
            return None
        return f"=(AVERAGE({rng})-{repr(float(ref))})/ABS({repr(float(ref))})*1000000", _STAT_FIX_FMT
    if name == "type_a_ppm":
        return f"=(STDEV({rng})/SQRT(COUNT({rng})))/ABS(AVERAGE({rng}))*1000000", _STAT_FIX_FMT
    return None


# ==========================================
# Sheet builders
# ==========================================
def _add_data_record_sheet(wb: Workbook, record_details: dict, save_names: list):
    ws = wb.create_sheet("Data Record")
    ws.sheet_view.showGridLines = True
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 42

    _write_header_row(ws, 2, [None, "Information", "Details"])

    now = time.localtime()
    rows = [
        ("Model", record_details.get("model") or "-"),
        ("Serial No.", record_details.get("serial_no") or "-"),
        ("Description", record_details.get("description") or "-"),
        ("Export Date", time.strftime("%Y-%m-%d", now)),
        ("Export Time", time.strftime("%H:%M:%S", now)),
    ]

    r = 3
    for label, value in rows:
        ws.cell(row=r, column=2, value=label).font = _LABEL_FONT
        ws.cell(row=r, column=2).fill = _LABEL_FILL
        ws.cell(row=r, column=2).border = _THIN_BORDER
        value_cell = ws.cell(row=r, column=3, value=value)
        value_cell.border = _THIN_BORDER
        value_cell.alignment = _LEFT
        value_cell.font = _DATA_FONT
        r += 1

    # Exported Files — แถวแรกมี label "Exported Files", แถวถัดไปเป็นชื่อไฟล์ล้วนๆ (ไม่มี label ซ้ำ)
    ws.cell(row=r, column=2, value="Exported Files").font = _LABEL_FONT
    ws.cell(row=r, column=2).fill = _LABEL_FILL
    ws.cell(row=r, column=2).border = _THIN_BORDER
    for i, name in enumerate(save_names):
        name_cell = ws.cell(row=r + i, column=3, value=name)
        name_cell.border = _THIN_BORDER
        name_cell.alignment = _LEFT
        name_cell.font = _DATA_FONT
    r += max(len(save_names), 1)

    ws.cell(row=r, column=2, value="Total Saved Files").font = _LABEL_FONT
    ws.cell(row=r, column=2).fill = _LABEL_FILL
    ws.cell(row=r, column=2).border = _THIN_BORDER
    total_cell = ws.cell(row=r, column=3, value=len(save_names))
    total_cell.border = _THIN_BORDER
    total_cell.alignment = _LEFT
    total_cell.font = _DATA_FONT


def _add_statistics_sheet(wb: Workbook, loaded_saves: list, raw_available: bool = False):
    """แท็บ Statistics Table — ถ้ามีแท็บ Raw Data ในไฟล์เดียวกัน (raw_available) ช่องสถิติจะเป็น "สูตร Excel"
    ที่อ้างค่าดิบเต็มความละเอียด ให้ผู้ใช้ตรวจสอบเองได้ (ช่องที่ทำสูตรไม่ได้จะคงเป็นค่าคงที่)
"""
    ws = wb.create_sheet("Statistics Table")
    ws.sheet_view.showGridLines = True

    # ตัดคอลัมน์ PPM Dev ออกถ้าไม่มี Save ไฟล์ไหนเปิดใช้ PPM Deviation เลยซักไฟล์
    # ตัดคอลัมน์ Nominal Value ออกถ้าไม่มี Save ไฟล์ไหนกรอก Nominal Value ไว้เลยซักไฟล์
    exclude_cols = set()
    if not _any_ppm_enabled(loaded_saves):
        exclude_cols |= {"pri_ppm", "sec_ppm"}
    if not _any_nominal_filled(loaded_saves):
        exclude_cols.add("nominal")

    layout = _raw_layout(not _any_ppm_enabled(loaded_saves), not _any_nominal_filled(loaded_saves))
    mode0 = loaded_saves[0]["data"].get("inputs", {}).get("run_mode", "SINGLE")

    _, columns, _, _ = _build_stats_rows(loaded_saves[0]["data"], exclude_cols)
    headers = ["Save Name"] + [label for _, label, _ in columns]
    groups = [0] + [g for _, _, g in columns]
    _write_grouped_header(ws, 1, headers, groups)
    ws.freeze_panes = "A2"

    row_idx = 2
    for save_idx, item in enumerate(loaded_saves, start=1):
        data = item["data"]
        inputs = data.get("inputs", {})
        _, _, rows, _ = _build_stats_rows(data, exclude_cols)

        # ช่วงแถวข้อมูลดิบต่อแถวสถิติ (สำหรับสูตร) — ใช้ได้เฉพาะเมื่อมีแท็บ Raw Data ของ Save นี้จริง
        raw_sheet = None
        spans = None
        if raw_available and (mode0 == "SINGLE" or save_idx == 1):
            raw_sheet = _raw_sheet_name(save_idx, mode0, len(loaded_saves))
            spans = _stat_row_spans(data)
            if spans is not None and len(spans) != len(rows):
                spans = None
        ppm_on = inputs.get("ppm_enabled", False)
        pri_ref = _safe_float(inputs.get("ppm_pri_ref")) if ppm_on else None
        sec_ref = _safe_float(inputs.get("ppm_sec_ref")) if ppm_on else None

        for r_i, row in enumerate(rows):
            name_cell = ws.cell(row=row_idx, column=1, value=item["save_name"])
            name_cell.alignment = _LEFT
            name_cell.border = _THIN_BORDER
            name_cell.font = _LABEL_FONT
            name_fill = _GROUP_BODY_COLOR[0]
            name_cell.fill = PatternFill(start_color=name_fill, end_color=name_fill, fill_type="solid")

            pri_rng = sec_rng = None
            n_here = 0
            if spans is not None:
                first = layout["first_row"] + spans[r_i][0]
                last = layout["first_row"] + spans[r_i][1]
                q = _quote_sheet(raw_sheet)
                pri_rng = f"{q}!${layout['pri_col']}${first}:${layout['pri_col']}${last}"
                sec_rng = f"{q}!${layout['sec_col']}${first}:${layout['sec_col']}${last}"
                n_here = spans[r_i][1] - spans[r_i][0] + 1

            for col_idx, value in enumerate(row, start=2):
                key = columns[col_idx - 2][0]
                group = groups[col_idx - 1]
                cell = ws.cell(row=row_idx, column=col_idx)

                formula = None
                if pri_rng is not None:
                    formula = _stat_formula(key, str(value), n_here, pri_rng, sec_rng, pri_ref, sec_ref)
                if formula is not None:
                    cell.value, cell.number_format = formula
                else:
                    _set_cell_value(cell, value)

                cell.alignment = _CENTER
                cell.border = _THIN_BORDER
                cell.font = _DATA_FONT
                body_color = _GROUP_BODY_COLOR.get(group)
                if body_color:
                    cell.fill = PatternFill(start_color=body_color, end_color=body_color, fill_type="solid")
            row_idx += 1

    if row_idx == 2:
        ws.cell(row=2, column=1, value="(ไม่มีข้อมูลสถิติให้แสดง)")

    _autosize(ws, start_row=1)


def _write_raw_data_tab(ws, item: dict, exclude_ppm: bool = False, exclude_nominal: bool = False):
    """เขียนเนื้อหา 1 แทบ Raw Data: ชื่อ Save -> Session Info (รวมวันเวลาที่วัด) -> ตารางข้อมูลดิบ
    exclude_ppm    : ตัด "PPM Ref (Primary/Secondary)" ออกจาก Session Info
    exclude_nominal: ตัดคอลัมน์ "Nominal Value" ออกจากตารางข้อมูลดิบ"""
    ws.sheet_view.showGridLines = True
    data = item["data"]
    inputs = data.get("inputs", {})
    results = data.get("results", {})
    session_info = data.get("session_info", {})
    meta = data.get("meta", {})

    ws.cell(row=1, column=1, value=f"Save Name: {item['save_name']}").font = _TITLE_FONT

    ws.cell(row=3, column=1, value="Measurement Session Info").font = _SUBTITLE_FONT
    r = 4

    # วันเวลาที่วัด — ดึงจาก meta.measurement_time (session_info เดิมไม่มี field นี้)
    ws.cell(row=r, column=1, value="Measurement Date/Time:").font = _LABEL_FONT
    ws.cell(row=r, column=1).fill = _LABEL_FILL
    ws.cell(row=r, column=1).border = _THIN_BORDER
    date_cell = ws.cell(row=r, column=2, value=meta.get("measurement_time") or "-")
    date_cell.border = _THIN_BORDER
    date_cell.alignment = _LEFT
    date_cell.font = _DATA_FONT
    r += 1

    for key, label in _SESSION_INFO_FIELDS:
        if exclude_ppm and key in ("ppm_pri_ref", "ppm_sec_ref"):
            continue
        value = session_info.get(key)
        ws.cell(row=r, column=1, value=f"{label}:").font = _LABEL_FONT
        ws.cell(row=r, column=1).fill = _LABEL_FILL
        ws.cell(row=r, column=1).border = _THIN_BORDER
        value_cell = ws.cell(row=r, column=2, value=value if value not in (None, "") else "-")
        value_cell.border = _THIN_BORDER
        value_cell.alignment = _LEFT
        value_cell.font = _DATA_FONT
        r += 1

    r += 1  # แถวว่างคั่น
    scpi_mode = inputs.get("scpi_mode")
    pri_label, sec_label = _scpi_axis_labels(scpi_mode)

    # นิยามคอลัมน์ทั้งหมด: (header, getter, กลุ่มสี) — ตัด "Nominal Value" ออกได้ถ้า exclude_nominal
    # กลุ่มสีคอลัมน์: No./Nominal/FUNC=identify(0), Freq/AVG/Signal/Samples=1,
    # Primary=2, Secondary=3, Status=ไม่ระบายพื้น
    col_defs = [
        ("No.", lambda rd: rd.get("no", ""), 0),
        ("Nominal Value", lambda rd: rd.get("nominal", "-"), 0),
        ("FUNC", lambda rd: rd.get("scpi_mode", "-"), 0),
        ("Frequency (Hz)", lambda rd: rd.get("freq", ""), 1),
        ("AVG", lambda rd: rd.get("avg", "-"), 1),
        ("Signal Level", lambda rd: rd.get("signal_level", "-"), 1),
        ("Samples (N)", lambda rd: rd.get("sample_text", ""), 1),
        (f"Primary [{pri_label}]", lambda rd: rd.get("primary", ""), 2),
        (f"Secondary [{sec_label}]", lambda rd: rd.get("secondary", ""), 3),
        ("Status", lambda rd: rd.get("status", ""), None),
    ]
    if exclude_nominal:
        col_defs = [c for c in col_defs if c[0] != "Nominal Value"]
    status_col_idx = len(col_defs)  # Status อยู่คอลัมน์สุดท้ายเสมอ

    headers = [h for h, _, _ in col_defs]
    _write_header_row(ws, r, headers)
    ws.freeze_panes = ws.cell(row=r + 1, column=1).coordinate
    r += 1

    # ค่า Primary/Secondary: เขียนเป็น float เต็มความละเอียด (ไม่ตัด/ไม่ปัด) เสมอ
    # ลำดับความสำคัญ: อาร์เรย์ float เต็มที่เก็บไว้ -> สตริงดิบจากเครื่อง -> สตริงในตาราง
    full_arrays = _full_raw_arrays(data)
    pri_col_idx = [i for i, c in enumerate(col_defs, start=1) if c[0].startswith("Primary")][0]
    sec_col_idx = pri_col_idx + 1

    for row_i, row_data in enumerate(results.get("raw_table_rows", [])):
        for col_idx, (_, getter, group) in enumerate(col_defs, start=1):
            value = getter(row_data)
            cell = ws.cell(row=r, column=col_idx)
            if col_idx in (pri_col_idx, sec_col_idx):
                num = None
                if full_arrays is not None:
                    num = full_arrays[0 if col_idx == pri_col_idx else 1][row_i]
                else:
                    key = "primary" if col_idx == pri_col_idx else "secondary"
                    num = _safe_float(row_data.get(key + "_raw")) or _safe_float(row_data.get(key))
                if num is not None:
                    cell.value = float(num)
                    cell.number_format = _FULL_SCI_FMT
                else:
                    _set_cell_value(cell, value)
            else:
                _set_cell_value(cell, value)
            cell.alignment = _CENTER
            cell.border = _THIN_BORDER
            cell.font = _DATA_FONT
            body_color = _GROUP_BODY_COLOR.get(group)
            if body_color:
                cell.fill = PatternFill(start_color=body_color, end_color=body_color, fill_type="solid")
            # สีสถานะ SUCCESS/FAIL — ใช้โทนเขียว/แดงเดียวกับสีปุ่ม START/STOP ในแอป
            if col_idx == status_col_idx and str(value).upper() != "SUCCESS":
                cell.font = Font(bold=True, color="D2544B")
            elif col_idx == status_col_idx:
                cell.font = Font(bold=True, color="14532D")
        r += 1

    for col_idx in range(1, len(col_defs) + 1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 20
    ws.column_dimensions["A"].width = max(ws.column_dimensions["A"].width, 28)


def _add_raw_data_sheets(wb: Workbook, loaded_saves: list):
    mode = loaded_saves[0]["data"].get("inputs", {}).get("run_mode", "SINGLE")

    # ตัด PPM Ref ออกถ้าไม่มี Save ไฟล์ไหนเปิดใช้ PPM Deviation เลยซักไฟล์
    # ตัด Nominal Value ออกถ้าไม่มี Save ไฟล์ไหนกรอก Nominal Value ไว้เลยซักไฟล์
    exclude_ppm = not _any_ppm_enabled(loaded_saves)
    exclude_nominal = not _any_nominal_filled(loaded_saves)

    if mode == "SINGLE" and len(loaded_saves) > 1:
        for idx, item in enumerate(loaded_saves, start=1):
            ws = wb.create_sheet(f"Raw Data {idx}")
            _write_raw_data_tab(ws, item, exclude_ppm=exclude_ppm, exclude_nominal=exclude_nominal)
    else:
        ws = wb.create_sheet("Raw Data")
        _write_raw_data_tab(ws, loaded_saves[0], exclude_ppm=exclude_ppm, exclude_nominal=exclude_nominal)


# ==========================================
# Public API
# ==========================================
def export_measurements_to_excel(
    save_paths: list,
    output_path,
    include_stats: bool = True,
    include_raw: bool = True,
    record_details: dict = None,
) -> Path:
    """
    Export ไฟล์ Save ที่เลือก (list ของ path หรือ dict ที่มี 'path'/'save_name') ไปเป็นไฟล์ Excel เดียว

    save_paths     : list ของ path (str/Path) หรือ dict {'path':.., 'save_name':..} ที่ได้จาก
                      save_manager.list_saves() — ต้องเป็น Save โหมดเดียวกันทั้งหมด
    output_path    : path ไฟล์ .xlsx ที่จะบันทึก (รวมชื่อไฟล์)
    include_stats  : ติ๊ก "Statistics Table" หรือไม่
    include_raw    : ติ๊ก "Raw Data Table" หรือไม่
    record_details : dict {'model', 'serial_no', 'description'} หรือ None ถ้าไม่ติ๊ก Add Record details

    คืนค่า Path ของไฟล์ที่บันทึกสำเร็จ — ข้อมูลทุกแทบเรียงตามเวลาที่วัด "เก่าสุด -> ใหม่สุด"
    """
    if not save_paths:
        raise ValueError("ไม่มี Save ที่เลือกสำหรับ Export")

    loaded_saves = []
    for item in save_paths:
        if isinstance(item, dict):
            path = item["path"]
            save_name = item.get("save_name")
        else:
            path = item
            save_name = None
        data = save_manager.load_save(path)
        if not save_name:
            save_name = data.get("meta", {}).get("save_name", Path(path).stem)
        loaded_saves.append({"path": path, "save_name": save_name, "data": data})

    # เรียงจากเวลาที่วัดเก่าสุด -> ใหม่สุด (list_saves() คืนค่ามาแบบใหม่สุดก่อน)
    loaded_saves.sort(key=_sort_key)

    wb = Workbook()
    wb.remove(wb.active)  # ลบ sheet เปล่า default ทิ้ง

    if record_details is not None:
        _add_data_record_sheet(wb, record_details, [it["save_name"] for it in loaded_saves])

    if include_stats:
        _add_statistics_sheet(wb, loaded_saves, raw_available=include_raw)

    if include_raw:
        _add_raw_data_sheets(wb, loaded_saves)

    wb.calculation.fullCalcOnLoad = True    # ให้ Excel คำนวณสูตรใหม่ทั้งหมดทุกครั้งที่เปิดไฟล์

    if not wb.sheetnames:
        # กันกรณีไม่ติ๊กอะไรเลย -> ยังต้องมีอย่างน้อย 1 sheet ไม่งั้น openpyxl error ตอน save
        wb.create_sheet("Data Record")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(output_path))
    return output_path