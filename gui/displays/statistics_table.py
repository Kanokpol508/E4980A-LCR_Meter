# ตารางสรุปสถิติ — ปรับโหมดแสดงผลตามโหมดการวัด (SINGLE / SWEEP / LIST)
#
# SINGLE : Overall Stats ของ session (N, Mean, SD, Min, Max, Type A ppm) — 1 แถวต่อ session
# SWEEP  : ตารางตามความถี่ (Freq, Primary, Secondary) — 1 แถวต่อความถี่ / วัด 1 ครั้งต่อความถี่
# LIST   : ตารางสถิติเต็ม (Freq, N, Mean, SD, Min, Max, %RSD, PPM) — 1 แถวต่อความถี่

import math
import statistics as _stat
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QLabel)
from PyQt6.QtCore import Qt

from data.data_processor import calculate_frequency_stats, format_stats_row_for_table

# ==========================================
# Column definitions แยกตามโหมด
# ==========================================
_COLS_SINGLE = [
    ("n",        "N (ครั้ง)"),
    ("mean_pri", "Primary Mean"),
    ("sd_pri",   "Primary SD"),
    ("min_pri",  "Primary Min"),
    ("max_pri",  "Primary Max"),
    ("typea_pri","Primary Type A (ppm)"),
    ("mean_sec", "Secondary Mean"),
    ("sd_sec",   "Secondary SD"),
    ("min_sec",  "Secondary Min"),
    ("max_sec",  "Secondary Max"),
    ("typea_sec","Secondary Type A (ppm)"),
]

_COLS_SWEEP = [
    ("freq",    "Frequency (Hz)"),
    ("primary", "Primary"),
    ("secondary","Secondary"),
]

_COLS_LIST = [
    ("freq",       "Frequency (Hz)"),
    ("n_samples",  "N"),
    ("pri_mean",   "Primary Mean"),
    ("pri_sd",     "Primary SD"),
    ("pri_min",    "Primary Min"),
    ("pri_max",    "Primary Max"),
    ("pri_rsd_pct","Primary %RSD"),
    ("pri_ppm",    "Primary PPM"),
    ("sec_mean",   "Secondary Mean"),
    ("sec_sd",     "Secondary SD"),
    ("sec_min",    "Secondary Min"),
    ("sec_max",    "Secondary Max"),
    ("sec_rsd_pct","Secondary %RSD"),
    ("sec_ppm",    "Secondary PPM"),
]

# hint text แยกตามโหมด
_HINTS = {
    "SINGLE": "โหมดวัดจุดเดียว — แสดงสถิติรวมของ session (อัปเดตทุกครั้งที่กด Start)",
    "SWEEP":  "โหมดสแกนความถี่ — แสดงค่าที่วัดได้ต่อความถี่ (วัด 1 ครั้ง/จุด ไม่มีสถิติซ้ำ)",
    "LIST":   "โหมดรายการความถี่ — สถิติเต็มรูปแบบแยกตามความถี่ (อัปเดตสดระหว่างวัด)",
}


def _fmt(val, sci=True):
    if val is None:
        return "-"
    return f"{val:.5e}" if sci else f"{val:.4f}"


def _fmt_ppm(val):
    if val is None:
        return "-"
    return f"{val:+.2f}"


def _type_a_ppm(data: list) -> str:
    """คำนวณ Type A Uncertainty (ppm) จาก list ของค่าดิบ"""
    n = len(data)
    if n < 2:
        return "-"
    try:
        sd   = _stat.stdev(data)
        mean = _stat.mean(data)
        if mean == 0:
            return "N/A"
        return f"{(sd / math.sqrt(n)) / abs(mean) * 1e6:+.2f}"
    except Exception:
        return "Error"


class StatisticsTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "LIST"   # โหมดปัจจุบัน — เริ่มต้น LIST (Sweep เป็น default ของ UI)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.lbl_hint = QLabel(_HINTS["LIST"])
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget::item { padding: 4px 10px; }
            QHeaderView::section { padding: 6px 10px; }
        """)
        layout.addWidget(self.table)

        self._apply_columns("LIST")

    # ==========================================
    # Internal helpers
    # ==========================================
    def _apply_columns(self, mode: str):
        """เปลี่ยน column headers ให้ตรงกับโหมด"""
        cols = {"SINGLE": _COLS_SINGLE, "SWEEP": _COLS_SWEEP, "LIST": _COLS_LIST}.get(mode, _COLS_LIST)
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels([label for _, label in cols])
        self.table.setRowCount(0)
        self._current_mode = mode
        self.lbl_hint.setText(_HINTS.get(mode, ""))

    def _set_row(self, row_idx: int, values: list):
        """เขียน values (list of str) ลงแถว row_idx"""
        for col_idx, text in enumerate(values):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, col_idx, item)

    # ==========================================
    # Public API
    # ==========================================
    def set_mode(self, mode: str):
        """เรียกจาก app_controller เมื่อโหมดการวัดเปลี่ยน"""
        if mode != self._current_mode:
            self._apply_columns(mode)

    def update_table(self, raw_records: list, pri_ref=None, sec_ref=None, mode: str = None):
        """
        อัปเดตตารางใหม่ทั้งหมดจากข้อมูลดิบ
        raw_records: list ของ dict [{'freq':.., 'primary':.., 'secondary':..}, ...]
        mode: 'SINGLE' / 'SWEEP' / 'LIST' — ถ้าไม่ส่งจะใช้โหมดปัจจุบัน
        """
        if mode and mode != self._current_mode:
            self._apply_columns(mode)

        if self._current_mode == "SINGLE":
            self._update_single(raw_records)
        elif self._current_mode == "SWEEP":
            self._update_sweep(raw_records)
        else:
            self._update_list(raw_records, pri_ref, sec_ref)

    def _update_single(self, raw_records: list):
        """
        SINGLE mode: สถิติ Overall ทั้ง session — แสดง 1 แถวเสมอ
        raw_records ใน SINGLE จะไม่มี 'freq' key ที่แตกต่างกัน
        ดึงค่า primary/secondary ทั้งหมดมาคำนวณรวมกัน
        """
        if not raw_records:
            self.table.setRowCount(0)
            return

        pri_vals = [r['primary']   for r in raw_records if r.get('primary')   is not None]
        sec_vals = [r['secondary'] for r in raw_records if r.get('secondary') is not None]
        n = len(pri_vals)

        def overall(vals):
            if not vals:
                return "-", "-", "-", "-", "-"
            mean = _stat.mean(vals)
            sd   = _stat.stdev(vals) if len(vals) > 1 else 0.0
            return (_fmt(mean), _fmt(sd), _fmt(min(vals)), _fmt(max(vals)),
                    _type_a_ppm(vals))

        pm, psd, pmin, pmax, pta = overall(pri_vals)
        sm, ssd, smin, smax, sta = overall(sec_vals)

        self.table.setRowCount(1)
        self._set_row(0, [str(n), pm, psd, pmin, pmax, pta,
                          sm, ssd, smin, smax, sta])

    def _update_sweep(self, raw_records: list):
        """
        SWEEP mode: แสดงค่าที่วัดได้ทีละจุด (1 ครั้ง/ความถี่)
        ไม่มีสถิติซ้ำ แค่แสดง Freq | Primary | Secondary ตามลำดับ
        """
        self.table.setRowCount(len(raw_records))
        for row_idx, rec in enumerate(raw_records):
            self._set_row(row_idx, [
                f"{rec.get('freq', 0):.2f}",
                _fmt(rec.get('primary')),
                _fmt(rec.get('secondary')),
            ])

    def _update_list(self, raw_records: list, pri_ref=None, sec_ref=None):
        """
        LIST mode: สถิติเต็มรูปแบบจัดกลุ่มตามความถี่ (เหมือนเดิม)
        """
        stats_rows = calculate_frequency_stats(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
        self.table.setRowCount(len(stats_rows))
        for row_idx, stat_row in enumerate(stats_rows):
            formatted = format_stats_row_for_table(stat_row)
            self._set_row(row_idx, [str(formatted[key]) for key, _ in _COLS_LIST])

    def clear_table(self):
        self.table.setRowCount(0)