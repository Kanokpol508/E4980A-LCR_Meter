# ตารางสรุปสถิติแยกตามความถี่ (Mean/SD/Min/Max/PPM) - อัปเดตสดระหว่างวัด
# ใช้ข้อมูลจาก data/data_processor.py ในการคำนวณ

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QLabel
from PyQt6.QtCore import Qt

from data.data_processor import calculate_frequency_stats, format_stats_row_for_table

COLUMNS = [
    ("freq", "ความถี่ (Hz)"),
    ("n_samples", "N"),
    ("pri_mean", "Primary Mean"),
    ("pri_sd", "Primary SD"),
    ("pri_min", "Primary Min"),
    ("pri_max", "Primary Max"),
    ("pri_rsd_pct", "Primary %RSD"),
    ("pri_ppm", "Primary PPM"),
    ("sec_mean", "Secondary Mean"),
    ("sec_sd", "Secondary SD"),
    ("sec_min", "Secondary Min"),
    ("sec_max", "Secondary Max"),
    ("sec_rsd_pct", "Secondary %RSD"),
    ("sec_ppm", "Secondary PPM"),
]


class StatisticsTable(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        self.lbl_hint = QLabel(
            "ตารางนี้ใช้งานได้กับโหมด Sweep และ List เท่านั้น "
            "(จัดกลุ่มข้อมูลตามความถี่ที่วัดได้ อัปเดตสดระหว่างการวัด)"
        )
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        self.table = QTableWidget()
        self.table.setColumnCount(len(COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in COLUMNS])
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

    def update_table(self, raw_records: list, pri_ref=None, sec_ref=None):
        """
        คำนวณสถิติใหม่จากข้อมูลดิบทั้งหมดที่มีตอนนี้ แล้ววาดตารางใหม่ทั้งตาราง
        raw_records: list ของ dict [{'freq':.., 'primary':.., 'secondary':..}, ...]
        """
        stats_rows = calculate_frequency_stats(raw_records, pri_ref=pri_ref, sec_ref=sec_ref)

        self.table.setRowCount(len(stats_rows))
        for row_idx, stat_row in enumerate(stats_rows):
            formatted = format_stats_row_for_table(stat_row)
            for col_idx, (key, _label) in enumerate(COLUMNS):
                item = QTableWidgetItem(str(formatted[key]))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_idx, col_idx, item)

    def clear_table(self):
        self.table.setRowCount(0)