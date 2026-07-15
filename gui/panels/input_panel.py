# กล่องสำหรับกรอกค่าพารามิเตอร์ต่างๆ เช่น ความถี่, แรงดัน, โหมดสแกน

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QGridLayout,
                             QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QHBoxLayout,
                             QSizePolicy, QLineEdit, QCheckBox, QPushButton)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDoubleValidator

# ความกว้างมาตรฐานของช่องกรอกค่าตัวเลขสั้นๆ (ความถี่ / แรงดัน)
FREQ_FIELD_WIDTH = 150
VOLT_FIELD_WIDTH = 90


class CleanDoubleSpinBox(QDoubleSpinBox):
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
        self.lbl_incomplete.setStyleSheet("color: #ff4444; font-weight: bold; font-size: 11px;")
        self.lbl_incomplete.setVisible(False)
        main_layout.addWidget(self.lbl_incomplete)

        # ปุ่มเพิ่มรายการความถี่ - เปลี่ยนจาก "+" วงกลมเป็นปุ่มข้อความ (สีเขียวเหมือนเดิม)
        self.btn_add = QPushButton("+ เพิ่มรายการความถี่")
        self.btn_add.setMinimumHeight(32)
        self.btn_add.setStyleSheet(
            "QPushButton { background-color: #22c55e; color: white; border-radius: 6px; "
            "font-weight: bold; font-size: 13px; padding: 4px 14px; border: 1px solid #16a34a; }"
            "QPushButton:hover { background-color: #16a34a; }"
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

        lbl = QLabel(f"ความถี่ที่ {index}")
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
                "QPushButton { background-color: #ef4444; color: white; border-radius: 16px; "
                "font-weight: bold; font-size: 11px; border: 1px solid #dc2626;}"
                "QPushButton:hover { background-color: #dc2626; }"
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
            r['label'].setText(f"ความถี่ที่ {i + 1}")

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
        self.group_prop = QGroupBox("ประเภทการวัด (Measurement Type)")
        grid_prop = QGridLayout()
        grid_prop.setVerticalSpacing(8)
        grid_prop.setColumnStretch(1, 1)

        self.combo_prop_group = QComboBox()
        self.combo_scpi_mode = QComboBox()

        lbl_prop_group = QLabel("กลุ่มพารามิเตอร์\n(Parameter Group):")
        lbl_scpi_mode = QLabel("โหมดพารามิเตอร์\n(SCPI Mode):")
        lbl_prop_group.setMaximumWidth(120)
        lbl_scpi_mode.setMaximumWidth(120)

        grid_prop.addWidget(lbl_prop_group, 0, 0)
        grid_prop.addWidget(self.combo_prop_group, 0, 1)
        grid_prop.addWidget(lbl_scpi_mode, 1, 0)
        grid_prop.addWidget(self.combo_scpi_mode, 1, 1)

        self.group_prop.setLayout(grid_prop)

        # ==========================================================
        # 2. ตั้งค่าความถี่ (Frequency Settings)
        # ==========================================================
        self.group_mode = QGroupBox("ตั้งค่าความถี่ (Frequency Settings)")
        v_mode = QVBoxLayout()
        v_mode.setSpacing(10)

        # --- Dropdown เลือกโหมดการวัด ---
        v_mode.addWidget(QLabel("เลือกโหมดการวัด (Select Measurement Mode):"))
        self.combo_run_mode = QComboBox()
        self.combo_run_mode.addItem("วัดจุดเดียว (Single Frequency)", userData="SINGLE")
        self.combo_run_mode.addItem("สแกนความถี่ (Sweep Frequency)", userData="SWEEP")
        self.combo_run_mode.addItem("รายการความถี่ (Frequency List)", userData="LIST")
        self.combo_run_mode.setCurrentIndex(0)  # ค่าเริ่มต้น = Single
        v_mode.addWidget(self.combo_run_mode)

        # --- เนื้อหาย่อย: วัดจุดเดียว (SINGLE) ---
        # ใช้ QGridLayout เพื่อให้ช่องกรอกทุกแถว (Frequency / Readings / Discard)
        # เสมอกันในแนวตั้ง (คอลัมน์ spinbox เริ่ม x เดียวกันเป๊ะ)
        self.widget_freq_single = QWidget()
        grid_single = QGridLayout(self.widget_freq_single)
        grid_single.setContentsMargins(0, 0, 0, 0)
        grid_single.setVerticalSpacing(8)

        self.input_freq = CleanDoubleSpinBox()
        self.input_freq.setRange(20.0, 2000000.0)
        self.input_freq.setDecimals(2)
        self.input_freq.setSingleStep(100)
        self.input_freq.setValue(100000.0)
        self.input_freq.setFixedWidth(FREQ_FIELD_WIDTH)

        # จำนวนครั้งที่วัดซ้ำ (N) ใน SINGLE mode
        self.input_n_single = QSpinBox()
        self.input_n_single.setRange(1, 9999)
        self.input_n_single.setValue(10)
        self.input_n_single.setFixedWidth(FREQ_FIELD_WIDTH)
        self.input_n_single.setToolTip(
            "จำนวนครั้งที่วัดซ้ำต่อ 1 ครั้งที่กด Start\n"
            "ยิ่งมาก Type A (ppm) ยิ่งน่าเชื่อถือ\n"
            "แนะนำ: ≥ 10 ครั้ง สำหรับงาน Metrology"
        )

        # Discard First Reading ใน SINGLE mode (ทิ้งค่าแรกหลังตั้งค่าเครื่อง)
        self.input_discard_single = QSpinBox()
        self.input_discard_single.setRange(0, 5)
        self.input_discard_single.setValue(1)
        self.input_discard_single.setFixedWidth(FREQ_FIELD_WIDTH)
        self.input_discard_single.setToolTip(
            "จำนวนครั้งแรกที่วัดแล้วทิ้ง ไม่นำไปคำนวณสถิติ\n"
            "เครื่องต้องใช้เวลาปรับตัวหลังตั้งค่า ค่าแรกๆ อาจยังไม่นิ่ง\n"
            "ทำงานเฉพาะครั้งแรกของ session (กด Start ครั้งที่ 2 เป็นต้นไปไม่ Discard)"
        )

        # Label แสดงจำนวนรอบวัดทั้งหมด = Discard + Readings (คล้ายกับ "จำนวนจุดที่ได้" ของ SWEEP)
        self.lbl_total_rounds_single = QLabel("-")
        self.lbl_total_rounds_single.setStyleSheet("color: #38bdf8; font-weight: bold;")

        grid_single.addWidget(QLabel("ความถี่ (Frequency):"), 0, 0)
        grid_single.addWidget(self.input_freq, 0, 1)
        grid_single.addWidget(QLabel("Hz"), 0, 2)

        grid_single.addWidget(QLabel("จำนวนครั้งที่วัด (Samples Count):"), 1, 0)
        grid_single.addWidget(self.input_n_single, 1, 1)
        grid_single.addWidget(QLabel("ครั้ง"), 1, 2)

        grid_single.addWidget(QLabel("ทิ้งค่าแรกสุด (Discard First):"), 2, 0)
        grid_single.addWidget(self.input_discard_single, 2, 1)
        grid_single.addWidget(QLabel("ครั้ง"), 2, 2)

        grid_single.addWidget(QLabel("รวมรอบวัดทั้งหมด:"), 3, 0)
        grid_single.addWidget(self.lbl_total_rounds_single, 3, 1)

        grid_single.setColumnStretch(3, 1)

        # เชื่อมสัญญาณเพื่ออัปเดต label ทุกครั้งที่ค่าเปลี่ยน
        # (signal connect และการคำนวณจริงอยู่ใน app_controller.py เพื่อรวมไว้กับ
        #  update_calculated_points ของ SWEEP ให้อยู่ที่เดียวกัน)

        v_mode.addWidget(self.widget_freq_single)

        # --- เนื้อหาย่อย: สแกนความถี่ Linear (SWEEP) ---
        # ใช้ QGridLayout เหมือนกลุ่มฮาร์ดแวร์ฯ เพื่อให้ label คอลัมน์ 0
        # ความกว้างเท่ากันทุกแถว -> ช่องกรอก (คอลัมน์ 1) เริ่มต้นตำแหน่งเดียวกันเป๊ะ
        self.widget_sweep = QWidget()
        grid_sweep = QGridLayout(self.widget_sweep)
        grid_sweep.setContentsMargins(0, 0, 0, 0)
        grid_sweep.setVerticalSpacing(8)

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
        self.lbl_calculated_points.setStyleSheet("color: #38bdf8; font-weight: bold;")

        grid_sweep.addWidget(QLabel("ความถี่เริ่มต้น (Start Freq):"), 0, 0)
        grid_sweep.addWidget(self.input_start_freq, 0, 1)
        grid_sweep.addWidget(QLabel("Hz"), 0, 2)

        grid_sweep.addWidget(QLabel("ความถี่สิ้นสุด (Stop Freq):"), 1, 0)
        grid_sweep.addWidget(self.input_stop_freq, 1, 1)
        grid_sweep.addWidget(QLabel("Hz"), 1, 2)

        grid_sweep.addWidget(QLabel("ค่าเพิ่มต่อจุด (Step Size):"), 2, 0)
        grid_sweep.addWidget(self.input_step_freq, 2, 1)
        grid_sweep.addWidget(QLabel("Hz"), 2, 2)

        grid_sweep.addWidget(QLabel("จำนวนจุดที่ได้:"), 3, 0)
        grid_sweep.addWidget(self.lbl_calculated_points, 3, 1)

        grid_sweep.setColumnStretch(3, 1)  # เผื่อพื้นที่ว่างด้านขวาสุด

        v_mode.addWidget(self.widget_sweep)

        # --- เนื้อหาย่อย: รายการความถี่ + Samples ต่อจุด (LIST) - คงรูปแบบเดิม ---
        self.widget_list = QWidget()
        v_list = QVBoxLayout(self.widget_list)
        v_list.setContentsMargins(0, 0, 0, 0)
        v_list.setSpacing(10)

        v_list.addWidget(QLabel("รายการความถี่ (Frequency List)"))
        self.input_freq_list = FrequencyListWidget()
        v_list.addWidget(self.input_freq_list)

        grid_list_nums = QGridLayout()
        grid_list_nums.setVerticalSpacing(8)
        grid_list_nums.setColumnStretch(2, 1)

        self.input_samples = QSpinBox()
        self.input_samples.setRange(1, 999)
        self.input_samples.setValue(10)

        self.input_discard_first = QSpinBox()
        self.input_discard_first.setRange(0, 5)
        self.input_discard_first.setValue(1)
        self.input_discard_first.setToolTip(
            "จำนวนตัวอย่างแรกสุดของแต่ละความถี่ที่จะไม่นำไปคำนวณสถิติ\n"
            "(ค่าที่วัดได้ทันทีหลังเปลี่ยนความถี่มักยังไม่นิ่ง)\n"
            "โปรแกรมจะวัดเพิ่มจากจำนวน Samples per Sweep โดยอัตโนมัติ\n"
            "เช่น Samples=5 + Discard=3 -> วัดจริง 8 ครั้ง เหลือใช้คำนวณสถิติครบ 5 ค่า"
        )

        # บังคับให้ทั้งสองช่องกว้างเท่ากันเป๊ะ (แคบกว่าช่องความถี่ปกติเล็กน้อย
        # เพราะค่าที่กรอกเป็นแค่จำนวนครั้ง ไม่ใช่ตัวเลขความถี่ที่อาจยาวหลักล้าน)
        self.input_samples.setFixedWidth(105)
        self.input_discard_first.setFixedWidth(105)

        # Label แสดงจำนวนรอบวัดทั้งหมดต่อ 1 ความถี่ = Discard + Samples
        self.lbl_total_rounds_list = QLabel("-")
        self.lbl_total_rounds_list.setStyleSheet("color: #38bdf8; font-weight: bold;")

        grid_list_nums.addWidget(QLabel("จำนวนรอบวัดซ้ำต่อความถี่ (Samples per Sweep):"), 0, 0)
        grid_list_nums.addWidget(self.input_samples, 0, 1)
        grid_list_nums.addWidget(QLabel("ครั้ง"), 0, 2)

        grid_list_nums.addWidget(QLabel("ทิ้งค่าตัวอย่างแรกสุด (Discard First Reading):"), 1, 0)
        grid_list_nums.addWidget(self.input_discard_first, 1, 1)
        grid_list_nums.addWidget(QLabel("ครั้ง"), 1, 2)

        grid_list_nums.addWidget(QLabel("รวมรอบวัดทั้งหมด/ความถี่:"), 2, 0)
        grid_list_nums.addWidget(self.lbl_total_rounds_list, 2, 1)

        # เชื่อมสัญญาณเพื่ออัปเดต label ทุกครั้งที่ค่าเปลี่ยน
        # (signal connect และการคำนวณจริงอยู่ใน app_controller.py เพื่อรวมไว้กับ
        #  update_calculated_points ของ SWEEP ให้อยู่ที่เดียวกัน)

        v_list.addLayout(grid_list_nums)

        v_mode.addWidget(self.widget_list)

        self.group_mode.setLayout(v_mode)

        # ==========================================================
        # 3. สัญญาณทดสอบ (Test Signal) + DC Bias (วางข้างกัน)
        # ==========================================================

        # --- 3a. Test Signal ---
        self.group_signal = QGroupBox("สัญญาณทดสอบ (Test Signal)")
        v_signal = QVBoxLayout()
        v_signal.setSpacing(8)

        self.input_volt = CleanDoubleSpinBox()
        self.input_volt.setRange(0.0001, 2.0)   # E4980A (ไม่มี Option 001) สูงสุด 2.0 Vrms / Arms
        self.input_volt.setDecimals(4)
        self.input_volt.setSingleStep(0.1)
        self.input_volt.setValue(1.0)
        self.input_volt.setFixedWidth(110)

        # Dropdown หน่วย: Vrms (Voltage) หรือ Arms (Current)
        self.combo_level_mode = QComboBox()
        self.combo_level_mode.addItem("Vrms", userData="Voltage")
        self.combo_level_mode.addItem("Arms", userData="Current")
        self.combo_level_mode.setFixedWidth(103)

        # Label อยู่แถวบน, SpinBox + Dropdown อยู่แถวล่าง
        v_signal.addWidget(QLabel("ระดับสัญญาณ (Signal Level):"))

        h_level = QHBoxLayout()
        h_level.addWidget(self.input_volt)
        h_level.addWidget(self.combo_level_mode)
        h_level.addStretch()
        v_signal.addLayout(h_level)

        # ALC (Automatic Level Control)
        self.chk_alc = QCheckBox("เปิด ALC (Automatic Level Control)")
        self.chk_alc.setToolTip(
            "ALC ทำให้ระดับสัญญาณ ณ จุดที่ชิ้นงาน เท่ากับค่าที่ตั้งไว้จริงๆ\n"
            "แนะนำเปิดเมื่อวัด Inductor ด้วยโหมด Arms\n"
            "เพื่อให้กระแสทดสอบคงที่ตลอดการวัดทุกความถี่"
        )

        v_signal.addWidget(self.chk_alc)
        v_signal.addStretch()
        self.group_signal.setLayout(v_signal)

        # --- 3b. DC Bias ---
        self.group_dc = QGroupBox("ไฟเลี้ยงกระแสตรง (DC Bias)")
        v_dc = QVBoxLayout()

        h_dc_enable = QHBoxLayout()
        self.chk_dc_enable = QCheckBox("เปิดใช้งาน (Enable)")
        h_dc_enable.addWidget(self.chk_dc_enable)
        v_dc.addLayout(h_dc_enable)

        self.widget_dc_inner = QWidget()
        v_dc_inner = QVBoxLayout(self.widget_dc_inner)
        v_dc_inner.setContentsMargins(0, 0, 0, 0)
        v_dc_inner.setSpacing(8)

        # [แก้ไข] เปลี่ยนเป็น Dropdown เลือกค่า DC Bias แบบตายตัว (E4980A standard: 1.5V, 2.0V)
        v_dc_inner.addWidget(QLabel("ระดับไฟ (Level):"))
        h_dc_level = QHBoxLayout()
        
        self.combo_dc_level = QComboBox()
        self.combo_dc_level.addItem("1.5 V", userData=1.5)
        self.combo_dc_level.addItem("2.0 V", userData=2.0)
        self.combo_dc_level.setFixedWidth(120)
        
        h_dc_level.addWidget(self.combo_dc_level)
        h_dc_level.addStretch()
        v_dc_inner.addLayout(h_dc_level)

        self.lbl_dc_warning = QLabel("")
        self.lbl_dc_warning.setWordWrap(True)

        self.lbl_dc_warning = QLabel("")
        self.lbl_dc_warning.setWordWrap(True)
        self.lbl_dc_warning.setMaximumWidth(190)
        self.lbl_dc_warning.setStyleSheet("color: #FF9900; font-weight: bold; font-size: 11px;")
        v_dc_inner.addWidget(self.lbl_dc_warning)

        v_dc.addWidget(self.widget_dc_inner)
        v_dc.addStretch()
        self.group_dc.setLayout(v_dc)

        h_signal_dc = QHBoxLayout()
        h_signal_dc.addWidget(self.group_signal, stretch=1)
        h_signal_dc.addWidget(self.group_dc, stretch=1)

        # ==========================================================
        # 4. ฮาร์ดแวร์และเวลา (Hardware & Timing)
        # ใช้ QGridLayout เพื่อให้ทั้ง 4 ช่อง (dropdown/spinbox) อยู่
        # คอลัมน์เดียวกัน -> ความกว้างเท่ากันและชิดตรงกันโดยอัตโนมัติ
        # ==========================================================
        self.group_hw = QGroupBox("ฮาร์ดแวร์และเวลา (Hardware & Timing)")
        grid_hw = QGridLayout()
        grid_hw.setVerticalSpacing(8)
        grid_hw.setColumnStretch(1, 1)

        self.combo_time = QComboBox()
        self.combo_time.addItems(["SHORT", "MEDIUM", "LONG"])
        self.combo_time.setCurrentText("LONG")  # ค่าเริ่มต้น = LONG (ความแม่นยำสูงสุด)

        self.input_avg = QSpinBox()
        self.input_avg.setRange(1, 256)
        self.input_avg.setValue(1)

        self.combo_cable = QComboBox()
        self.combo_cable.addItems(["0 m", "1 m", "2 m", "4 m"])

        self.combo_range = QComboBox()
        self.combo_range.addItem("AUTO", userData="AUTO")
        self.combo_range.addItem("0.1 Ω", userData=0.1)
        self.combo_range.addItem("1 Ω", userData=1)
        self.combo_range.addItem("10 Ω", userData=10)
        self.combo_range.addItem("100 Ω", userData=100)
        self.combo_range.addItem("300 Ω", userData=300)
        self.combo_range.addItem("1 kΩ", userData=1000)
        self.combo_range.addItem("3 kΩ", userData=3000)
        self.combo_range.addItem("10 kΩ", userData=10000)
        self.combo_range.addItem("30 kΩ", userData=30000)
        self.combo_range.addItem("100 kΩ", userData=100000)

        grid_hw.addWidget(QLabel("เวลาวัด (Meas Time):"), 0, 0)
        grid_hw.addWidget(self.combo_time, 0, 1)
        grid_hw.addWidget(QLabel("ค่าเฉลี่ย (Averaging):"), 1, 0)
        grid_hw.addWidget(self.input_avg, 1, 1)
        grid_hw.addWidget(QLabel("สายวัด (Cable Length):"), 2, 0)
        grid_hw.addWidget(self.combo_cable, 2, 1)
        grid_hw.addWidget(QLabel("ย่านอิมพีแดนซ์ (Z Range):"), 3, 0)
        grid_hw.addWidget(self.combo_range, 3, 1)

        self.group_hw.setLayout(grid_hw)

        # ==========================================================
        # ประกอบ Layout
        # ==========================================================
        layout.addWidget(self.group_prop)
        layout.addWidget(self.group_mode)
        layout.addLayout(h_signal_dc)
        layout.addWidget(self.group_hw)

        layout.addStretch()