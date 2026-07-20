# กราฟสรุปผล vs ความถี่ (Frequency Summary Graph)
# ต่างจาก graph_display.py (แกน X = ลำดับจุดที่วัดจริง / raw sequence)
# กราฟนี้แกน X = ความถี่ (เรียงจากน้อยไปมาก) แสดงค่าเฉลี่ย (Mean) ต่อความถี่
# ใช้ได้เฉพาะโหมด LIST / SWEEP เท่านั้น (ต้องมีหลายความถี่ถึงจะมีเส้นแนวโน้ม)
#
# แกน X/Y ใช้สไตล์เดียวกับ ppm_summary_graph.py (Eng notation, กันค่า overflow ตอนสลับ
# Linear/Log, ล็อคขอบเขตไม่ให้เลื่อน/ซูมหลุดช่วงสเปคเครื่อง)

import os
import re
import math
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLabel, QLineEdit, QComboBox, QPushButton, QFileDialog, QMessageBox
)
from PyQt6.QtCore import QStandardPaths
import pyqtgraph as pg
import pyqtgraph.exporters

# แยก "ชื่อพารามิเตอร์" กับ "หน่วยในวงเล็บท้ายสุด" เช่น
# "Resistance, R (Ω)" -> ("Resistance, R", "Ω")
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
    จำกัดขอบเขตการวาดตัวเลขให้อยู่ในสเปคเครื่อง (0 - 2.1MHz)
    และป้องกัน OverflowError ตอนสลับ Linear/Log แล้ว pyqtgraph ส่งค่า tick ที่ใหญ่ผิดปกติมา
    (เช่น 10**v ตอน v มีค่ามากเกินกว่าที่ float รองรับ)"""

    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            # log10(20Hz) ~= 1.3, log10(2.1MHz) ~= 6.32 — ค่าที่สมเหตุสมผลไม่ควรหลุดช่วงนี้มาก
            # ถ้า v หลุดช่วงนี้ไปไกล (เช่น ตอนสลับ Linear/Log แล้ว pyqtgraph ยังไม่ทัน sync
            # view range ใหม่) ให้ทิ้ง tick นั้นไปเลยโดยไม่คำนวณ 10**v ต่อ กัน OverflowError
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
    """แกนพารามิเตอร์ (Y): รองรับค่าติดลบได้ ย่อหน่วยได้ทุกระดับ (k, m, µ ...)
    และป้องกัน OverflowError แบบเดียวกับแกน X

    ต่างจากเวอร์ชันก่อนหน้า: เลือก 'หน่วยเดียว' ให้ใช้ร่วมกันทั้งชุด tick ที่กำลังวาด
    (ดูจากค่าที่มากที่สุดในชุดนั้น) แทนที่จะให้แต่ละ tick เลือกหน่วยของตัวเองอิสระ —
    กันปัญหาแกนเดียวกันมีทั้ง '500m', '1', '1.5k' ปนกันจนอ่านยาก และคำนวณจำนวนทศนิยม
    จาก spacing จริงของ tick กันตัวเลขงอกเป็นเศษ (เช่น 12.9999k จาก error สะสมของ float)
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
        # กันตัวเลขงอกเป็นเศษเวลา zoom เข้าไปดูช่วงแคบๆ
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


class FreqSummaryGraph(QWidget):
    # สี Primary/Secondary ให้ตรงกับกราฟหลัก (graph_display.py) เพื่อไม่ให้ผู้ใช้สับสน
    COLOR_PRIMARY = '#0066CC'    # น้ำเงิน
    COLOR_SECONDARY = '#CC0066'  # แดงอมชมพู

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label_style = {'color': '#1e293b', 'font-size': '10pt', 'font-weight': 'normal'}

        # ชื่อพารามิเตอร์จริงตาม SCPI mode (อัปเดตผ่าน set_axis_labels)
        self.pri_name = "Primary"
        self.sec_name = "Secondary"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ==========================================
        # แถบควบคุม: Plot Display Options
        # เรียงลำดับ: checkbox ต่างๆ ชิดซ้าย -> stretch -> Frequency Scale ชิดขวาสุด
        # ==========================================
        group_opts = QGroupBox("Plot Display Options")
        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(12)

        self.chk_plot_pri = QCheckBox("Plot Primary")
        self.chk_plot_pri.setChecked(True)
        self.chk_plot_sec = QCheckBox("Plot Secondary")
        self.chk_plot_sec.setChecked(True)
        self.chk_error_bar = QCheckBox("Show SD Error Bars")
        self.chk_error_bar.setChecked(True)
        self.chk_data_labels = QCheckBox("Show Data Labels")
        self.chk_data_labels.setChecked(False)
        self.chk_show_legend = QCheckBox("Show Legend")
        self.chk_show_legend.setChecked(True)

        opts_layout.addWidget(self.chk_plot_pri)
        opts_layout.addWidget(self.chk_plot_sec)
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
        # แถบ Graph Title + ปุ่ม Save เป็น JPEG
        # ==========================================
        title_bar = QHBoxLayout()
        title_bar.addWidget(QLabel("Graph Title:"))
        self.input_graph_title = QLineEdit()
        self.input_graph_title.setPlaceholderText("เช่น 10kOhm Resistor vs Frequency")
        title_bar.addWidget(self.input_graph_title, stretch=1)

        self.btn_save_jpeg = QPushButton("💾 Save as JPEG")
        title_bar.addWidget(self.btn_save_jpeg)
        main_layout.addLayout(title_bar)

        # ==========================================
        # กราฟหลัก (Primary/Secondary รวมในแกน Y เดียวกัน)
        # ==========================================
        self.plot_widget = pg.PlotWidget(
            title="Mean vs. Frequency",
            axisItems={
                'bottom': _FreqEngAxisItem(orientation='bottom'),
                'left':   _EngAxisItem(orientation='left'),
            }
        )
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._style_axes_dark(self.plot_widget)
        self.plot_widget.setLabel('bottom', 'Frequency (Hz)', **self.label_style)
        self.plot_widget.setLabel('left', 'Mean Value', **self.label_style)

        # ตั้งช่วงเริ่มต้นให้เป็นช่วงความถี่ทั่วไปของเครื่อง LCR (20Hz - 2.1MHz)
        # เผื่อขอบไว้นิดหน่อยกันข้อมูลที่วัดได้พอดี 2MHz ไปติดขอบกราฟ
        self.plot_widget.setXRange(FREQ_MIN, FREQ_MAX_BUFFERED)

        vb = self.plot_widget.getViewBox()
        # ล็อคไม่ให้เลื่อน/ซูมแกน X หลุดช่วงความถี่ที่เครื่อง E4980A รองรับจริง (0 - 2.1MHz)
        vb.setLimits(xMin=0, xMax=FREQ_MAX_BUFFERED)
        vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)  # ขยับ/ย่อสเกลตามข้อมูลที่เข้ามาใหม่เสมอ

        # legend มุมขวาบนของกราฟ (เหมือนโปรแกรมรุ่นพี่) — เพิ่ม/ลบ item เองแบบ dynamic
        # ตามเส้นที่เปิด/ปิดจริง ไม่ใช้ plotItem.legend ที่เก็บ item ตายตัวไว้ตั้งแต่ต้น
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

        self._data_label_items = []  # เก็บ TextItem ไว้ลบทิ้งตอน redraw

        main_layout.addWidget(self.plot_widget, stretch=1)

        # ==========================================
        # Signal เชื่อมต่อ: เปลี่ยนตัวเลือกแล้ว redraw ทันที
        # ==========================================
        for w in (self.chk_plot_pri, self.chk_plot_sec, self.chk_error_bar,
                  self.chk_data_labels, self.chk_show_legend):
            w.stateChanged.connect(self._redraw)
        self.combo_x_scale.currentTextChanged.connect(self._on_scale_changed)
        self.input_graph_title.textChanged.connect(self._redraw)
        self.btn_save_jpeg.clicked.connect(self.save_as_jpeg)

        self._freqs, self._pri_mean, self._pri_sd = [], [], []
        self._sec_mean, self._sec_sd = [], []

        self._redraw()

    # --------------------------------------------------------
    def _style_axes_dark(self, plot_widget):
        for axis_name in ('left', 'bottom'):
            axis = plot_widget.getAxis(axis_name)
            axis.setPen(pg.mkPen('#334155'))
            axis.setTextPen(pg.mkPen('#1e293b'))

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
    def set_axis_labels(self, pri_label: str, sec_label: str):
        """เรียกจาก app_controller ตอนเปลี่ยน SCPI mode — เก็บชื่อพารามิเตอร์จริงไว้ใช้
        เป็นทั้งชื่อแกน Y และชื่อเส้นใน Legend (แทนคำว่า Primary/Secondary เฉยๆ)"""
        self.pri_name = pri_label
        self.sec_name = sec_label
        self._redraw()

    def update_data(self, freqs: list, pri_mean: list, pri_sd: list,
                     sec_mean: list, sec_sd: list):
        """freqs ต้องเรียงจากน้อยไปมากแล้ว (ผลจาก calculate_frequency_stats)"""
        self._freqs = freqs
        self._pri_mean, self._pri_sd = pri_mean, pri_sd
        self._sec_mean, self._sec_sd = sec_mean, sec_sd
        self._redraw()

    def clear(self):
        self._freqs, self._pri_mean, self._pri_sd = [], [], []
        self._sec_mean, self._sec_sd = [], []
        self._redraw()
        is_log = (self.combo_x_scale.currentText().lower() == 'log')
        if is_log:
            self.plot_widget.setXRange(math.log10(FREQ_MIN), math.log10(FREQ_MAX_BUFFERED))
        else:
            self.plot_widget.setXRange(FREQ_MIN, FREQ_MAX_BUFFERED)

    # --------------------------------------------------------
    def _group_y_label(self, show_pri: bool, show_sec: bool) -> str:
        """ตั้งชื่อแกน Y ตาม 'กลุ่มพารามิเตอร์' ที่ติ๊กเปิดอยู่จริง
        ถ้าหน่วยเหมือนกันทั้งคู่ (เช่น Re/Im เป็น Ω ทั้งคู่) ให้รวมเป็นกลุ่มเดียว
        เช่น 'Resistance, R & Reactance, X (Ω)' แทนที่จะเขียนหน่วยซ้ำสองรอบ"""
        pri_text, pri_unit = _split_name_unit(self.pri_name)
        sec_text, sec_unit = _split_name_unit(self.sec_name)

        if show_pri and show_sec:
            if pri_unit and pri_unit == sec_unit:
                return f"{pri_text} & {sec_text} ({pri_unit})"
            return f"{self.pri_name} & {self.sec_name}"
        elif show_pri:
            return self.pri_name
        elif show_sec:
            return self.sec_name
        return "Mean Value"

    # --------------------------------------------------------
    def _redraw(self, *args):
        # ล้าง data label เก่าทุกครั้ง
        for item in self._data_label_items:
            self.plot_widget.removeItem(item)
        self._data_label_items.clear()

        # ล้าง legend เก่าทุกครั้ง แล้วค่อยเติมเฉพาะเส้นที่ "เปิด" ตอนนี้จริงๆ
        self.legend.clear()

        title = self.input_graph_title.text().strip()
        self.plot_widget.setTitle(title if title else "Mean vs. Frequency")

        is_log = (self.combo_x_scale.currentText().lower() == 'log')

        freqs = np.array(self._freqs, dtype=float) if self._freqs else np.array([])
        # [แก้ไข] บั๊ก Log Scale ผิดเพี้ยน: pyqtgraph's PlotDataItem (เส้นกราฟ/error bar) จะทำ
        # log10() ให้กับข้อมูลที่ป้อนเข้าไป "อัตโนมัติ" อยู่แล้วเมื่อ setLogMode(x=True) เปิดอยู่
        # โค้ดเดิม log10(freqs) เองก่อนป้อนเข้า setData() ทำให้โดน log10 ซ้ำสอง
        # (กลายเป็น log10(log10(f)) ตำแหน่งจุดเลยหดมารวมกันแคบๆ แถว x=2-3 ผิดตำแหน่งจริง)
        # ต้องป้อนความถี่ "ดิบ" ให้ PlotDataItem เสมอ ปล่อยให้มันทำ log10 เอง
        #
        # ส่วน TextItem (Data Labels) ไม่ได้อยู่ใน pipeline auto-log ของ PlotDataItem
        # (แค่ setPos ธรรมดา) จึงยังต้องคำนวณตำแหน่ง x เป็น log10(freq) เองอยู่เหมือนเดิม
        plot_x = freqs
        label_x = np.log10(freqs) if (is_log and len(freqs)) else freqs

        show_pri = self.chk_plot_pri.isChecked() and len(freqs) > 0
        show_sec = self.chk_plot_sec.isChecked() and len(freqs) > 0

        # ---- ชื่อแกน Y ตามกลุ่มพารามิเตอร์ที่เลือกจริง ----
        self.plot_widget.setLabel('left', self._group_y_label(show_pri, show_sec), **self.label_style)

        pri_legend_name = f"{self.pri_name} (Mean)"
        sec_legend_name = f"{self.sec_name} (Mean)"

        # ---- Primary ----
        if show_pri:
            means = np.array(self._pri_mean, dtype=float)
            self.curve_pri.setData(plot_x, means)
            self.curve_pri.setVisible(True)
            if self.chk_show_legend.isChecked():
                self.legend.addItem(self.curve_pri, pri_legend_name)
            if self.chk_error_bar.isChecked():
                sds = np.array(self._pri_sd, dtype=float)
                # [แก้ไข] ErrorBarItem ถูกเพิ่มด้วย addItem() ไม่ใช่ plot() จึงไม่อยู่ใน
                # รายการ items ที่ setLogMode() ของ PlotItem จะแจ้งเตือน/ทำ log10 ให้อัตโนมัติ
                # เหมือน PlotDataItem (เส้นกราฟ) — ต้องป้อนตำแหน่ง x ที่ log10 มาแล้วเอง
                # (label_x) ไม่งั้น ViewBox จะตีความค่าความถี่ดิบเป็นพิกัด log-space ตรงๆ
                # ทำให้ผิดเพี้ยนมหาศาล (แกนโชว์ตัวคูณ x1e+27 อย่างที่เจอ)
                self.errbar_pri.setData(x=label_x, y=means, height=sds * 2)
                self.errbar_pri.setVisible(True)
            else:
                self.errbar_pri.setVisible(False)
            if self.chk_data_labels.isChecked():
                for x, y in zip(label_x, means):
                    t = pg.TextItem(f'{y:.5e}', color='#0a3d91', anchor=(0.5, 1.2))
                    t.setPos(x, y)
                    self.plot_widget.addItem(t)
                    self._data_label_items.append(t)
        else:
            self.curve_pri.setVisible(False)
            self.errbar_pri.setVisible(False)

        # ---- Secondary ----
        if show_sec:
            means = np.array(self._sec_mean, dtype=float)
            self.curve_sec.setData(plot_x, means)
            self.curve_sec.setVisible(True)
            if self.chk_show_legend.isChecked():
                self.legend.addItem(self.curve_sec, sec_legend_name)
            if self.chk_error_bar.isChecked():
                sds = np.array(self._sec_sd, dtype=float)
                # [แก้ไข] เหตุผลเดียวกับ errbar_pri ด้านบน — ต้องใช้ label_x (log10 แล้ว)
                self.errbar_sec.setData(x=label_x, y=means, height=sds * 2)
                self.errbar_sec.setVisible(True)
            else:
                self.errbar_sec.setVisible(False)
            if self.chk_data_labels.isChecked():
                for x, y in zip(label_x, means):
                    t = pg.TextItem(f'{y:.5e}', color='#8f0050', anchor=(0.5, -0.2))
                    t.setPos(x, y)
                    self.plot_widget.addItem(t)
                    self._data_label_items.append(t)
        else:
            self.curve_sec.setVisible(False)
            self.errbar_sec.setVisible(False)

        # legend ไม่มีอะไรเปิดเลย (หรือผู้ใช้ปิด Show Legend) ให้ซ่อนกล่อง legend ไปเลย
        self.legend.setVisible(self.chk_show_legend.isChecked() and (show_pri or show_sec))

        # บังคับขยาย/หดสเกลกราฟให้พอดีกับข้อมูลล่าสุดเสมอ (เฉพาะตอนมีข้อมูลจริงแล้ว
        # ถ้ายังไม่มีข้อมูล คงช่วงเริ่มต้น 20Hz-2.1MHz ไว้ ไม่ปล่อยให้ autoRange ยุบเหลือช่วงแคบๆ)
        if len(freqs) > 0:
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

        default_name = (self.input_graph_title.text().strip() or "freq_summary_graph") + ".jpg"
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