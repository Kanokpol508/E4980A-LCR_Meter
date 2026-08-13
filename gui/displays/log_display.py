# แผงแสดง Log การทำงานของโปรแกรมแบบ Real-time
# ใช้ Python logging module มาตรฐาน + custom Handler ที่ส่งข้อความเข้า QTextEdit
# ทำงานได้ปลอดภัยข้าม Thread เพราะใช้ QMetaObject.invokeMethod แทนการเรียก UI ตรงๆ

import logging
from collections import deque
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QTextEdit, QLabel, QComboBox,
                              QMessageBox)
from PyQt6.QtCore import Qt, QMetaObject, Q_ARG, pyqtSlot
from PyQt6.QtGui import QFont, QTextCursor
from utils.helpers import NoScrollComboBox


# ==========================================
# Custom Logging Handler: ส่ง log record เข้า QTextEdit อย่างปลอดภัย
# ==========================================
class QtLogHandler(logging.Handler):
    """
    Logging Handler ที่เชื่อม Python logging เข้ากับ QTextEdit
    ใช้ QMetaObject.invokeMethod เพื่อให้ปลอดภัยตอนเรียกจาก Worker Thread
    (QTextEdit ต้องถูกแก้ไขใน GUI Thread เท่านั้น — ห้ามเรียกตรงจาก QThread)
    """
    def __init__(self, log_widget: 'LogDisplay'):
        super().__init__()
        self.log_widget = log_widget

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        level = record.levelname
        # ส่ง message เข้า GUI Thread อย่างปลอดภัยผ่าน invokeMethod
        QMetaObject.invokeMethod(
            self.log_widget,
            "append_log",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, msg),
            Q_ARG(str, level)
        )


# ==========================================
# LogDisplay Widget
# ==========================================
class LogDisplay(QWidget):
    """
    แผง Log แสดงผลการทำงานแบบ Real-time
    - ระบายสีแยกตาม Level: INFO (ขาว), WARNING (เหลือง), ERROR (แดง), CRITICAL (แดงสด), DEBUG (เทา)
    - มีปุ่ม Clear Log (พร้อม confirm dialog)
    - มีปุ่ม Copy Log (คัดลอกข้อความที่แสดงอยู่ + แจ้ง popup)
    - มี Dropdown กรอง Level ที่จะแสดง (DEBUG / INFO / WARNING / ERROR / CRITICAL)
    - Auto-scroll ลงล่างทุกครั้งที่มี Log ใหม่
    """

    # ลำดับ severity ที่ใช้เปรียบเทียบ Filter (ครอบคลุมทุก level ที่มี LEVEL_COLORS)
    _LEVEL_ORDER = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    # สีตาม Level (ใช้ hex color ให้เข้ากับ pastel white theme ของโปรแกรม)
    LEVEL_COLORS = {
        "DEBUG":    "#9AA5B5",   # เทาอ่อน
        "INFO":     "#33415C",   # กรมท่าอ่อน (อ่านง่ายบนพื้นขาว)
        "WARNING":  "#C98A1F",   # ส้มอำพันเข้มพออ่านออกบนพื้นขาว
        "ERROR":    "#D2544B",   # แดงพาสเทลเข้ม
        "CRITICAL": "#B3261E",   # แดงเข้ม
    }

    # จำนวน record สูงสุดที่เก็บไว้ใน buffer (ใช้ร่วมกับ deque maxlen)
    _MAX_RECORDS = 2000

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._setup_logger()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- แถบเครื่องมือด้านบน ---
        toolbar = QHBoxLayout()

        lbl = QLabel("แสดงตั้งแต่ Level:")
        lbl.setFixedWidth(130)
        lbl.setStyleSheet("color: #FFFFFF;")
        toolbar.addWidget(lbl)

        self.combo_level_filter = NoScrollComboBox()
        self.combo_level_filter.addItems([
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ])
        self.combo_level_filter.setCurrentText("INFO")
        self.combo_level_filter.setFixedWidth(160)
        self.combo_level_filter.setToolTip(
            "แสดง log ตั้งแต่ระดับที่เลือกขึ้นไป\n"
            "DEBUG    = ทุก level (DEBUG ขึ้นไป)\n"
            "INFO     = INFO + WARNING + ERROR + CRITICAL\n"
            "WARNING  = WARNING + ERROR + CRITICAL\n"
            "ERROR    = ERROR + CRITICAL\n"
            "CRITICAL = CRITICAL อย่างเดียว"
        )
        self.combo_level_filter.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.combo_level_filter)

        toolbar.addStretch()

        # ปุ่ม Copy Log
        self.btn_copy = QPushButton("📋 Copy Log")
        self.btn_copy.setFixedHeight(28)
        self.btn_copy.setToolTip("คัดลอกข้อความ log ที่แสดงอยู่ในหน้าจอทั้งหมด")
        self.btn_copy.setStyleSheet(
            "QPushButton { background-color: #AACCE2; color: #1B2740; border-radius: 4px; padding: 0 10px; border: 1px solid #789CCE; }"
            "QPushButton:hover { background-color: #95C8D7; }"
        )
        self.btn_copy.clicked.connect(self.copy_log)
        toolbar.addWidget(self.btn_copy)

        # ปุ่ม Clear Log
        self.btn_clear = QPushButton("🗑 Clear Log")
        self.btn_clear.setFixedHeight(28)
        self.btn_clear.setToolTip("ล้าง log ทั้งหมดที่แสดงอยู่และ buffer ภายใน")
        self.btn_clear.setStyleSheet(
            "QPushButton { background-color: #FADEE1; color: #7A1F1B; border-radius: 4px; padding: 0 10px; border: 1px solid #F5B8BC; }"
            "QPushButton:hover { background-color: #F8C6CA; }"
        )
        self.btn_clear.clicked.connect(self.clear_log)
        toolbar.addWidget(self.btn_clear)

        layout.addLayout(toolbar)

        # --- พื้นที่แสดง Log ---
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        font = QFont("Courier New", 11)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_area.setFont(font)
        self.text_area.setStyleSheet(
            "QTextEdit {"
            "  background-color: #FBFCFD;"
            "  color: #33415C;"
            "  border: 1px solid #D6E4F0;"
            "  border-radius: 4px;"
            "}"
        )
        layout.addWidget(self.text_area)

        # [จุดที่ 5] เปลี่ยนจาก list เป็น deque(maxlen=_MAX_RECORDS)
        # เดิม: self._all_records = self._all_records[-2000:] ทุก append → O(n) ต่อครั้ง
        # ใหม่: deque จัดการตัดทิ้งอัตโนมัติเมื่อเกิน maxlen → O(1) ต่อครั้ง
        self._all_records: deque[tuple[str, str]] = deque(maxlen=self._MAX_RECORDS)

    def _setup_logger(self):
        """สร้าง Logger ชื่อ 'LCR' และผูก QtLogHandler เข้ากับ text_area"""
        self.logger = logging.getLogger("LCR")
        self.logger.setLevel(logging.DEBUG)

        # ป้องกันการเพิ่ม Handler ซ้ำตอน __init__ ถูกเรียกหลายครั้ง
        if not any(isinstance(h, QtLogHandler) for h in self.logger.handlers):
            handler = QtLogHandler(self)
            formatter = logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(message)s",
                datefmt="%H:%M:%S"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        # ป้องกัน log ไหลขึ้นไปยัง root logger (กันข้อความซ้ำใน console)
        self.logger.propagate = False

    @pyqtSlot(str, str)
    def append_log(self, message: str, level: str):
        """
        รับ log message จาก QtLogHandler (เรียกผ่าน invokeMethod เสมอ จึงอยู่ใน GUI Thread)
        เก็บไว้ใน _all_records แล้วแสดงถ้าผ่าน filter ปัจจุบัน

        [จุดที่ 5] deque.append() เป็น O(1) และตัดทิ้งอัตโนมัติเมื่อเกิน maxlen
        ไม่ต้องเช็ค len() และสร้าง list ใหม่ทุกครั้งเหมือนเดิมอีกต่อไป
        """
        self._all_records.append((message, level))

        if self._passes_filter(level):
            self._append_colored_line(message, level)

    def _passes_filter(self, level: str) -> bool:
        """
        เช็คว่า level นี้ผ่าน filter ที่เลือกไว้หรือไม่
        ใช้ _LEVEL_ORDER เป็น ground truth — DEBUG คือตัวต่ำสุด แสดงครบทุก level
        """
        filter_level = self.combo_level_filter.currentText().split()[0]
        try:
            return self._LEVEL_ORDER.index(level) >= self._LEVEL_ORDER.index(filter_level)
        except ValueError:
            return True

    def _append_colored_line(self, message: str, level: str):
        """เพิ่มบรรทัด log พร้อมสีตาม level เข้า QTextEdit แล้ว auto-scroll"""
        color = self.LEVEL_COLORS.get(level, "#33415C")
        cursor = self.text_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # ใส่สีผ่าน HTML inline style
        html_line = (
            f'<span style="color:{color}; font-family:\'Courier New\',monospace; font-size:11pt;">'
            f'{self._escape_html(message)}</span><br>'
        )
        cursor.insertHtml(html_line)

        # Auto-scroll ลงล่างสุดเสมอ
        self.text_area.setTextCursor(cursor)
        self.text_area.ensureCursorVisible()

    @staticmethod
    def _escape_html(text: str) -> str:
        """escape อักขระพิเศษ HTML เพื่อกัน XSS/rendering พัง"""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    def _on_filter_changed(self, _text: str):
        """
        Re-render ข้อความทั้งหมดใหม่เมื่อเปลี่ยน Level filter

        [จุดที่ 5] รวม HTML ทั้งหมดเป็น string เดียวแล้ว setHtml() ครั้งเดียว
        แทนการเรียก insertHtml() ทีละบรรทัด ลด DOM reflow จาก O(n) ครั้ง
        เหลือ 1 ครั้ง ทำให้การเปลี่ยน filter เร็วขึ้นมากเมื่อมี record จำนวนมาก
        """
        font_style = "font-family:'Courier New',monospace; font-size:11pt;"
        html_parts = []
        for msg, level in self._all_records:
            if self._passes_filter(level):
                color = self.LEVEL_COLORS.get(level, "#33415C")
                html_parts.append(
                    f'<span style="color:{color}; {font_style}">'
                    f'{self._escape_html(msg)}</span><br>'
                )

        # setHtml() ล้างและเขียนใหม่ทั้งหมดใน 1 ครั้ง
        self.text_area.setHtml("".join(html_parts))

        # เลื่อนไปที่ท้ายสุดหลัง re-render
        self.text_area.moveCursor(QTextCursor.MoveOperation.End)
        self.text_area.ensureCursorVisible()

    def copy_log(self):
        """
        คัดลอก log ที่แสดงอยู่บนหน้าจอ (ที่ผ่าน filter แล้ว) ลง Clipboard
        แล้วแสดง popup แจ้งผู้ใช้
        """
        visible_lines = [
            msg for msg, level in self._all_records
            if self._passes_filter(level)
        ]

        if not visible_lines:
            QMessageBox.information(
                self,
                "Copy Log",
                "ไม่มีข้อความ log ที่จะคัดลอก"
            )
            return

        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(visible_lines))

        n = len(visible_lines)
        QMessageBox.information(
            self,
            "Copy Log สำเร็จ",
            f"✅ คัดลอก {n} บรรทัดไปยัง Clipboard เรียบร้อยแล้ว"
        )

    def clear_log(self):
        """ยืนยันกับผู้ใช้ก่อน แล้วจึงล้าง log ทั้งหมดทั้งใน UI และ buffer"""
        reply = QMessageBox.question(
            self,
            "ยืนยันการล้าง Log",
            "คุณต้องการล้างประวัติ Log ทั้งหมดใช่หรือไม่?\n(ข้อมูลที่ล้างแล้วจะไม่สามารถกู้คืนได้)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.text_area.clear()
            self._all_records.clear()

    def get_logger(self) -> logging.Logger:
        """คืน Logger 'LCR' ให้ app_controller เรียกใช้งาน"""
        return self.logger