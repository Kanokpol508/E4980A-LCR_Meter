# แสดงผลข้อมูลดิบ (Raw Data) จากเครื่องวัด LCR Meter แบบ Real-time เพื่อใช้ตรวจสอบความถูกต้องของข้อมูล


from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QGroupBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLabel)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from utils.helpers import truncate_sci

# [NEW] จำนวนทศนิยม (นัยสำคัญ) ที่ใช้แสดงค่า Primary/Secondary ในตาราง — ตั้งไว้ที่ 9
# ตำแหน่งให้ตรงกับความละเอียดจริงที่เครื่อง E4980A ส่งกลับมาทาง :FETCh? (รูปแบบ
# ค่าเริ่มต้นของเครื่องคือ 9 หลักหลังจุดทศนิยม เช่น "+1.059517689E-24" ตามคู่มือ)
# มากกว่านี้จะเป็นแค่ floating-point noise จากการแปลง string -> float ไม่ใช่นัยสำคัญ
# จริงจากเครื่องแล้ว
RAW_VALUE_DECIMALS = 9

class RawDataTable(QWidget):
    """
    ตารางแสดงข้อมูลดิบ (Raw Data) ที่อ่านได้จากเครื่องแบบ Real-time
    - แสดงค่าเรียงตามลำดับการวัด (No.)
    - แสดงสถานะ (Status) ของแต่ละจุด เพื่อตรวจสอบ Error/Overload
    - เปลี่ยนหัวคอลัมน์แบบไดนามิกตามโหมดการวัดและ SCPI Mode
    - [NEW] มี Session Info Bar เหนือตาราง แสดงค่าคงที่ตลอด session
      (Mode/สัญญาณ/สายวัด/ย่าน/PPM Ref ฯลฯ) แยกจากตารางเพราะไม่เปลี่ยนต่อแถว
    """
    # [NEW] คำอธิบาย (label) ของแต่ละ key ใน session info — ใช้ทั้งตอนสร้าง UI และ update
    SESSION_INFO_FIELDS = [
        ("mode",             "SCPI Mode"),
        ("signal",           "Signal Level"),
        ("meas_time",        "Meas Time (Aperture)"),
        ("avg",              "Averaging"),
        ("cable",            "Cable Length"),
        ("imp_range",        "Range"),
        ("ppm_pri_ref",      "PPM Ref (Primary)"),
        ("ppm_sec_ref",      "PPM Ref (Secondary)"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mode = "LIST"
        self._session_info_labels = {}   # key -> QLabel (ค่า) สำหรับอัปเดตทีหลัง
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # [NEW] Session Info Bar — แสดงค่าคงที่ตลอด session การวัดนี้
        self.group_session_info = QGroupBox("Measurement Session Info")
        grid_info = QGridLayout()
        grid_info.setHorizontalSpacing(18)
        grid_info.setVerticalSpacing(4)

        for idx, (key, label_text) in enumerate(self.SESSION_INFO_FIELDS):
            row, col = divmod(idx, 2)
            lbl_title = QLabel(f"{label_text}:")
            lbl_title.setStyleSheet("color: #94a3b8; font-size: 11px;")
            lbl_value = QLabel("-")
            lbl_value.setStyleSheet("font-weight: bold; font-size: 12px;")
            grid_info.addWidget(lbl_title, row, col * 2)
            grid_info.addWidget(lbl_value, row, col * 2 + 1)
            self._session_info_labels[key] = lbl_value

        self.group_session_info.setLayout(grid_info)
        layout.addWidget(self.group_session_info)

        self.lbl_hint = QLabel("Raw Data Table (ตารางข้อมูลดิบ) — แสดงค่าที่ได้รับจากเครื่องมือแบบเรียลไทม์")
        self.lbl_hint.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # คอลัมน์ No. ให้พอดีเนื้อหา
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget::item { padding: 4px; }
            QHeaderView::section { padding: 6px; font-weight: bold; }
        """)
        layout.addWidget(self.table)
        
        self.set_mode("LIST") # ค่าเริ่มต้น

    def set_mode(self, mode: str):
        """ปรับหัวคอลัมน์ตามโหมดการวัด (SINGLE, SWEEP, LIST)"""
        self._current_mode = mode
        self.table.setColumnCount(6)
        
        # คอลัมน์พื้นฐาน (ทุกโหมดใช้ "Samples (N)" เหมือนกันแล้ว)
        headers = ["No.", "Frequency (Hz)", "Samples (N)", "Primary", "Secondary", "Status"]
            
        self.table.setHorizontalHeaderLabels(headers)
        self.clear_table()

    def update_headers(self, scpi_mode: str):
        """แปลง SCPI Mode เป็นชื่อแกนแบบย่อ เช่น CPD -> Primary [Cp], Secondary [D]"""
        if not scpi_mode:
            return
            
        pri, sec = "Primary", "Secondary"
        
        # แปลง Primary
        if scpi_mode.startswith("CP"): pri = "Cp"
        elif scpi_mode.startswith("CS"): pri = "Cs"
        elif scpi_mode.startswith("LP"): pri = "Lp"
        elif scpi_mode.startswith("LS"): pri = "Ls"
        elif scpi_mode.startswith("Z"): pri = "Z"
        elif scpi_mode.startswith("Y"): pri = "Y"
        elif scpi_mode.startswith("R"): pri = "R"
        elif scpi_mode == "GB": pri = "G"
        
        # แปลง Secondary
        if scpi_mode.endswith("D") and not scpi_mode.endswith("TD"): sec = "D"
        elif scpi_mode.endswith("Q"): sec = "Q"
        elif scpi_mode.endswith("G"): sec = "G"
        elif scpi_mode.endswith("RS"): sec = "Rs"
        elif scpi_mode.endswith("RP"): sec = "Rp"
        elif scpi_mode.endswith("TD"): sec = "θd"
        elif scpi_mode.endswith("TR"): sec = "θr"
        elif scpi_mode.endswith("X"): sec = "X"
        elif scpi_mode == "GB": sec = "B"

        # ตั้งชื่อ Header คอลัมน์ 3 และ 4 ใหม่
        item_pri = self.table.horizontalHeaderItem(3)
        item_sec = self.table.horizontalHeaderItem(4)
        if item_pri: item_pri.setText(f"Primary [{pri}]")
        if item_sec: item_sec.setText(f"Secondary [{sec}]")

    def append_row(self, data: dict):
        """
        เพิ่ม 1 แถวในตาราง
        data ต้องมี keys: no, freq, sample_text, primary, secondary, status
        """
        row_idx = self.table.rowCount()
        self.table.insertRow(row_idx)

        # 0: No.
        item_no = QTableWidgetItem(str(data.get('no', '')))
        item_no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 0, item_no)

        # 1: Frequency
        freq = data.get('freq')
        freq_str = f"{freq:.2f}" if isinstance(freq, (int, float)) else str(freq)
        item_freq = QTableWidgetItem(freq_str)
        item_freq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 1, item_freq)

        # 2: Samples (N)
        item_sample = QTableWidgetItem(str(data.get('sample_text', '-')))
        item_sample.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 2, item_sample)

        # 3: Primary
        # [แก้ไข] เดิม f"{pri:.5e}" ปัดเศษ (round) และตัดความละเอียดเหลือแค่ 5 ตำแหน่ง
        # เปลี่ยนมาใช้ truncate_sci() ที่ "ตัดทิ้ง" ไม่ปัดเศษ (ตรงกับหลักการเดียวกับ
        # Data Labels ในกราฟ) และเพิ่มเป็น 9 ตำแหน่งเพื่อเก็บนัยสำคัญให้มากที่สุด
        # เท่าที่เครื่องส่งมาจริง (ดู RAW_VALUE_DECIMALS ด้านบน)
        pri = data.get('primary')
        pri_str = truncate_sci(pri, RAW_VALUE_DECIMALS) if isinstance(pri, (int, float)) else str(pri)
        item_pri = QTableWidgetItem(pri_str)
        item_pri.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 3, item_pri)

        # 4: Secondary
        sec = data.get('secondary')
        sec_str = truncate_sci(sec, RAW_VALUE_DECIMALS) if isinstance(sec, (int, float)) else str(sec)
        item_sec = QTableWidgetItem(sec_str)
        item_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 4, item_sec)

        # 5: Status
        status = str(data.get('status', 'SUCCESS'))
        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # ใส่สีแดงให้ตัวอักษรถ้า Status ไม่ใช่ SUCCESS
        if status.upper() != "SUCCESS":
            item_status.setForeground(QBrush(QColor("#ef4444"))) # สีแดง Tailwind
            item_status.setFont(self._get_bold_font())
        else:
            item_status.setForeground(QBrush(QColor("#10b981"))) # สีเขียว Tailwind
            
        self.table.setItem(row_idx, 5, item_status)
        
        # เลื่อนหน้าจอลงมาแถวล่าสุด
        self.table.scrollToBottom()

    def _get_bold_font(self):
        font = self.table.font()
        font.setBold(True)
        return font

    def update_session_info(self, info: dict):
        """[NEW] อัปเดตค่าใน Session Info Bar — เรียกตอนวัดเสร็จ หรือตอน Open Save
        info: dict ที่มี key ตรงกับ SESSION_INFO_FIELDS (ค่าที่ไม่มีจะแสดงเป็น '-')"""
        for key, _ in self.SESSION_INFO_FIELDS:
            value = info.get(key)
            text = str(value) if value not in (None, "") else "-"
            self._session_info_labels[key].setText(text)

    def clear_session_info(self):
        """[NEW] รีเซ็ต Session Info Bar กลับเป็น '-' ทั้งหมด (เรียกตอน Clear Data)"""
        for _, lbl in self._session_info_labels.items():
            lbl.setText("-")

    def clear_table(self):
        self.table.setRowCount(0)

    def get_rows(self) -> list:
        """[NEW] คืนค่าทุกแถวในตารางเป็น list ของ dict (ใช้ตอน Save Result)
        เก็บเป็นข้อความตามที่แสดงผลจริง เพื่อให้ Open Save คืนค่าตารางได้ตรงเป๊ะ"""
        rows = []
        for r in range(self.table.rowCount()):
            def cell(col):
                item = self.table.item(r, col)
                return item.text() if item else ""
            rows.append({
                'no': cell(0),
                'freq': cell(1),
                'sample_text': cell(2),
                'primary': cell(3),
                'secondary': cell(4),
                'status': cell(5),
            })
        return rows