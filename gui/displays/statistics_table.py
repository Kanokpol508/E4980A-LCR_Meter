# ตารางสรุปสถิติ — ปรับโหมดแสดงผลตามโหมดการวัด (SINGLE / SWEEP / LIST)
# ไฟล์นี้เป็น UI ล้วนๆ — สูตรคำนวณทั้งหมดอยู่ใน data/data_processor.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QLabel)
from PyQt6.QtCore import Qt

from data.data_processor import (
    calculate_single_stats,    format_single_row_for_table,
    calculate_sweep_rows,      format_sweep_row_for_table,
    calculate_frequency_stats, format_stats_row_for_table,
)

# ==========================================
# Column definitions แยกตามโหมด
# ==========================================
_COLS_SINGLE = [
    ("freq",           "Frequency (Hz)"),
    ("n",              "Readings (Count)"),
    ("pri_mean",       "Primary Mean"),
    ("pri_sd",         "Primary SD"),
    ("pri_min",        "Primary Min"),
    ("pri_max",        "Primary Max"),
    ("pri_type_a_ppm", "Primary Type A (ppm)"),
    ("sec_mean",       "Secondary Mean"),
    ("sec_sd",         "Secondary SD"),
    ("sec_min",        "Secondary Min"),
    ("sec_max",        "Secondary Max"),
    ("sec_type_a_ppm", "Secondary Type A (ppm)"),
]

_COLS_SWEEP = [
    ("point_num",  "Point No."),
    ("step_size",  "Step Size (Hz)"),
    ("freq",       "Frequency (Hz)"),
    ("primary",    "Primary"),
    ("secondary",  "Secondary"),
]

_COLS_LIST = [
    ("freq",           "Frequency (Hz)"),
    ("n_samples",      "Samples (Count)"),
    ("pri_mean",       "Primary Mean"),
    ("pri_sd",         "Primary SD"),
    ("pri_min",        "Primary Min"),
    ("pri_max",        "Primary Max"),
    ("pri_ppm",        "Primary PPM Dev"),
    ("pri_type_a_ppm", "Primary Type A (ppm)"),
    ("sec_mean",       "Secondary Mean"),
    ("sec_sd",         "Secondary SD"),
    ("sec_min",        "Secondary Min"),
    ("sec_max",        "Secondary Max"),
    ("sec_ppm",        "Secondary PPM Dev"),
    ("sec_type_a_ppm", "Secondary Type A (ppm)"),
]

_HINTS = {
    "SINGLE": (
        "โหมดวัดจุดเดียว — สถิติรวมของ session ที่ความถี่นั้น "
        "(Type A ppm = ความไม่แน่นอนจากการวัดซ้ำ)"
    ),
    "SWEEP": (
        "โหมดสแกนความถี่ — แสดงค่าที่วัดได้ต่อความถี่ "
        "(วัด 1 ครั้ง/จุด จึงไม่มีสถิติซ้ำ)"
    ),
    "LIST": (
        "โหมดรายการความถี่ — สถิติเต็มรูปแบบแยกตามความถี่ "
        "(PPM Dev ต้องเปิด Deviation PPM และกรอกค่า Reference)"
    ),
}


class StatisticsTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "LIST"

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
        cols = {"SINGLE": _COLS_SINGLE, "SWEEP": _COLS_SWEEP, "LIST": _COLS_LIST}[mode]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels([label for _, label in cols])
        self.table.setRowCount(0)
        self._current_mode = mode
        self.lbl_hint.setText(_HINTS[mode])

    def _set_row(self, row_idx: int, values: list):
        for col_idx, text in enumerate(values):
            item = QTableWidgetItem(str(text))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, col_idx, item)

    def _cols(self) -> list:
        return {"SINGLE": _COLS_SINGLE, "SWEEP": _COLS_SWEEP, "LIST": _COLS_LIST}[self._current_mode]

    # ==========================================
    # Public API
    # ==========================================
    def set_mode(self, mode: str):
        """เรียกจาก app_controller เมื่อโหมดการวัดเปลี่ยน"""
        if mode != self._current_mode:
            self._apply_columns(mode)

    def update_table(self, raw_records: list, pri_ref=None, sec_ref=None, mode: str = None, step_size: float = None):
        """
        อัปเดตตารางใหม่ทั้งหมดจากข้อมูลดิบ
        raw_records: [{'freq':.., 'primary':.., 'secondary':..}, ...]
        step_size: ค่า Step Size (Hz) สำหรับโหมด SWEEP — ใช้แสดงในคอลัมน์ "ค่าเพิ่มต่อจุด"
        สูตรทั้งหมดอยู่ใน data_processor.py — ที่นี่แค่แสดงผล
        """
        if mode and mode != self._current_mode:
            self._apply_columns(mode)

        if self._current_mode == "SINGLE":
            self._render_single(raw_records)
        elif self._current_mode == "SWEEP":
            self._render_sweep(raw_records, step_size=step_size)
        else:
            self._render_list(raw_records, pri_ref, sec_ref)

    def _render_single(self, raw_records: list):
        stat = calculate_single_stats(raw_records)
        if stat is None:
            self.table.setRowCount(0)
            return
        fmt = format_single_row_for_table(stat)
        self.table.setRowCount(1)
        self._set_row(0, [fmt[key] for key, _ in _COLS_SINGLE])

    def _render_sweep(self, raw_records: list, step_size: float = None):
        rows = calculate_sweep_rows(raw_records, step_size=step_size)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            fmt = format_sweep_row_for_table(row)
            self._set_row(i, [fmt[key] for key, _ in _COLS_SWEEP])

    def _render_list(self, raw_records: list, pri_ref=None, sec_ref=None):
        stats = calculate_frequency_stats(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
        self.table.setRowCount(len(stats))
        for i, stat_row in enumerate(stats):
            fmt = format_stats_row_for_table(stat_row)
            self._set_row(i, [fmt[key] for key, _ in _COLS_LIST])

    def clear_table(self):
        self.table.setRowCount(0)