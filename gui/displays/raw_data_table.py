# แสดงผลข้อมูลดิบ (Raw Data) จากเครื่องวัด LCR Meter แบบ Real-time เพื่อใช้ตรวจสอบความถูกต้องของข้อมูล


from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QGroupBox, QTableWidget,
                             QTableWidgetItem, QHeaderView, QLabel)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush

from utils.helpers import format_full_sci

# จำนวนทศนิยม (นัยสำคัญ) ที่ใช้แสดงค่า Primary/Secondary ในตาราง — ตั้งไว้ที่ 9
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
    - เปลี่ยนหัวคอลัมน์แบบไดนามิกตามโหมดการวัดและ FUNC
    - มี Session Info Bar เหนือตาราง แสดงค่าคงที่ตลอด session
      (Mode/สัญญาณ/สายวัด/ย่าน/PPM Ref ฯลฯ) แยกจากตารางเพราะไม่เปลี่ยนต่อแถว
    """
    # คำอธิบาย (label) ของแต่ละ key ใน session info — ใช้ทั้งตอนสร้าง UI และ update
    # ย้าย FUNC / Signal Level / Averaging ออกจาก Session Info Bar ไปบันทึก
    # เป็นคอลัมน์ต่อแถวในตารางแทน (ผู้ใช้ปลดล็อกให้แก้ค่าเหล่านี้ระหว่าง session ได้แล้ว
    # จึงไม่ใช่ค่าคงที่ตลอด session อีกต่อไป — ต้องอ้างอิงต่อแถวถึงจะถูกต้อง)
    SESSION_INFO_FIELDS = [
        ("meas_time",        "Meas Time (Aperture)"),
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

        # Session Info Bar — แสดงค่าคงที่ตลอด session การวัดนี้
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
        self.table.setColumnCount(10)

        # คอลัมน์พื้นฐาน (ทุกโหมดใช้ "Samples (N)" เหมือนกันแล้ว)
        # Nominal Value อยู่ถัดจาก No., FUNC อยู่ถัดจาก Nominal Value
        # AVG อยู่ถัดจาก Frequency (Hz), Signal Level อยู่ถัดจาก AVG
        headers = ["No.", "Nominal Value", "FUNC", "Frequency (Hz)", "AVG", "Signal Level",
                   "Samples (N)", "Primary", "Secondary", "Status"]

        self.table.setHorizontalHeaderLabels(headers)
        self.clear_table()

    def update_headers(self, scpi_mode: str):
        """แปลง FUNC เป็นชื่อแกนแบบย่อ เช่น CPD -> Primary [Cp], Secondary [D]"""
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

        # ตั้งชื่อ Header คอลัมน์ Primary และ Secondary ใหม่
        # (คอลัมน์ 7/8 หลังจากแทรก Nominal Value/FUNC/AVG/Signal Level)
        item_pri = self.table.horizontalHeaderItem(7)
        item_sec = self.table.horizontalHeaderItem(8)
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

        # 1: Nominal Value (ข้อความอิสระที่ผู้ใช้กรอก — ถ้าไม่ได้กรอกให้แสดง "-")
        nominal = data.get('nominal')
        nominal_str = str(nominal).strip() if nominal not in (None, "") else "-"
        if not nominal_str:
            nominal_str = "-"
        item_nominal = QTableWidgetItem(nominal_str)
        item_nominal.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 1, item_nominal)

        # 2: FUNC (ค่าที่ใช้จริงตอนวัดแถวนี้ — ย้ายมาจาก Session Info Bar เดิม)
        item_scpi = QTableWidgetItem(str(data.get('scpi_mode', '-')))
        item_scpi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 2, item_scpi)

        # 3: Frequency
        freq = data.get('freq')
        freq_str = f"{freq:.2f}" if isinstance(freq, (int, float)) else str(freq)
        item_freq = QTableWidgetItem(freq_str)
        item_freq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 3, item_freq)

        # 4: AVG (Averaging — ย้ายมาจาก Session Info Bar เดิม)
        item_avg = QTableWidgetItem(str(data.get('avg', '-')))
        item_avg.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 4, item_avg)

        # 5: Signal Level (ย้ายมาจาก Session Info Bar เดิม)
        item_signal = QTableWidgetItem(str(data.get('signal_level', '-')))
        item_signal.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 5, item_signal)

        # 6: Samples (N)
        item_sample = QTableWidgetItem(str(data.get('sample_text', '-')))
        item_sample.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 6, item_sample)

        # 7: Primary
        # เดิม f"{pri:.5e}" ปัดเศษ (round) และตัดความละเอียดเหลือแค่ 5 ตำแหน่ง
        # เปลี่ยนมาใช้ truncate_sci() ที่ "ตัดทิ้ง" ไม่ปัดเศษ (ตรงกับหลักการเดียวกับ
        # Data Labels ในกราฟ) และเพิ่มเป็น 9 ตำแหน่งเพื่อเก็บนัยสำคัญให้มากที่สุด
        # เท่าที่เครื่องส่งมาจริง (ดู RAW_VALUE_DECIMALS ด้านบน)
        pri = data.get('primary')
        # แสดงค่าเต็ม (lossless) ไม่ตัด ไม่ปัด — ตรงกับค่าที่เก็บและใช้คำนวณสถิติทุกบิต
        pri_str = format_full_sci(pri) if isinstance(pri, (int, float)) else str(pri)
        item_pri = QTableWidgetItem(pri_str)
        item_pri.setData(Qt.ItemDataRole.UserRole, data.get('primary_raw'))  # สตริงดิบจากเครื่อง
        item_pri.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 7, item_pri)

        # 8: Secondary
        sec = data.get('secondary')
        sec_str = format_full_sci(sec) if isinstance(sec, (int, float)) else str(sec)
        item_sec = QTableWidgetItem(sec_str)
        item_sec.setData(Qt.ItemDataRole.UserRole, data.get('secondary_raw'))
        item_sec.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_idx, 8, item_sec)

        # 9: Status
        status = str(data.get('status', 'SUCCESS'))
        item_status = QTableWidgetItem(status)
        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # ใส่สีแดงให้ตัวอักษรถ้า Status ไม่ใช่ SUCCESS
        if status.upper() != "SUCCESS":
            item_status.setForeground(QBrush(QColor("#ef4444"))) # สีแดง Tailwind
            item_status.setFont(self._get_bold_font())
        else:
            item_status.setForeground(QBrush(QColor("#10b981"))) # สีเขียว Tailwind
            
        self.table.setItem(row_idx, 9, item_status)
        
        # เลื่อนหน้าจอลงมาแถวล่าสุด
        self.table.scrollToBottom()

    def _get_bold_font(self):
        font = self.table.font()
        font.setBold(True)
        return font

    def update_session_info(self, info: dict):
        """อัปเดตค่าใน Session Info Bar — เรียกตอนวัดเสร็จ หรือตอน Open Save
        info: dict ที่มี key ตรงกับ SESSION_INFO_FIELDS (ค่าที่ไม่มีจะแสดงเป็น '-')"""
        for key, _ in self.SESSION_INFO_FIELDS:
            value = info.get(key)
            text = str(value) if value not in (None, "") else "-"
            self._session_info_labels[key].setText(text)

    def clear_session_info(self):
        """รีเซ็ต Session Info Bar กลับเป็น '-' ทั้งหมด (เรียกตอน Clear Data)"""
        for _, lbl in self._session_info_labels.items():
            lbl.setText("-")

    def clear_table(self):
        self.table.setRowCount(0)

    def get_rows(self) -> list:
        """คืนค่าทุกแถวในตารางเป็น list ของ dict (ใช้ตอน Save Result)
        เก็บเป็นข้อความตามที่แสดงผลจริง เพื่อให้ Open Save คืนค่าตารางได้ตรงเป๊ะ"""
        rows = []
        for r in range(self.table.rowCount()):
            def cell(col):
                item = self.table.item(r, col)
                return item.text() if item else ""
            def raw(col):
                item = self.table.item(r, col)
                return item.data(Qt.ItemDataRole.UserRole) if item else None
            rows.append({
                'no': cell(0),
                'nominal': cell(1),
                'scpi_mode': cell(2),
                'freq': cell(3),
                'avg': cell(4),
                'signal_level': cell(5),
                'sample_text': cell(6),
                'primary': cell(7),
                'secondary': cell(8),
                'primary_raw': raw(7),
                'secondary_raw': raw(8),
                'status': cell(9),
            })
        return rows