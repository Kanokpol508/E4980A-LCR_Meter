# กล่องสำหรับกรอกค่าพารามิเตอร์ต่างๆ เช่น ความถี่, แรงดัน, โหมดสแกน

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QGridLayout,
                             QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QHBoxLayout,
                             QSizePolicy, QLineEdit, QCheckBox, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from utils.helpers import NoScrollComboBox, NoScrollSpinBox, NoScrollDoubleSpinBox

# ความกว้างมาตรฐานของช่องกรอกค่าตัวเลขสั้นๆ (ความถี่ / แรงดัน)
# (ลดลงจากเดิมเพื่อคืนพื้นที่ฝั่งซ้ายให้แคบลง เอาไปเพิ่มพื้นที่ Output ฝั่งขวา)
FREQ_FIELD_WIDTH = 135
VOLT_FIELD_WIDTH = 80
# ความกว้างช่องกรอกตัวเลข "จำนวนครั้ง" (Samples / Discard) ซึ่งเป็นเลขหลักเดียว-4 หลัก
# ไม่จำเป็นต้องกว้างเท่าช่องความถี่ (สูงสุด 7 หลัก) จึงแยกค่าคงที่ให้แคบกว่า
COUNT_FIELD_WIDTH = 111

# จำนวนค่าแรกที่โปรแกรม "ทิ้ง" อัตโนมัติเสมอ ก่อนเริ่มเก็บค่าไปคำนวณสถิติจริง
# (เดิมเป็นช่องให้ผู้ใช้กรอกเอง 0-5 ครั้ง ตอนนี้ล็อกเป็นค่าคงที่ ผู้ใช้ไม่ต้องกรอก/ตั้งค่าเอง
#  แต่ยังคงทำงานอยู่เบื้องหลังเหมือนเดิมทุกโหมด SINGLE/SWEEP/LIST)
DISCARD_FIRST_COUNT = 3


class CleanDoubleSpinBox(NoScrollDoubleSpinBox):
    def textFromValue(self, val):
        # โชว์ตัวเลขเต็ม ไม่มีย่อ (k, M) และตัดทศนิยม .00 ด้านหลังทิ้ง
        text = f"{val:.{self.decimals()}f}"
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        return text


def _make_row(label_text, widget, unit_text=None):
    """สร้างแถว: [หัวข้อ:] [ช่องกรอก/dropdown (ขยายเต็มที่)] [หน่วย (ถ้ามี)]"""
    row = QHBoxLayout()
    row.addWidget(QLabel(label_text))
    row.addWidget(widget, stretch=1)
    if unit_text:
        row.addWidget(QLabel(unit_text))
    return row


def _make_fixed_row(label_text, widget, unit_text=None, width=FREQ_FIELD_WIDTH):
    """สร้างแถว: [หัวข้อ:] [ช่องกรอก ความกว้างคงที่เป๊ะๆ ไม่ว่าตัวเลขข้างในจะสั้นหรือยาว] [หน่วย (ถ้ามี)] ...พื้นที่ว่าง"""
    widget.setFixedWidth(width)
    row = QHBoxLayout()
    row.addWidget(QLabel(label_text))
    row.addWidget(widget)
    if unit_text:
        row.addWidget(QLabel(unit_text))
    row.addStretch()
    return row


class FrequencyListWidget(QWidget):
    """
    ช่องกรอกรายการความถี่แบบทีละแถว (แทนวิธีพิมพ์คั่นด้วย comma แบบเดิม)
    - เริ่มต้นมี 2 แถวเสมอ (ความถี่ที่ 1, 2) ลบไม่ได้ ต้องมีอย่างน้อย 2 จุด
    - กด "เพิ่มรายการความถี่" เพื่อเพิ่มแถวใหม่ได้เรื่อยๆ แถวที่เพิ่มมา (ที่ 3 ขึ้นไป) มีปุ่ม "X" ลบได้
    - มี .text() คืนค่าเป็น string คั่น comma เหมือน QLineEdit เดิม เพื่อให้โค้ดส่วนอื่น
      (validate_freq_list, start_measurement ใน app_controller.py) ใช้งานต่อได้โดยไม่ต้องแก้
    - มีข้อความเตือนในตัว (ใต้แถวความถี่ล่าสุด เหนือปุ่ม "เพิ่มรายการความถี่") กรณีกรอกไม่ครบทุกช่อง
      หรือกรอกความถี่เกินสเปคเครื่อง (20 Hz - 2,000,000 Hz)
    """
    freq_changed = pyqtSignal()

    MIN_ROWS = 2
    MIN_FREQ = 20.0
    MAX_FREQ = 2_000_000.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []  # each: {'container': QWidget, 'input': QLineEdit, 'label': QLabel}

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(6)
        main_layout.addLayout(self.rows_layout)

        # ข้อความเตือน: กรอกไม่ครบทุกช่อง / ค่าเกินสเปคเครื่อง
        # วางไว้ใต้แถวความถี่ล่าสุด เหนือปุ่ม "เพิ่มรายการความถี่" ตามที่ต้องการ
        self.lbl_incomplete = QLabel("")
        self.lbl_incomplete.setWordWrap(True)
        self.lbl_incomplete.setStyleSheet("color: #D2544B; font-weight: bold; font-size: 11px;")
        self.lbl_incomplete.setVisible(False)
        main_layout.addWidget(self.lbl_incomplete)

        # ปุ่มเพิ่มรายการความถี่ - เปลี่ยนจาก "+" วงกลมเป็นปุ่มข้อความ (สีเขียวเหมือนเดิม)
        self.btn_add = QPushButton("+ Add Frequency")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.setStyleSheet(
            "QPushButton { background-color: #A8E6C1; color: #14532D; border-radius: 6px; "
            "font-weight: bold; font-size: 13px; padding: 4px 14px; border: 1px solid #7FD9A0; }"
            "QPushButton:hover { background-color: #7FD9A0; }"
        )
        self.btn_add.clicked.connect(self.add_row)

        h_add = QHBoxLayout()
        h_add.addWidget(self.btn_add)
        h_add.addStretch()
        main_layout.addLayout(h_add)

        # เชื่อมสัญญาณให้เช็คความครบถ้วน/ช่วงค่าใหม่ทุกครั้งที่มีการแก้ไขรายการ
        self.freq_changed.connect(self._check_and_warn)

        # เริ่มต้นด้วย 2 แถวเสมอ (ลบไม่ได้)
        self.add_row()
        self.add_row()

    def add_row(self):
        index = len(self._rows) + 1

        row_container = QWidget()
        row_layout = QHBoxLayout(row_container)
        row_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(f"Frequency {index}")
        lbl.setFixedWidth(95)

        input_field = QLineEdit()
        input_field.setFixedWidth(FREQ_FIELD_WIDTH)
        # จำกัดช่วงค่าตามสเปคเครื่อง E4980A: 20 Hz - 2,000,000 Hz (2 MHz)
        # ใช้ StandardNotation แทน ScientificNotation เพราะ QDoubleValidator
        # ของ Qt มีบั๊กที่รู้จักกันดี คือไม่บังคับค่า top/bottom อย่างเข้มงวดตอนอยู่โหมด
        # ScientificNotation (ยังพิมพ์เกินได้) จึงต้องดักซ้ำด้วย _on_freq_text_changed ด้านล่างด้วย
        validator = QDoubleValidator(self.MIN_FREQ, self.MAX_FREQ, 6)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        input_field.setValidator(validator)
        input_field.textChanged.connect(lambda _text, w=input_field: self._on_freq_text_changed(w))

        row_layout.addWidget(lbl)
        row_layout.addWidget(input_field)
        row_layout.addWidget(QLabel("Hz"))

        # ลบได้เฉพาะแถวที่ 3 ขึ้นไป (2 แถวแรกบังคับให้มีอย่างน้อยเสมอ)
        if index > self.MIN_ROWS:
            btn_del = QPushButton("X")
            btn_del.setFixedSize(32, 32)
            btn_del.setStyleSheet(
                "QPushButton { background-color: #FDAFAB; color: #7A1F1B; border-radius: 16px; "
                "font-weight: bold; font-size: 11px; border: 1px solid #F58E89;}"
                "QPushButton:hover { background-color: #F58E89; }"
            )
            btn_del.clicked.connect(lambda: self.remove_row(row_container))
            row_layout.addWidget(btn_del)

        row_layout.addStretch()

        self.rows_layout.addWidget(row_container)
        self._rows.append({'container': row_container, 'input': input_field, 'label': lbl})
        self.freq_changed.emit()

    def _on_freq_text_changed(self, field: QLineEdit):
        """เรียกทุกครั้งที่มีการพิมพ์/แก้ไข/วางข้อความในช่องความถี่ช่องใดช่องหนึ่ง
        ถ้าค่าที่ได้เกิน MAX_FREQ (2,000,000 Hz) จะตัดตัวอักษรท้ายสุดทิ้งไปเรื่อยๆ
        จนกว่าค่าจะกลับมาอยู่ในช่วงที่อนุญาต (ป้องกันไม่ให้พิมพ์เกินได้ตั้งแต่ต้น
        ไม่ต้องรอ validate ตอนกด Start) จากนั้นค่อย emit freq_changed ให้ตรวจสอบต่อ"""
        text = field.text()
        if text:
            try:
                val = float(text)
                if val > self.MAX_FREQ:
                    cursor_pos = field.cursorPosition()
                    trimmed = text
                    while trimmed:
                        trimmed = trimmed[:-1]
                        if trimmed == "":
                            break
                        try:
                            if float(trimmed) <= self.MAX_FREQ:
                                break
                        except ValueError:
                            break
                    field.blockSignals(True)
                    field.setText(trimmed)
                    field.setCursorPosition(min(cursor_pos, len(trimmed)))
                    field.blockSignals(False)
            except ValueError:
                pass  # ข้อความระหว่างพิมพ์ที่ยังแปลงเป็นตัวเลขไม่ได้ (เช่น "-", ".") ปล่อยผ่านไปก่อน
        self.freq_changed.emit()

    def remove_row(self, row_container):
        for i, r in enumerate(self._rows):
            if r['container'] is row_container:
                self.rows_layout.removeWidget(row_container)
                row_container.deleteLater()
                self._rows.pop(i)
                break
        self._renumber_labels()
        self.freq_changed.emit()

    def _renumber_labels(self):
        for i, r in enumerate(self._rows):
            r['label'].setText(f"Frequency {i + 1}")

    def _check_and_warn(self):
        """ตรวจสอบว่ารายการความถี่กรอกครบทุกช่อง (ไม่มีช่องว่างค้าง) และค่าที่กรอก
        อยู่ในช่วงสเปคเครื่องหรือไม่ แล้วอัปเดตข้อความเตือนใต้แถวล่าสุด (เหนือปุ่มเพิ่มรายการ)
        คืนค่า True ถ้าไม่มีปัญหาใดๆ เลย"""
        filled = [r for r in self._rows if r['input'].text().strip() != ""]
        empty = [r for r in self._rows if r['input'].text().strip() == ""]

        problems = []

        # มีช่องว่างค้างอยู่ (ไม่ว่าจะยังไม่กรอกเลยสักช่อง หรือกรอกบางช่องแต่ไม่ครบ)
        if empty:
            if len(self._rows) > self.MIN_ROWS:
                # มีแถวเกิน 2 แถวขั้นต่ำ -> ลบแถวที่ไม่ใช้ทิ้งได้ จึงเสนอตัวเลือกนี้เพิ่ม
                problems.append("กรุณากรอกให้ครบทุกช่อง หรือลบช่องที่ไม่ใช้ทิ้ง")
            else:
                # มีแค่ 2 แถวขั้นต่ำ (ลบไม่ได้อยู่แล้ว) -> ต้องกรอกให้ครบเท่านั้น
                problems.append("กรุณากรอกให้ครบทุกช่อง")

        # ค่าที่กรอกเกินสเปคเครื่อง (เผื่อกรณี validator ปล่อยผ่านค่าที่กำลังพิมพ์อยู่ชั่วขณะ)
        out_of_range = False
        for r in filled:
            try:
                val = float(r['input'].text().strip())
                if val < self.MIN_FREQ or val > self.MAX_FREQ:
                    out_of_range = True
            except ValueError:
                pass
        if out_of_range:
            problems.append(f"ความถี่ต้องอยู่ในช่วง {self.MIN_FREQ:.0f} Hz - {self.MAX_FREQ:,.0f} Hz (2 MHz) เท่านั้น")

        if problems:
            self.lbl_incomplete.setText("⚠️ " + "\n".join(problems))
            self.lbl_incomplete.setVisible(True)
            return False

        self.lbl_incomplete.setText("")
        self.lbl_incomplete.setVisible(False)
        return True

    def is_valid(self) -> bool:
        """ให้ภายนอก (app_controller.py) เรียกเช็คว่ารายการความถี่ผ่านทุกเงื่อนไขหรือไม่
        (กรอกครบ + อยู่ในช่วงสเปค) ก่อนอนุญาตให้กด Start"""
        return self._check_and_warn()

    def get_frequencies(self) -> list:
        """คืนค่าเป็น list ของ float (ข้ามช่องว่าง/พิมพ์ผิดที่แปลงไม่ได้)"""
        freqs = []
        for r in self._rows:
            text = r['input'].text().strip()
            if not text:
                continue
            try:
                freqs.append(float(text))
            except ValueError:
                continue
        return freqs

    def text(self) -> str:
        """Mimic QLineEdit.text() -> คืนค่าเป็น string คั่น comma เพื่อให้ใช้กับ
        parser เดิม (MeasurementWorker._parse_freq_list) ได้โดยไม่ต้องแก้โค้ดที่อื่น"""
        return ",".join(str(f) for f in self.get_frequencies())

    def set_frequencies(self, freqs: list):
        """ตั้งค่ารายการความถี่ทั้งหมดใหม่ (ใช้ตอน Open Save เพื่อคืนค่า Input เดิม)
        ปรับจำนวนแถวให้เท่ากับ freqs ที่ส่งเข้ามาโดยอัตโนมัติ (เพิ่ม/ลบแถวให้พอดี)
        แล้วค่อยใส่ค่าแต่ละแถว ก่อนแจ้งเตือน freq_changed ให้ validate อีกครั้ง"""
        freqs = [f for f in (freqs or [])]
        while len(freqs) < self.MIN_ROWS:
            freqs.append(None)

        while len(self._rows) < len(freqs):
            self.add_row()
        while len(self._rows) > len(freqs):
            self.remove_row(self._rows[-1]['container'])

        for row, val in zip(self._rows, freqs):
            row['input'].blockSignals(True)
            row['input'].setText("" if val is None else self._format_freq(val))
            row['input'].blockSignals(False)

        self.freq_changed.emit()

    @staticmethod
    def _format_freq(val) -> str:
        try:
            f = float(val)
            return str(int(f)) if f.is_integer() else str(f)
        except (TypeError, ValueError):
            return str(val)


class InputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ==========================================================
        # 1. ประเภทการวัด (Measurement Type)
        # ใช้ QGridLayout เพื่อให้ทั้ง 2 dropdown อยู่คอลัมน์เดียวกัน
        # -> ความกว้างเท่ากันและชิดตรงกันโดยอัตโนมัติ
        # ==========================================================
        self.group_prop = QGroupBox("Measurement Type")
        grid_prop = QGridLayout()
        grid_prop.setVerticalSpacing(8)
        grid_prop.setHorizontalSpacing(6)
        grid_prop.setColumnStretch(1, 1)

        self.combo_prop_group = NoScrollComboBox()
        self.combo_scpi_mode = NoScrollComboBox()
        self.edit_nominal_value = QLineEdit()
        self.edit_nominal_value.setPlaceholderText("กรอก Nominal Value (ถ้ามี)")

        lbl_prop_group = QLabel("Parameter Group:")
        lbl_scpi_mode = QLabel("FUNC:")
        lbl_nominal_value = QLabel("Nominal Value:")
        lbl_prop_group.setMaximumWidth(120)
        lbl_scpi_mode.setMaximumWidth(120)
        lbl_nominal_value.setMaximumWidth(120)

        grid_prop.addWidget(lbl_prop_group, 0, 0)
        grid_prop.addWidget(self.combo_prop_group, 0, 1)
        grid_prop.addWidget(lbl_scpi_mode, 1, 0)
        grid_prop.addWidget(self.combo_scpi_mode, 1, 1)
        grid_prop.addWidget(lbl_nominal_value, 2, 0)
        grid_prop.addWidget(self.edit_nominal_value, 2, 1)

        self.group_prop.setLayout(grid_prop)

        # ==========================================================
        # 2. ตั้งค่าความถี่ (Frequency Settings)
        # ==========================================================
        self.group_mode = QGroupBox("Frequency Settings")
        v_mode = QVBoxLayout()
        v_mode.setSpacing(10)

        # --- Dropdown เลือกโหมดการวัด ---
        v_mode.addWidget(QLabel("Select Measurement Mode:"))
        self.combo_run_mode = NoScrollComboBox()
        self.combo_run_mode.addItem("Single Frequency (โหมดวัดจุดเดียว)", userData="SINGLE")
        self.combo_run_mode.addItem("Sweep Frequency (โหมดสแกนความถี่)", userData="SWEEP")
        self.combo_run_mode.addItem("Frequency List (โหมดรายการความถี่)", userData="LIST")
        self.combo_run_mode.setCurrentIndex(0)  # ค่าเริ่มต้น = Single
        v_mode.addWidget(self.combo_run_mode)

        # --- เนื้อหาย่อย: วัดจุดเดียว (SINGLE) ---
        # แยกเป็น 2 QGridLayout อิสระจากกัน (เหมือนวิธีที่ใช้กับ SWEEP/LIST):
        # 1) Frequency (ใช้ FREQ_FIELD_WIDTH ซึ่งกว้างกว่า เพราะต้องรองรับเลขได้ถึง 7 หลัก)
        # 2) Samples Count / Discard First / Total Readings (ใช้ COUNT_FIELD_WIDTH แคบกว่า)
        # เหตุผลที่ต้องแยก: ถ้าอยู่ grid เดียวกัน คอลัมน์ช่องกรอกจะถูกบังคับให้กว้างเท่า
        # ช่องที่กว้างที่สุดในคอลัมน์นั้นเสมอ (Frequency, 110px) ทำให้ช่อง Samples/Discard
        # ที่ตั้ง fixed width แคบกว่า (85px) ถูกจัดชิดซ้ายแล้วเหลือช่องว่างก่อนถึงหน่วย "Times"
        # (นี่คือสาเหตุจริงของช่องว่างที่ยังเห็นอยู่ก่อนหน้านี้)
        self.widget_freq_single = QWidget()
        v_single = QVBoxLayout(self.widget_freq_single)
        v_single.setContentsMargins(0, 0, 0, 0)
        v_single.setSpacing(14)

        # --- กลุ่ม 1: Frequency ---
        grid_single_freq = QGridLayout()
        grid_single_freq.setVerticalSpacing(8)
        grid_single_freq.setHorizontalSpacing(6)

        self.input_freq = CleanDoubleSpinBox()
        self.input_freq.setRange(20.0, 2000000.0)
        self.input_freq.setDecimals(2)
        self.input_freq.setSingleStep(100)
        self.input_freq.setValue(1000.0)
        self.input_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        grid_single_freq.addWidget(QLabel("Frequency:"), 0, 0)
        grid_single_freq.addWidget(self.input_freq, 0, 1)
        grid_single_freq.addWidget(QLabel("Hz"), 0, 2)
        grid_single_freq.setColumnStretch(3, 1)

        v_single.addLayout(grid_single_freq)

        # --- กลุ่ม 2: Samples Count / Discard First / Total Readings ---
        grid_single_samples = QGridLayout()
        grid_single_samples.setVerticalSpacing(8)
        grid_single_samples.setHorizontalSpacing(6)

        # จำนวนครั้งที่วัดซ้ำ (N) ใน SINGLE mode
        self.input_n_single = NoScrollSpinBox()
        self.input_n_single.setRange(1, 9999)
        self.input_n_single.setValue(5)
        self.input_n_single.setFixedWidth(COUNT_FIELD_WIDTH)

        # เดิมเป็นช่อง "Discard First" ให้ผู้ใช้กรอกเอง (SINGLE mode) — เอาช่องกรอก
        # ออกแล้ว โปรแกรมทิ้งค่าแรก DISCARD_FIRST_COUNT (=3) ครั้งให้อัตโนมัติเสมอเบื้องหลัง
        # (ทำงานเฉพาะครั้งแรกของ session เหมือนเดิม) ผู้ใช้ไม่ต้องตั้งค่าเอง แต่ยังเห็นผลรวม
        # ผ่าน Label "Total Readings" ด้านล่างว่ามีการ Discard อยู่จริง

        # Label แสดงจำนวนรอบวัดทั้งหมด = Discard + Readings (คล้ายกับ "จำนวนจุดที่ได้" ของ SWEEP)
        self.lbl_total_rounds_single = QLabel("-")
        self.lbl_total_rounds_single.setStyleSheet("color: #5B7FB5; font-weight: bold;")

        grid_single_samples.addWidget(QLabel("Samples Count:"), 0, 0)
        grid_single_samples.addWidget(self.input_n_single, 0, 1)
        grid_single_samples.addWidget(QLabel("Times"), 0, 2)

        grid_single_samples.addWidget(QLabel("Total Readings:"), 1, 0)
        # colSpan=3 (คร่อมคอลัมน์ 1-3): เพราะข้อความในนี้ยาว (เช่น
        # "11 Times (Discard 3 + Measure 10)") ถ้าใส่แค่คอลัมน์ 1 เฉยๆ จะไปบังคับ
        # ให้คอลัมน์ 1 กว้างตามข้อความยาวนี้ไปด้วย ทำให้ช่อง Samples ที่แคบกว่า
        # ถูกจัดชิดซ้ายแล้วเหลือช่องว่างค้างก่อนถึงหน่วย "Times" (สาเหตุของปัญหาที่เคยเห็น)
        grid_single_samples.addWidget(self.lbl_total_rounds_single, 1, 1, 1, 3)

        grid_single_samples.setColumnStretch(3, 1)

        v_single.addLayout(grid_single_samples)

        # เชื่อมสัญญาณเพื่ออัปเดต label ทุกครั้งที่ค่าเปลี่ยน
        # (signal connect และการคำนวณจริงอยู่ใน app_controller.py เพื่อรวมไว้กับ
        #  update_calculated_points ของ SWEEP ให้อยู่ที่เดียวกัน)

        v_mode.addWidget(self.widget_freq_single)

        # --- เนื้อหาย่อย: สแกนความถี่ Linear (SWEEP) ---
        # แยกเป็น 2 QGridLayout อิสระจากกัน:
        # 1) ความถี่เริ่มต้น/สิ้นสุด/ค่าเพิ่มต่อจุด/จำนวนจุดที่ได้ (คอลัมน์ชิดกันเอง)
        # 2) จำนวนรอบวัดซ้ำ/ทิ้งค่าตัวอย่างแรก/รวมรอบวัด (คอลัมน์ชิดกันเอง แยกจากกลุ่มบน)
        # เพื่อไม่ให้ความกว้างคอลัมน์ของทั้งสองกลุ่มต้องเท่ากันเหมือนตอนอยู่ grid เดียวกัน
        self.widget_sweep = QWidget()
        v_sweep = QVBoxLayout(self.widget_sweep)
        v_sweep.setContentsMargins(0, 0, 0, 0)
        v_sweep.setSpacing(14)

        # --- กลุ่ม 1: ความถี่เริ่มต้น / สิ้นสุด / ค่าเพิ่มต่อจุด / จำนวนจุดที่ได้ ---
        grid_sweep = QGridLayout()
        grid_sweep.setVerticalSpacing(8)
        grid_sweep.setHorizontalSpacing(6)

        self.input_start_freq = CleanDoubleSpinBox()
        self.input_start_freq.setRange(20.0, 2000000.0)
        self.input_start_freq.setDecimals(2)
        self.input_start_freq.setSingleStep(100)
        self.input_start_freq.setValue(100.0)
        self.input_start_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        self.input_stop_freq = CleanDoubleSpinBox()
        self.input_stop_freq.setRange(20.0, 2000000.0)
        self.input_stop_freq.setDecimals(2)
        self.input_stop_freq.setSingleStep(100)
        self.input_stop_freq.setValue(1000000.0)
        self.input_stop_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        self.input_step_freq = CleanDoubleSpinBox()
        self.input_step_freq.setRange(0.01, 1999980.0)
        self.input_step_freq.setDecimals(2)
        self.input_step_freq.setSingleStep(100)
        self.input_step_freq.setValue(20000.0)
        self.input_step_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        self.lbl_calculated_points = QLabel("-")
        self.lbl_calculated_points.setStyleSheet("color: #5B7FB5; font-weight: bold;")

        grid_sweep.addWidget(QLabel("Start Frequency:"), 0, 0)
        grid_sweep.addWidget(self.input_start_freq, 0, 1)
        grid_sweep.addWidget(QLabel("Hz"), 0, 2)

        grid_sweep.addWidget(QLabel("Stop Frequency:"), 1, 0)
        grid_sweep.addWidget(self.input_stop_freq, 1, 1)
        grid_sweep.addWidget(QLabel("Hz"), 1, 2)

        grid_sweep.addWidget(QLabel("Step Size:"), 2, 0)
        grid_sweep.addWidget(self.input_step_freq, 2, 1)
        grid_sweep.addWidget(QLabel("Hz"), 2, 2)

        grid_sweep.addWidget(QLabel("Points Count:"), 3, 0)
        grid_sweep.addWidget(self.lbl_calculated_points, 3, 1)

        grid_sweep.setColumnStretch(3, 1)  # เผื่อพื้นที่ว่างด้านขวาสุด

        v_sweep.addLayout(grid_sweep)

        # --- กลุ่ม 2: จำนวนรอบวัดซ้ำต่อความถี่ + ทิ้งค่าตัวอย่างแรกสุด (เหมือนโหมด LIST) ---
        grid_sweep_samples = QGridLayout()
        grid_sweep_samples.setVerticalSpacing(8)
        grid_sweep_samples.setHorizontalSpacing(6)
        # หมายเหตุ: เดิมกลุ่มนี้ไม่ได้ตั้ง setColumnStretch เลย ทำให้ Qt กระจายพื้นที่ว่าง
        # ให้ทุกคอลัมน์เท่าๆ กัน (รวมคอลัมน์ระหว่างช่องกรอกกับหน่วย "Times") จึงดูห่างเกินไป
        # ต้องดันพื้นที่ว่างทั้งหมดไปไว้คอลัมน์ขวาสุดเหมือน grid_sweep ด้านบนแทน
        grid_sweep_samples.setColumnStretch(3, 1)

        self.input_samples_sweep = NoScrollSpinBox()
        self.input_samples_sweep.setRange(1, 999)
        self.input_samples_sweep.setValue(5)
        self.input_samples_sweep.setFixedWidth(COUNT_FIELD_WIDTH)

        # เดิมเป็นช่อง "Discard First Reading" ให้ผู้ใช้กรอกเอง — เอาช่องกรอกออก
        # โปรแกรมทิ้งค่าแรก DISCARD_FIRST_COUNT (=3) ค่าแรกของทุกความถี่ให้อัตโนมัติเสมอ
        # เบื้องหลัง ผู้ใช้ไม่ต้องตั้งค่าเอง แต่ยังเห็นผลรวมผ่าน Label "Total Readings" ด้านล่าง

        self.lbl_total_rounds_sweep = QLabel("-")
        self.lbl_total_rounds_sweep.setStyleSheet("color: #5B7FB5; font-weight: bold;")

        grid_sweep_samples.addWidget(QLabel("Samples per Sweep:"), 0, 0)
        grid_sweep_samples.addWidget(self.input_samples_sweep, 0, 1)
        grid_sweep_samples.addWidget(QLabel("Times"), 0, 2)

        grid_sweep_samples.addWidget(QLabel("Total Readings / Frequency:"), 1, 0)
        grid_sweep_samples.addWidget(self.lbl_total_rounds_sweep, 1, 1, 1, 3)

        v_sweep.addLayout(grid_sweep_samples)

        v_mode.addWidget(self.widget_sweep)

        # --- เนื้อหาย่อย: รายการความถี่ + Samples ต่อจุด (LIST) - คงรูปแบบเดิม ---
        self.widget_list = QWidget()
        v_list = QVBoxLayout(self.widget_list)
        v_list.setContentsMargins(0, 0, 0, 0)
        v_list.setSpacing(10)

        v_list.addWidget(QLabel("Frequency List:"))
        self.input_freq_list = FrequencyListWidget()
        v_list.addWidget(self.input_freq_list)

        grid_list_nums = QGridLayout()
        grid_list_nums.setVerticalSpacing(8)
        grid_list_nums.setHorizontalSpacing(6)
        # เดิมตั้ง stretch ไว้ที่คอลัมน์ 2 (คอลัมน์ label "Times") ทำให้พื้นที่ว่างไปแทรก
        # อยู่ระหว่างช่องกรอกกับ "Times" เอง (ห่างเกินไป) ต้องย้ายไปคอลัมน์ 3 (ขวาสุด) แทน
        # เหมือนกลุ่ม grid_sweep / grid_single เพื่อให้ช่องกรอกชิดหน่วยพอดี
        grid_list_nums.setColumnStretch(3, 1)

        self.input_samples = NoScrollSpinBox()
        self.input_samples.setRange(1, 999)
        self.input_samples.setValue(5)

        # เดิมเป็นช่อง "Discard First Reading" ให้ผู้ใช้กรอกเอง — เอาช่องกรอกออก
        # โปรแกรมทิ้งค่าแรก DISCARD_FIRST_COUNT (=3) ค่าแรกของทุกความถี่ให้อัตโนมัติเสมอ
        # เบื้องหลัง ผู้ใช้ไม่ต้องตั้งค่าเอง แต่ยังเห็นผลรวมผ่าน Label "Total Readings" ด้านล่าง

        # บังคับให้ช่องกว้างเท่ากับช่องอื่นๆ ในกลุ่มเดียวกัน (แคบกว่าช่องความถี่ปกติเล็กน้อย
        # เพราะค่าที่กรอกเป็นแค่จำนวนครั้ง ไม่ใช่ตัวเลขความถี่ที่อาจยาวหลักล้าน)
        self.input_samples.setFixedWidth(COUNT_FIELD_WIDTH)

        # Label แสดงจำนวนรอบวัดทั้งหมดต่อ 1 ความถี่ = Discard + Samples
        self.lbl_total_rounds_list = QLabel("-")
        self.lbl_total_rounds_list.setStyleSheet("color: #5B7FB5; font-weight: bold;")

        grid_list_nums.addWidget(QLabel("Samples per Sweep:"), 0, 0)
        grid_list_nums.addWidget(self.input_samples, 0, 1)
        grid_list_nums.addWidget(QLabel("Times"), 0, 2)

        grid_list_nums.addWidget(QLabel("Total Readings / Frequency:"), 1, 0)
        grid_list_nums.addWidget(self.lbl_total_rounds_list, 1, 1, 1, 3)

        # เชื่อมสัญญาณเพื่ออัปเดต label ทุกครั้งที่ค่าเปลี่ยน
        # (signal connect และการคำนวณจริงอยู่ใน app_controller.py เพื่อรวมไว้กับ
        #  update_calculated_points ของ SWEEP ให้อยู่ที่เดียวกัน)

        v_list.addLayout(grid_list_nums)

        v_mode.addWidget(self.widget_list)

        self.group_mode.setLayout(v_mode)

        # ==========================================================
        # 3. สัญญาณทดสอบ (Test Signal)
        # ==========================================================
        self.group_signal = QGroupBox("Test Signal")
        v_signal = QVBoxLayout()
        v_signal.setSpacing(8)

        self.input_volt = CleanDoubleSpinBox()
        # ช่วงกว้างสุดเผื่อไว้ตอนสร้าง widget (0.1mV ต่ำสุดฝั่ง Voltage - 20V สูงสุดฝั่ง Voltage)
        # ค่า Min/Max จริงตามโหมด V/A และความถี่ปัจจุบัน จะถูกกำหนดโดย update_hardware_limits()
        # อ้างอิงคู่มือ E4980A Option 001: Table 3-12 (Voltage 0.1mV-20Vrms, ≤15Vrms ถ้า Freq>1MHz)
        # และ Table 3-13 (Current 50uA-100mArms)
        self.input_volt.setRange(0.00005, 20.0)
        self.input_volt.setDecimals(4)
        self.input_volt.setSingleStep(0.1)
        self.input_volt.setValue(1.0)
        self.input_volt.setFixedWidth(VOLT_FIELD_WIDTH)

        # Dropdown หน่วย: V (Voltage) หรือ A (Current)
        self.combo_level_mode = NoScrollComboBox()
        self.combo_level_mode.addItem("Voltage(V)", userData="Voltage")
        self.combo_level_mode.addItem("Current(A)", userData="Current")
        self.combo_level_mode.setFixedWidth(135)

        # ALC (Automatic Level Control) — [แก้ไข] ย้ายมาอยู่แถวเดียวกับ SpinBox + Dropdown
        # (ข้าง Dropdown หน่วย) แทนที่จะแยกอยู่คนละแถวด้านล่าง และตัดชื่อเต็ม
        # "(Automatic Level Control)" ออก เหลือแค่ "Enable ALC" (คำอธิบายเต็มยังอยู่ใน tooltip)
        self.chk_alc = QCheckBox("Enable ALC")
        self.chk_alc.setToolTip(
            "ALC ทำให้ระดับสัญญาณ ณ จุดที่ชิ้นงาน เท่ากับค่าที่ตั้งไว้จริงๆ\n"
            "แนะนำเปิดเมื่อวัด Inductor ด้วยโหมด A\n"
            "เพื่อให้กระแสทดสอบคงที่ตลอดการวัดทุกความถี่"
        )
        # เปลี่ยนข้อความ + สีเป็นเขียวพร้อมอิโมจิ ✅ เมื่อติ๊กเปิดใช้งาน เพื่อให้เห็นชัดเจนว่า
        # ALC กำลังทำงานอยู่ (ไม่ใช่แค่ดูจากติ๊กถูกเฉยๆ)
        self.chk_alc.toggled.connect(self._on_alc_toggled)
        self._on_alc_toggled(self.chk_alc.isChecked())

        # Label อยู่แถวบน, SpinBox + Dropdown + Enable ALC อยู่แถวล่างเดียวกัน
        v_signal.addWidget(QLabel("Signal Level:"))

        h_level = QHBoxLayout()
        h_level.addWidget(self.input_volt)
        h_level.addWidget(self.combo_level_mode)
        h_level.addWidget(self.chk_alc)
        h_level.addStretch()
        v_signal.addLayout(h_level)

        v_signal.addStretch()
        self.group_signal.setLayout(v_signal)

        # ==========================================================
        # 4. ฮาร์ดแวร์และเวลา (Hardware & Timing)
        # ใช้ QGridLayout เพื่อให้ทั้ง 4 ช่อง (dropdown/spinbox) อยู่
        # คอลัมน์เดียวกัน -> ความกว้างเท่ากันและชิดตรงกันโดยอัตโนมัติ
        # ==========================================================
        self.group_hw = QGroupBox("Hardware & Timing")
        grid_hw = QGridLayout()
        grid_hw.setVerticalSpacing(8)
        grid_hw.setHorizontalSpacing(6)
        grid_hw.setColumnStretch(1, 1)

        self.combo_time = NoScrollComboBox()
        self.combo_time.addItems(["SHORT", "MEDIUM", "LONG"])
        self.combo_time.setCurrentText("LONG")  # ค่าเริ่มต้น = LONG (ความแม่นยำสูงสุด)

        self.input_avg = NoScrollSpinBox()
        self.input_avg.setRange(1, 256)
        self.input_avg.setValue(10)

        self.combo_cable = NoScrollComboBox()
        self.combo_cable.addItems(["0 m", "1 m", "2 m", "4 m"])
        self.combo_cable.setCurrentText("1 m")

        self.combo_range = NoScrollComboBox()
        self.combo_range.addItem("AUTO", userData="AUTO")
        # 100 mΩ ใช้ได้เฉพาะเครื่องที่มี Option 001 และห้ามใช้เมื่อ Test Signal Level <= 2V (คู่มือหน้า 51 footnote 1)
        self.combo_range.addItem("0.1 Ω", userData=0.1)
        self.combo_range.addItem("1 Ω", userData=1)
        self.combo_range.addItem("10 Ω", userData=10)
        self.combo_range.addItem("100 Ω", userData=100)
        self.combo_range.addItem("300 Ω", userData=300)
        self.combo_range.addItem("1000 Ω", userData=1000)
        self.combo_range.addItem("3000 Ω", userData=3000)
        self.combo_range.addItem("10000 Ω", userData=10000)
        self.combo_range.addItem("30000 Ω", userData=30000)
        self.combo_range.addItem("100000 Ω", userData=100000)

        grid_hw.addWidget(QLabel("Meas Time:"), 0, 0)
        grid_hw.addWidget(self.combo_time, 0, 1)
        grid_hw.addWidget(QLabel("Averaging(AVG):"), 1, 0)
        grid_hw.addWidget(self.input_avg, 1, 1)
        grid_hw.addWidget(QLabel("Cable Length:"), 2, 0)
        grid_hw.addWidget(self.combo_cable, 2, 1)
        grid_hw.addWidget(QLabel("Range:"), 3, 0)
        grid_hw.addWidget(self.combo_range, 3, 1)

        self.group_hw.setLayout(grid_hw)

        # ==========================================================
        # ประกอบ Layout
        # ==========================================================
        layout.addWidget(self.group_prop)
        layout.addWidget(self.group_mode)
        layout.addWidget(self.group_signal)
        layout.addWidget(self.group_hw)

        layout.addStretch()

    def _on_alc_toggled(self, checked: bool):
        """เปลี่ยนข้อความ + สี checkbox 'Enable ALC' เมื่อผู้ใช้ติ๊กเปิด/ปิด
        - เปิด (checked=True): ข้อความสีเขียว + อิโมจิ ✅ ต่อท้าย เพื่อให้เห็นชัดว่า ALC กำลังทำงานอยู่
        - ปิด (checked=False): กลับเป็นข้อความปกติ ไม่มีสี/อิโมจิ
        กำหนด QCheckBox:disabled ไว้ในสไตล์นี้ด้วยเสมอ (สีเทาเดียวกับ assets/styles.qss)
        เพราะ stylesheet ที่ตั้งตรงที่ตัว widget (setStyleSheet) จะมีสิทธิ์เหนือกว่า
        stylesheet ระดับแอปพลิเคชันเสมอ — ถ้าไม่ใส่เงื่อนไข :disabled ไว้เอง ตัวอักษรจะยัง
        เขียวสดค้างอยู่แม้ช่องนี้จะถูกล็อก (setEnabled(False)) ระหว่างกำลังวัด/Correction/
        SINGLE mode session ก็ตาม ทำให้ผู้ใช้เข้าใจผิดว่ายังกดแก้ไขได้อยู่"""
        if checked:
            self.chk_alc.setText("Enable ALC ✅")
            self.chk_alc.setStyleSheet(
                "QCheckBox { color: #2E8B57; font-weight: bold; } "
                "QCheckBox:disabled { color: #A3ADC2; font-weight: normal; }"
            )
        else:
            self.chk_alc.setText("Enable ALC")
            self.chk_alc.setStyleSheet("")