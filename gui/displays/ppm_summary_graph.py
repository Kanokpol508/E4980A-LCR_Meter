# กราฟ PPM Deviation vs ความถี่ (PPM Summary Graph)
# แกน X = ความถี่ (เรียงจากน้อยไปมาก), แกน Y = ค่าเบี่ยงเบนจากค่าอ้างอิง (PPM Deviation)
# ใช้ pri_ppm / sec_ppm จาก calculate_frequency_stats() — ต้องเปิด "PPM Reference"
# (chk_dev_ppm_enable + input_dev_pri/sec ใน advanced_panel) และกรอกค่านอมินอลไว้ก่อนวัด
# Error bar = SD Error Bar (Stability, ppm) = SD / |Ref| × 1e6 (คำนวณใน app_controller._sd_to_ppm)
# ใช้ได้เฉพาะโหมด LIST / SWEEP เท่านั้น (เหตุผลเดียวกับ freq_summary_graph.py)

import os
import re
import math
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QLineEdit, QComboBox, QPushButton, QFileDialog, QMessageBox
)
from PyQt6.QtCore import QStandardPaths, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem
import pyqtgraph as pg
import pyqtgraph.exporters

# แยก "ชื่อพารามิเตอร์" กับ "หน่วยในวงเล็บท้ายสุด" เช่น
# "Resistance, R (Ω)" -> ("Resistance, R", "Ω")  — ใช้แค่ดึงชื่อออกมา ไม่สนใจหน่วยเดิม
# เพราะกราฟนี้หน่วยของแกน Y เป็น "ppm" เสมอ ไม่ใช่หน่วยเดิมของพารามิเตอร์
_UNIT_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")


def _split_name_unit(label: str):
    m = _UNIT_RE.match(label.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return label.strip(), None


# ขอบเขตแกน X ตามสเปคเครื่อง E4980A (20Hz - 2MHz) เผื่อขอบไว้อีกนิด (2.1MHz)
# กันไม่ให้จุดข้อมูลที่วัดได้ที่ 2MHz พอดีไปติดชิดขอบกราฟจนมองไม่เห็นเต็มจุด
FREQ_MIN = 20
FREQ_MAX = 2_000_000
FREQ_MAX_BUFFERED = 2_100_000


class _FreqEngAxisItem(pg.AxisItem):
    """แกนความถี่ (X): ย่อ k, M, G ได้ ไม่มีทศนิยม ไม่มีค่าติดลบ
    และจำกัดขอบเขตการวาดตัวเลขให้อยู่ในสเปคเครื่อง 0 - 2.1 MHz
    ป้องกัน OverflowError ตอนสลับ Linear/Log แล้ว pyqtgraph ส่งค่า tick ที่ใหญ่ผิดปกติมา
    (เช่น 10**v ตอน v มีค่ามากเกินกว่าที่ float รองรับ)"""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            # log10(20Hz) ~= 1.3, log10(2.1MHz) ~= 6.32 — ค่าที่สมเหตุสมผลไม่ควรหลุดช่วงนี้มาก
            # ถ้า v หลุดช่วงนี้ไปไกล ให้ทิ้ง tick นั้นไปเลยโดยไม่คำนวณ 10**v ต่อ กัน OverflowError
            # ทุกรูปแบบ (ทั้งตอน 10**v เอง และตอนแปลงเป็น float ในขั้นตอนถัดไป)
            if self.logMode and (v < -50 or v > 50):
                strings.append("")
                continue
            try:
                raw_val = (10 ** v) if self.logMode else v
                val = raw_val * scale
                if not math.isfinite(val):
                    strings.append("")
                    continue
            except (OverflowError, ValueError):
                strings.append("")
                continue

            if val < 0 or val > FREQ_MAX_BUFFERED:
                strings.append("")
                continue
            if abs(val - round(val)) > 1e-5:
                strings.append("")
                continue

            strings.append(self._format_eng(val))
        return strings

    def _format_eng(self, val):
        if val == 0:
            return "0"
        abs_val = abs(val)
        if abs_val >= 1e9:
            return f"{val/1e9:g}G"
        elif abs_val >= 1e6:
            return f"{val/1e6:g}M"
        elif abs_val >= 1e3:
            return f"{val/1e3:g}k"
        else:
            return f"{int(round(val))}"


class _EngAxisItem(pg.AxisItem):
    """แกน PPM Deviation (Y): รองรับค่าติดลบได้ (deviation ต่ำ/สูงกว่านอมินอลได้ทั้งคู่)
    และย่อหน่วยได้ทุกระดับ (k ppm, m ppm ...)

    เลือก 'หน่วยเดียว' ให้ใช้ร่วมกันทั้งชุด tick ที่กำลังวาด (ดูจากค่าที่มากที่สุดในชุดนั้น)
    แทนที่จะให้แต่ละ tick เลือกหน่วยของตัวเองอิสระ — กันปัญหาแกนเดียวกันมีทั้ง
    '500m', '1', '1.5k' ปนกันจนอ่านยาก และคำนวณจำนวนทศนิยมจาก spacing จริงของ tick
    กันตัวเลขงอกเป็นเศษ (เช่น 12.9999k จาก error สะสมของ float)
    """

    _SUFFIXES = [
        (1e9, 'G'), (1e6, 'M'), (1e3, 'k'), (1, ''),
        (1e-3, 'm'), (1e-6, 'µ'), (1e-9, 'n'), (1e-12, 'p'),
    ]

    def tickStrings(self, values, scale, spacing):
        if not values:
            return []

        raw_vals = []
        for v in values:
            if self.logMode and (v < -300 or v > 300):
                raw_vals.append(None)
                continue
            try:
                rv = (10 ** v) if self.logMode else v
                rv = rv * scale
                if not math.isfinite(rv):
                    raw_vals.append(None)
                    continue
            except (OverflowError, ValueError):
                raw_vals.append(None)
                continue
            raw_vals.append(rv)

        finite_vals = [rv for rv in raw_vals if rv is not None]
        max_abs = max((abs(rv) for rv in finite_vals), default=0)

        factor, suffix = 1, ''
        for f, s in self._SUFFIXES:
            if max_abs >= f:
                factor, suffix = f, s
                break

        # จำนวนทศนิยมคำนวณจาก spacing จริงของ tick เทียบกับหน่วยที่เลือก
        if self.logMode and len(finite_vals) >= 2:
            sorted_vals = sorted(set(round(rv, 12) for rv in finite_vals))
            diffs = [b - a for a, b in zip(sorted_vals, sorted_vals[1:]) if b - a > 0]
            step = min(diffs) if diffs else max_abs
        else:
            step = spacing * scale

        if factor and step > 0:
            step_in_units = step / factor
            decimals = 0 if step_in_units >= 1 else min(4, max(0, math.ceil(-math.log10(step_in_units))))
        else:
            decimals = 0

        strings = []
        for rv in raw_vals:
            if rv is None:
                strings.append("")
                continue
            if rv == 0:
                strings.append("0")
                continue
            val = rv / factor if factor else rv
            if decimals == 0:
                strings.append(f"{round(val)}{suffix}")
            else:
                strings.append(f"{val:.{decimals}f}{suffix}")
        return strings


class PpmSummaryGraph(QWidget):
    # สีเดียวกับ freq_summary_graph.py เพื่อไม่ให้ผู้ใช้สับสนระหว่าง Tab
    COLOR_PRIMARY = '#0066CC'    # น้ำเงิน
    COLOR_SECONDARY = '#CC0066'  # แดงอมชมพู

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label_style = {'color': '#1e293b', 'font-size': '10pt', 'font-weight': 'normal'}

        # ชื่อพารามิเตอร์จริงตาม SCPI mode (อัปเดตผ่าน set_axis_labels) — ไม่รวมหน่วยเดิม
        # เพราะกราฟนี้แกน Y เป็น ppm เสมอ
        self.pri_name = "Primary"
        self.sec_name = "Secondary"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ==========================================
        # แถบควบคุม: Plot Display Options
        # ==========================================
        group_opts = QGroupBox("Plot Display Options")
        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(12)

        # [เปลี่ยนจาก 2 checkbox อิสระ (Plot Primary / Plot Secondary) มาเป็น
        #  Dropdown เดียว 3 ตัวเลือก: Primary / Secondary / Both — ค่าเริ่มต้นเปิดโปรแกรม
        #  ครั้งแรกคือ "Plot Primary" ตามที่ผู้ใช้ต้องการ]
        # ใช้ QStandardItemModel แทน addItem() ธรรมดา เพราะต้อง enable/disable ทีละตัวเลือก
        # ได้ (เช่น ปิด "Plot Primary" ถ้ายังไม่กรอก Primary Ref) เหมือนที่เดิม
        # setEnabled(False) ทำกับ checkbox ทีละตัวได้ แต่ QComboBox ทำแบบนั้นไม่ได้
        # ต้องสั่งที่ item ใน model แทน
        self.combo_plot_select = QComboBox()
        self._plot_select_model = QStandardItemModel(self.combo_plot_select)

        self._item_plot_pri = QStandardItem("Plot Primary")
        self._item_plot_pri.setData("PRI", Qt.ItemDataRole.UserRole)
        self._item_plot_sec = QStandardItem("Plot Secondary")
        self._item_plot_sec.setData("SEC", Qt.ItemDataRole.UserRole)
        self._item_plot_both = QStandardItem("Plot Both")
        self._item_plot_both.setData("BOTH", Qt.ItemDataRole.UserRole)

        for item in (self._item_plot_pri, self._item_plot_sec, self._item_plot_both):
            self._plot_select_model.appendRow(item)

        self.combo_plot_select.setModel(self._plot_select_model)
        self.combo_plot_select.setCurrentIndex(0)  # ค่าเริ่มต้น = Plot Primary

        self.chk_error_bar = QCheckBox("Show Stability Error Bars (SD PPM)")
        self.chk_error_bar.setChecked(True)
        self.chk_data_labels = QCheckBox("Show Data Labels")
        self.chk_data_labels.setChecked(False)
        self.chk_show_legend = QCheckBox("Show Legend")
        self.chk_show_legend.setChecked(True)

        opts_layout.addWidget(QLabel("Plot:"))
        opts_layout.addWidget(self.combo_plot_select)
        opts_layout.addWidget(self.chk_error_bar)
        opts_layout.addWidget(self.chk_data_labels)
        opts_layout.addWidget(self.chk_show_legend)

        opts_layout.addStretch(1)

        opts_layout.addWidget(QLabel("Frequency Scale:"))
        self.combo_x_scale = QComboBox()
        self.combo_x_scale.addItems(["Linear", "Log"])
        opts_layout.addWidget(self.combo_x_scale)

        group_opts.setLayout(opts_layout)
        main_layout.addWidget(group_opts)

        # ==========================================
        # แถบ Progress / Current Reading (ระหว่างวัดซ้ำ)
        # แสดงว่าตอนนี้กำลังวัดซ้ำอยู่ที่ความถี่ไหน — อัปเดตจาก app_controller
        # ผ่าน set_progress()/set_current_reading() ทุกครั้งที่มีจุดข้อมูลใหม่เข้ามา
        # ==========================================
        status_bar = QHBoxLayout()
        status_bar.addWidget(QLabel("Progress:"))
        self.lbl_progress = QLabel("Idle")
        self.lbl_progress.setStyleSheet("font-weight: bold;")
        status_bar.addWidget(self.lbl_progress)

        status_bar.addSpacing(20)

        status_bar.addWidget(QLabel("Current Reading:"))
        self.lbl_current_reading = QLabel("--")
        self.lbl_current_reading.setStyleSheet("font-weight: bold;")
        status_bar.addWidget(self.lbl_current_reading)

        status_bar.addStretch(1)
        main_layout.addLayout(status_bar)

        # ==========================================
        # แถบ Graph Title + ปุ่ม Save เป็น JPEG
        # ==========================================
        title_bar = QHBoxLayout()
        title_bar.addWidget(QLabel("Graph Title:"))
        self.input_graph_title = QLineEdit()
        self.input_graph_title.setPlaceholderText("กรอกชื่อกราฟที่ต้องการ")
        title_bar.addWidget(self.input_graph_title, stretch=1)

        self.btn_save_jpeg = QPushButton("💾 Save as JPEG")
        title_bar.addWidget(self.btn_save_jpeg)
        main_layout.addLayout(title_bar)

        # ==========================================
        # กราฟหลัก (Primary/Secondary รวมในแกน Y เดียวกัน หน่วย ppm)
        # ==========================================
        self.plot_widget = pg.PlotWidget(
            title="PPM Deviation vs. Frequency",
            axisItems={
                'bottom': _FreqEngAxisItem(orientation='bottom'),
                'left':   _EngAxisItem(orientation='left'),
            }
        )
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._style_axes_dark(self.plot_widget)
        self.plot_widget.setLabel('bottom', 'Frequency (Hz)', **self.label_style)
        self.plot_widget.setLabel('left', 'PPM Deviation', **self.label_style)

        # เส้นอ้างอิงที่ 0 ppm (นอมินอล) — ช่วยให้เห็นชัดว่าค่าเบี่ยงเบนไปทางบวก/ลบแค่ไหน
        self.zero_line = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('#94a3b8', width=1, style=pg.QtCore.Qt.PenStyle.DashLine))
        self.plot_widget.addItem(self.zero_line)

        # ตั้งช่วงเริ่มต้นให้เป็นช่วงความถี่ทั่วไปของเครื่อง LCR (20Hz - 2.1MHz)
        # เผื่อขอบไว้นิดหน่อยกันข้อมูลที่วัดได้พอดี 2MHz ไปติดขอบกราฟ
        self.plot_widget.setXRange(FREQ_MIN, FREQ_MAX_BUFFERED)

        vb = self.plot_widget.getViewBox()
        # ล็อคไม่ให้เลื่อน/ซูมแกน X หลุดช่วงความถี่ที่เครื่อง E4980A รองรับจริง (0 - 2.1MHz)
        vb.setLimits(xMin=0, xMax=FREQ_MAX_BUFFERED)
        vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)

        # legend มุมขวาบนของกราฟ — เพิ่ม/ลบ item เองแบบ dynamic ตามเส้นที่เปิด/ปิดจริง
        self.legend = pg.LegendItem(offset=None)
        self.legend.setParentItem(self.plot_widget.plotItem)
        self.legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-10, 10))

        self.curve_pri = self.plot_widget.plot(
            pen=pg.mkPen(self.COLOR_PRIMARY, width=2), symbol='o',
            symbolSize=7, symbolBrush=self.COLOR_PRIMARY
        )
        self.curve_sec = self.plot_widget.plot(
            pen=pg.mkPen(self.COLOR_SECONDARY, width=2), symbol='s',
            symbolSize=7, symbolBrush=self.COLOR_SECONDARY
        )

        self.errbar_pri = pg.ErrorBarItem(pen=pg.mkPen(self.COLOR_PRIMARY, width=1))
        self.plot_widget.addItem(self.errbar_pri)
        self.errbar_sec = pg.ErrorBarItem(pen=pg.mkPen(self.COLOR_SECONDARY, width=1))
        self.plot_widget.addItem(self.errbar_sec)

        # ข้อความแจ้งเตือนกลางกราฟตอนไม่มีข้อมูล ppm (ยังไม่เปิด PPM Reference)
        self.no_data_text = pg.TextItem(
            "ยังไม่มีข้อมูล PPM — กรุณาเปิด PPM Reference และกรอกค่านอมินอลก่อนวัด",
            color='#94a3b8', anchor=(0.5, 0.5)
        )
        self.no_data_text.setVisible(False)
        self.plot_widget.addItem(self.no_data_text)

        self._data_label_items = []  # เก็บ TextItem ไว้ลบทิ้งตอน redraw

        main_layout.addWidget(self.plot_widget, stretch=1)

        # ==========================================
        # Signal เชื่อมต่อ: เปลี่ยนตัวเลือกแล้ว redraw ทันที
        # ==========================================
        for w in (self.chk_error_bar, self.chk_data_labels, self.chk_show_legend):
            w.stateChanged.connect(self._redraw)
        self.combo_plot_select.currentIndexChanged.connect(self._redraw)
        self.combo_x_scale.currentTextChanged.connect(self._on_scale_changed)
        self.input_graph_title.textChanged.connect(self._redraw)
        self.btn_save_jpeg.clicked.connect(self.save_as_jpeg)

        self._freqs, self._pri_ppm, self._pri_err = [], [], []
        self._sec_ppm, self._sec_err = [], []

        self._redraw()

    # --------------------------------------------------------
    def is_plot_primary_enabled(self) -> bool:
        """คืนค่า True ถ้าตัวเลือกปัจจุบันใน Dropdown คือ 'Plot Primary' หรือ 'Plot Both'
        (แทนที่ chk_plot_pri.isChecked() เดิม)"""
        return self.combo_plot_select.currentData() in ("PRI", "BOTH")

    def is_plot_secondary_enabled(self) -> bool:
        """คืนค่า True ถ้าตัวเลือกปัจจุบันใน Dropdown คือ 'Plot Secondary' หรือ 'Plot Both'"""
        return self.combo_plot_select.currentData() in ("SEC", "BOTH")

    def set_primary_option_enabled(self, enabled: bool, tooltip: str = ""):
        """เปิด/ปิดตัวเลือก 'Plot Primary' ใน Dropdown (แทนที่ chk_plot_pri.setEnabled() เดิม)
        ไม่บังคับเปลี่ยนตัวเลือกที่กำลังเลือกอยู่แม้จะถูกปิด — รักษาพฤติกรรมเดิมที่แค่ทำให้
        เลือกไม่ได้ (จาง) แต่ไม่รีเซ็ตตัวเลือกทิ้ง เผื่อผู้ใช้กรอก Ref กลับมาใหม่ภายหลัง"""
        self._item_plot_pri.setEnabled(enabled)
        self._item_plot_pri.setToolTip(tooltip)

    def set_secondary_option_enabled(self, enabled: bool, tooltip: str = ""):
        """เปิด/ปิดตัวเลือก 'Plot Secondary' ใน Dropdown (แทนที่ chk_plot_sec.setEnabled() เดิม)"""
        self._item_plot_sec.setEnabled(enabled)
        self._item_plot_sec.setToolTip(tooltip)

    # --------------------------------------------------------
    def _on_scale_changed(self, *args):
        """สลับ Linear/Log — ต้องรีเซ็ต view range ก่อน redraw เสมอ กัน pyqtgraph
        เก็บ range เก่า (ที่เป็นหน่วยอื่น เช่น Hz ตรงๆ) มาตีความผิดเป็น log-space
        จนได้ tick ค่ามหาศาลแล้ว overflow ตอน 10**v"""
        is_log = (self.combo_x_scale.currentText().lower() == 'log')
        self.plot_widget.setLogMode(x=is_log, y=False)
        if len(self._freqs) == 0:
            if is_log:
                self.plot_widget.setXRange(math.log10(FREQ_MIN), math.log10(FREQ_MAX_BUFFERED))
            else:
                self.plot_widget.setXRange(FREQ_MIN, FREQ_MAX_BUFFERED)
        self._redraw()

    # --------------------------------------------------------
    def _style_axes_dark(self, plot_widget):
        for axis_name in ('left', 'bottom'):
            axis = plot_widget.getAxis(axis_name)
            axis.setPen(pg.mkPen('#334155'))
            axis.setTextPen(pg.mkPen('#1e293b'))

    # --------------------------------------------------------
    def set_axis_labels(self, pri_label: str, sec_label: str):
        """เรียกจาก app_controller ตอนเปลี่ยน SCPI mode — ใช้แค่ 'ชื่อ' พารามิเตอร์
        (ตัดหน่วยเดิมทิ้ง เพราะกราฟนี้แกน Y เป็น ppm เสมอ ไม่ใช่หน่วยเดิม เช่น Ω, F)"""
        self.pri_name, _ = _split_name_unit(pri_label)
        self.sec_name, _ = _split_name_unit(sec_label)
        self._redraw()

    def update_data(self, freqs: list, pri_ppm: list, pri_err: list,
                     sec_ppm: list, sec_err: list):
        """freqs ต้องเรียงจากน้อยไปมากแล้ว (ผลจาก calculate_frequency_stats)
        pri_ppm/sec_ppm อาจมีค่า None ปนอยู่ได้ (ถ้ายังไม่เปิด PPM Reference ตอนวัดความถี่นั้น)
        pri_err/sec_err คือ SD Error Bar (Stability, ppm) = SD / |Ref| × 1e6
        (ไม่ใช่ Type A ppm — ไม่หารด้วย √N จึงสะท้อนความกระจายของการวัดซ้ำจริงๆ)
        — widget จะกรองจุดที่เป็น None ทิ้งให้เองก่อนวาด"""
        self._freqs = freqs
        self._pri_ppm, self._pri_err = pri_ppm, pri_err
        self._sec_ppm, self._sec_err = sec_ppm, sec_err
        self._redraw()

    def clear(self):
        self._freqs, self._pri_ppm, self._pri_err = [], [], []
        self._sec_ppm, self._sec_err = [], []
        self._redraw()
        is_log = (self.combo_x_scale.currentText().lower() == 'log')
        if is_log:
            self.plot_widget.setXRange(math.log10(FREQ_MIN), math.log10(FREQ_MAX_BUFFERED))
        else:
            self.plot_widget.setXRange(FREQ_MIN, FREQ_MAX_BUFFERED)
        self.set_progress("Idle")
        self.set_current_reading("--")

    # --------------------------------------------------------
    def set_progress(self, text: str):
        """เรียกจาก app_controller ระหว่างวัด เพื่อบอกสถานะภาพรวม
        เช่น 'Sample 2/5 @ Freq 3/10 (1.0 kHz)' หรือ 'Idle' / 'Stopped' / 'Complete'"""
        self.lbl_progress.setText(text)

    def set_current_reading(self, text: str):
        """เรียกจาก app_controller ทุกครั้งที่มีจุดข้อมูลใหม่เข้ามา เพื่อบอกว่ากำลัง
        วัดซ้ำอยู่ที่ความถี่ไหน พร้อมค่าที่อ่านได้ล่าสุด เช่น 'Re: 1.00234e+04 Ω @ 1.0 kHz'"""
        self.lbl_current_reading.setText(text)

    # --------------------------------------------------------
    @staticmethod
    def _filter_none(freqs, values, errs):
        """คัดเฉพาะจุดที่ ppm ไม่ใช่ None ออกมา (ความถี่ที่ปิด PPM ref ไว้จะไม่ถูกวาด)"""
        fx, vy, ey = [], [], []
        for f, v, e in zip(freqs, values, errs):
            if v is not None:
                fx.append(f)
                vy.append(v)
                ey.append(e if e is not None else 0.0)
        return fx, vy, ey

    def _group_y_label(self, show_pri: bool, show_sec: bool) -> str:
        if show_pri and show_sec:
            return f"{self.pri_name} & {self.sec_name} Deviation (ppm)"
        elif show_pri:
            return f"{self.pri_name} Deviation (ppm)"
        elif show_sec:
            return f"{self.sec_name} Deviation (ppm)"
        return "PPM Deviation"

    # --------------------------------------------------------
    def _redraw(self, *args):
        for item in self._data_label_items:
            self.plot_widget.removeItem(item)
        self._data_label_items.clear()

        self.legend.clear()

        title = self.input_graph_title.text().strip()
        self.plot_widget.setTitle(title if title else "PPM Deviation vs. Frequency")

        x_scale = self.combo_x_scale.currentText().lower()
        is_log = (x_scale == 'log')
        self.plot_widget.setLogMode(x=is_log, y=False)

        pri_fx, pri_vy, pri_ey = self._filter_none(self._freqs, self._pri_ppm, self._pri_err)
        sec_fx, sec_vy, sec_ey = self._filter_none(self._freqs, self._sec_ppm, self._sec_err)

        show_pri = self.is_plot_primary_enabled() and len(pri_fx) > 0
        show_sec = self.is_plot_secondary_enabled() and len(sec_fx) > 0

        self.plot_widget.setLabel('left', self._group_y_label(show_pri, show_sec), **self.label_style)

        pri_legend_name = f"{self.pri_name} Dev (PPM)"
        sec_legend_name = f"{self.sec_name} Dev (PPM)"

        # ---- Primary ----
        if show_pri:
            # [แก้ไข] เหตุผลเดียวกับ freq_summary_graph.py — PlotDataItem ทำ log10 อัตโนมัติ
            # เองอยู่แล้วเมื่อ setLogMode(x=True) ต้องป้อนความถี่ดิบเข้า setData()
            # ส่วน TextItem (Data Labels) ต้องคำนวณ log10 เองเพราะไม่อยู่ใน auto-log pipeline
            raw_fx = np.array(pri_fx, dtype=float)
            label_fx = np.log10(raw_fx) if is_log else raw_fx
            vy = np.array(pri_vy, dtype=float)
            self.curve_pri.setData(raw_fx, vy)
            self.curve_pri.setVisible(True)
            if self.chk_show_legend.isChecked():
                self.legend.addItem(self.curve_pri, pri_legend_name)
            if self.chk_error_bar.isChecked():
                ey = np.array(pri_ey, dtype=float)
                # [แก้ไข] ErrorBarItem ไม่อยู่ใน pipeline auto-log ของ setLogMode() (เพิ่มด้วย
                # addItem() ไม่ใช่ plot()) ต้องป้อน x ที่ log10 มาแล้วเอง (label_fx) เสมอ
                self.errbar_pri.setData(x=label_fx, y=vy, height=ey * 2)
                self.errbar_pri.setVisible(True)
            else:
                self.errbar_pri.setVisible(False)
            if self.chk_data_labels.isChecked():
                for x, y in zip(label_fx, vy):
                    t = pg.TextItem(f'{y:+.2f}', color='#0a3d91', anchor=(0.5, 1.2))
                    t.setPos(x, y)
                    self.plot_widget.addItem(t)
                    self._data_label_items.append(t)
        else:
            self.curve_pri.setVisible(False)
            self.errbar_pri.setVisible(False)

        # ---- Secondary ----
        if show_sec:
            raw_fx = np.array(sec_fx, dtype=float)
            label_fx = np.log10(raw_fx) if is_log else raw_fx
            vy = np.array(sec_vy, dtype=float)
            self.curve_sec.setData(raw_fx, vy)
            self.curve_sec.setVisible(True)
            if self.chk_show_legend.isChecked():
                self.legend.addItem(self.curve_sec, sec_legend_name)
            if self.chk_error_bar.isChecked():
                ey = np.array(sec_ey, dtype=float)
                # [แก้ไข] เหตุผลเดียวกับ errbar_pri ด้านบน
                self.errbar_sec.setData(x=label_fx, y=vy, height=ey * 2)
                self.errbar_sec.setVisible(True)
            else:
                self.errbar_sec.setVisible(False)
            if self.chk_data_labels.isChecked():
                for x, y in zip(label_fx, vy):
                    t = pg.TextItem(f'{y:+.2f}', color='#8f0050', anchor=(0.5, -0.2))
                    t.setPos(x, y)
                    self.plot_widget.addItem(t)
                    self._data_label_items.append(t)
        else:
            self.curve_sec.setVisible(False)
            self.errbar_sec.setVisible(False)

        self.legend.setVisible(self.chk_show_legend.isChecked() and (show_pri or show_sec))

        # แจ้งเตือนกลางกราฟถ้ามีความถี่ที่วัดแล้วจริง แต่ไม่มีจุด ppm เลย (ไม่ได้เปิด PPM Reference)
        has_any_freq = len(self._freqs) > 0
        has_any_ppm = show_pri or show_sec
        self.no_data_text.setVisible(has_any_freq and not has_any_ppm)
        if self.no_data_text.isVisible():
            vb_range = self.plot_widget.getViewBox().viewRange()
            cx = (vb_range[0][0] + vb_range[0][1]) / 2
            cy = (vb_range[1][0] + vb_range[1][1]) / 2
            self.no_data_text.setPos(cx, cy)

        if show_pri or show_sec:
            vb = self.plot_widget.getViewBox()
            vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            vb.autoRange()

    # --------------------------------------------------------
    def save_as_jpeg(self):
        """เซฟกราฟที่กำลังแสดงอยู่เป็นไฟล์ JPEG โดย default ให้เปิดที่โฟลเดอร์ Downloads
        ของเครื่องผู้ใช้เสมอ (ใช้ QStandardPaths ซึ่งรองรับ Windows/macOS/Linux ให้เอง)"""
        downloads_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
        if not downloads_dir or not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")

        default_name = (self.input_graph_title.text().strip() or "ppm_summary_graph") + ".jpg"
        default_path = os.path.join(downloads_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Graph as JPEG", default_path, "JPEG Image (*.jpg *.jpeg)"
        )
        if not path:
            return
        if not path.lower().endswith(('.jpg', '.jpeg')):
            path += '.jpg'
        try:
            exporter = pg.exporters.ImageExporter(self.plot_widget.plotItem)
            exporter.parameters()['width'] = 1600
            exporter.export(path)
        except Exception as e:
            QMessageBox.warning(self, "Save Failed", f"ไม่สามารถบันทึกไฟล์ได้: {e}")