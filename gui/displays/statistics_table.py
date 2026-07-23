# ตารางสรุปสถิติ — ปรับโหมดแสดงผลตามโหมดการวัด (SINGLE / SWEEP / LIST)
# ไฟล์นี้เป็น UI ล้วนๆ — สูตรคำนวณทั้งหมดอยู่ใน data/data_processor.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget,
                              QTableWidgetItem, QHeaderView, QLabel,
                              QStyledItemDelegate, QStyle)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from data.data_processor import (
    calculate_single_stats_per_run, format_single_row_for_table,
    calculate_frequency_stats, format_stats_row_for_table,
)

# ==========================================
# สีกลุ่มคอลัมน์ — ให้โทนเดียวกับสีเส้นในกราฟ (Primary=น้ำเงิน, Secondary=ชมพู/แดง)
# เพื่อให้ผู้ใช้จับคู่ "สีในตาราง" กับ "สีเส้นในกราฟ" ได้ทันทีโดยไม่ต้องอ่านชื่อคอลัมน์
#
# ใช้โทน "มืด" ให้เข้ากับธีมของแอป (ดู assets/styles.qss: พื้นหลังตาราง #040814,
# ตัวอักษรสีขาว) แต่ต้องเข้มพอที่จะตัดกับพื้นเดิมที่มืดมากอยู่แล้วให้เห็นชัด
#
# หมายเหตุสำคัญ: ตั้งใจไม่ใช้ item.setBackground() เพียงอย่างเดียว เพราะแอปนี้ตั้ง
# QSS แบบ global ที่ QApplication (main.py: app.setStyleSheet(...)) — เมื่อมี QSS
# ระดับแอป Qt จะสลับไปวาดผ่าน "style engine" แทน QPalette/BackgroundRole เฉยๆ
# ทำให้สีพื้นหลังที่ตั้งผ่าน setBackground() ถูกทับเงียบๆ ไม่ขึ้นบนหน้าจอ (ปัญหาที่รู้จัก
# กันดีใน Qt Style Sheets) จึงต้องบังคับวาดเองด้วย custom delegate/header ด้านล่าง
# ==========================================
_GROUP_COLORS = {
    1: QColor("#1E293B"),  # กลุ่ม 1: Frequency, Samples (N) — เทาเข้มเป็นกลาง
    2: QColor("#164E8C"),  # กลุ่ม 2: Primary (Mean/SD/Min/Max/%RSD/PPM/Type A) — น้ำเงิน (ตรงกับ COLOR_PRIMARY '#0066CC')
    3: QColor("#8C1550"),  # กลุ่ม 3: Secondary (Mean/SD/Min/Max/%RSD/PPM/Type A) — แดงอมชมพู (ตรงกับ COLOR_SECONDARY '#CC0066')
}
_GROUP_HEADER_COLORS = {
    1: QColor("#334155"),
    2: QColor("#1D4ED8"),
    3: QColor("#BE185D"),
}


def _column_group(key: str) -> int:
    """กำหนดว่าคอลัมน์ (จาก key ใน _COLS_*) อยู่กลุ่มไหน"""
    if key.startswith("pri_"):
        return 2
    if key.startswith("sec_"):
        return 3
    return 1  # freq, n, n_samples


class _GroupColorDelegate(QStyledItemDelegate):
    """วาดพื้นหลังสีกลุ่มคอลัมน์เอง 'ก่อน' ให้ style engine วาดทับ กัน QSS
    ระดับแอปเมิน background ที่ตั้งผ่าน item.setBackground()/BackgroundRole
    (ปัญหาที่รู้จักกันดีเมื่อมี QApplication.setStyleSheet() แบบ global)"""

    def __init__(self, get_group_fn, parent=None):
        super().__init__(parent)
        self._get_group = get_group_fn

    def paint(self, painter, option, index):
        color = self._get_group(index.column())
        if color is not None and not (option.state & QStyle.StateFlag.State_Selected):
            painter.save()
            painter.fillRect(option.rect, color)
            painter.restore()
        super().paint(painter, option, index)


class _ColoredHeaderView(QHeaderView):
    """QHeaderView ที่วาดพื้นหลังแต่ละ section เองตามกลุ่มคอลัมน์ — ต้อง subclass
    เพราะ QSS (QHeaderView::section { background-color: ... }) กำหนดสีเดียวทั้งแถว
    ไม่มี selector ให้ระบุสีแยกทีละ section ได้ ถ้าไม่ subclass สีกลุ่มคอลัมน์ที่ header
    จะไม่มีทางแสดงผล ไม่ว่าจะตั้งค่าผ่าน item.setBackground() แบบไหนก็ตาม"""

    def __init__(self, get_group_fn, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._get_group = get_group_fn

    def paintSection(self, painter, rect, logicalIndex):
        color = self._get_group(logicalIndex)
        if color is not None:
            painter.save()
            painter.fillRect(rect, color)
            painter.restore()
            painter.save()
            painter.setPen(QColor("#E2E8F0"))
            text = self.model().headerData(logicalIndex, Qt.Orientation.Horizontal) if self.model() else ""
            painter.drawText(rect.adjusted(6, 0, -6, 0), Qt.AlignmentFlag.AlignCenter, str(text or ""))
            painter.restore()
        else:
            super().paintSection(painter, rect, logicalIndex)

# ==========================================
# Column definitions แยกตามโหมด
# ==========================================
_COLS_SINGLE = [
    ("freq",           "Frequency (Hz)"),
    ("n",              "Samples (N)"),
    ("pri_mean",       "Primary Mean"),
    ("pri_sd",         "Primary SD"),
    ("pri_min",        "Primary Min"),
    ("pri_max",        "Primary Max"),
    ("pri_rsd_pct",    "Primary %RSD"),
    ("pri_ppm",        "Primary PPM Dev"),
    ("pri_type_a_ppm", "Primary Type A (ppm)"),
    ("sec_mean",       "Secondary Mean"),
    ("sec_sd",         "Secondary SD"),
    ("sec_min",        "Secondary Min"),
    ("sec_max",        "Secondary Max"),
    ("sec_rsd_pct",    "Secondary %RSD"),
    ("sec_ppm",        "Secondary PPM Dev"),
    ("sec_type_a_ppm", "Secondary Type A (ppm)"),
]

# SWEEP ใช้ column set เดียวกับ LIST ทุกประการ (วัดซ้ำได้หลายครั้ง/ความถี่เหมือนกันแล้ว)
_COLS_LIST = [
    ("freq",           "Frequency (Hz)"),
    ("n_samples",      "Samples (N)"),
    ("pri_mean",       "Primary Mean"),
    ("pri_sd",         "Primary SD"),
    ("pri_min",        "Primary Min"),
    ("pri_max",        "Primary Max"),
    ("pri_rsd_pct",    "Primary %RSD"),
    ("pri_ppm",        "Primary PPM Dev"),
    ("pri_type_a_ppm", "Primary Type A (ppm)"),
    ("sec_mean",       "Secondary Mean"),
    ("sec_sd",         "Secondary SD"),
    ("sec_min",        "Secondary Min"),
    ("sec_max",        "Secondary Max"),
    ("sec_rsd_pct",    "Secondary %RSD"),
    ("sec_ppm",        "Secondary PPM Dev"),
    ("sec_type_a_ppm", "Secondary Type A (ppm)"),
]
_COLS_SWEEP = _COLS_LIST

_HINTS = {
    "SINGLE": (
        "Single Frequency mode \u2014 สถิติรวมของ session ที่ความถี่นั้น "
        "(Type A ppm = ความไม่แน่นอนจากการวัดซ้ำ)"
    ),
    "SWEEP": (
        "Sweep Frequency mode \u2014 สถิติแบบละเอียดแยกตามความถี่"
        "(PPM Dev ต้องเปิดใช้งาน Deviation PPM และกรอกค่าอ้างอิง (Reference) ก่อน)"
    ),
    "LIST": (
        "Frequency List mode \u2014 สถิติแบบละเอียดแยกตามความถี่"
        "(PPM Dev ต้องเปิดใช้งาน Deviation PPM และกรอกค่าอ้างอิง (Reference) ก่อน)"
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

        # header/delegate ที่บังคับวาดสีกลุ่มคอลัมน์เอง (เหตุผลดูใน docstring ของคลาส
        # ด้านบน — QSS แบบ global ของแอปจะเมิน background ที่ตั้งผ่าน setBackground() เฉยๆ)
        colored_header = _ColoredHeaderView(self._group_color_for_header, self.table)
        self.table.setHorizontalHeader(colored_header)
        self.table.setItemDelegate(_GroupColorDelegate(self._group_color_for_cell, self.table))

        colored_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        colored_header.setStretchLastSection(False)
        colored_header.setMinimumSectionSize(90)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget::item { padding: 4px 10px; }
            QHeaderView::section { padding: 6px 10px; }
        """)
        layout.addWidget(self.table)

        self._apply_columns("LIST")

    # --------------------------------------------------------
    # ให้ delegate/header เรียกกลับมาถามว่า "คอลัมน์นี้สีอะไร" แบบสด (คำนวณจาก
    # _cols() ปัจจุบันเสมอ) แทนที่จะฝังสีไว้ใน item ตอนสร้าง — กันปัญหาสีไม่อัปเดต
    # ตอนสลับโหมด SINGLE/LIST/SWEEP ที่ column set เปลี่ยนตำแหน่ง key
    def _group_color_for_cell(self, col_idx: int):
        cols = self._cols()
        if col_idx >= len(cols):
            return None
        return _GROUP_COLORS[_column_group(cols[col_idx][0])]

    def _group_color_for_header(self, col_idx: int):
        cols = self._cols()
        if col_idx >= len(cols):
            return None
        return _GROUP_HEADER_COLORS[_column_group(cols[col_idx][0])]

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
        self.table.horizontalHeader().viewport().update()

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

    def update_table(self, raw_records: list, pri_ref=None, sec_ref=None, mode: str = None):
        """
        อัปเดตตารางใหม่ทั้งหมดจากข้อมูลดิบ
        - SINGLE mode: raw_records คือ "กลุ่มต่อรอบ" [[{...},...], [{...},...], ...]
          (1 ครั้งกด Start = 1 รอบ = 1 แถวในตาราง)
        - SWEEP/LIST mode: raw_records คือ flat list [{'freq':.., 'primary':.., 'secondary':..}, ...]
        สูตรทั้งหมดอยู่ใน data_processor.py — ที่นี่แค่แสดงผล
        (SWEEP ใช้สูตรและการแสดงผลเดียวกับ LIST ทุกประการ)
        """
        if mode and mode != self._current_mode:
            self._apply_columns(mode)

        if self._current_mode == "SINGLE":
            self._render_single(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
        else:  # SWEEP หรือ LIST
            self._render_list(raw_records, pri_ref, sec_ref)

    def _render_single(self, run_groups: list, pri_ref=None, sec_ref=None):
        """[แก้ไข] เดิมรวมทุกรอบเป็นแถวเดียว (calculate_single_stats บนข้อมูลทั้งหมด)
        ตอนนี้แยกคำนวณทีละรอบ (1 รอบ = 1 แถว) ด้วย calculate_single_stats_per_run()
        และแก้บั๊กเดิมที่ไม่เคยส่ง pri_ref/sec_ref เข้าไปเลย ทำให้คอลัมน์ PPM Dev ของ
        โหมด SINGLE ไม่เคยคำนวณค่าให้แม้จะกรอก Reference ไว้แล้วก็ตาม"""
        stats_list = calculate_single_stats_per_run(run_groups, pri_ref=pri_ref, sec_ref=sec_ref)
        self.table.setRowCount(len(stats_list))
        for i, stat in enumerate(stats_list):
            fmt = format_single_row_for_table(stat)
            self._set_row(i, [fmt[key] for key, _ in _COLS_SINGLE])

    def _render_list(self, raw_records: list, pri_ref=None, sec_ref=None):
        stats = calculate_frequency_stats(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)
        self.table.setRowCount(len(stats))
        for i, stat_row in enumerate(stats):
            fmt = format_stats_row_for_table(stat_row)
            self._set_row(i, [fmt[key] for key, _ in _COLS_LIST])

    def clear_table(self):
        self.table.setRowCount(0)