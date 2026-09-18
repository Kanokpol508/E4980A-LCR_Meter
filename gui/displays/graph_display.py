# กราฟ Live Trend (วาดด้วย pyqtgraph)
#
# [แก้ไข] เดิมเป็น 2 กราฟแยก (Primary กับ Secondary คนละแกน Y คนละ PlotWidget)
# ตอนนี้ปรับให้เป็น "กราฟเดียว" (แกน Y ร่วมกัน) พร้อม Plot Display Options
# แบบเดียวกับ freq_summary_graph.py / ppm_summary_graph.py ได้แก่:
#   - Dropdown เลือก Plot Primary / Plot Secondary / Plot Both
#   - ติ๊กเปิด/ปิด Show Data Labels
#   - ติ๊กเปิด/ปิด Show Legend
#   - Dropdown เลือก Frequency Scale: Linear / Log
#   - แถบ Progress / Current Reading
#   - ช่องตั้งชื่อ Graph Title + ปุ่ม Save เป็น JPEG
#
# หมายเหตุ: แกน X ของกราฟนี้คือ "ลำดับจุดที่วัด (Points)" หรือ "ความถี่ (Hz)"
# แล้วแต่โหมดการวัด (กำหนดผ่าน set_axis_labels) — ไม่ได้ล็อคช่วงตายตัวแบบ
# freq_summary_graph.py เพราะ Live Trend ต้องรองรับทั้งสองกรณี

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
from utils.helpers import NoScrollComboBox, pick_series_unit, format_with_unit

# แยก "ชื่อพารามิเตอร์" กับ "หน่วยในวงเล็บท้ายสุด" เช่น
# "Resistance, R (Ω)" -> ("Resistance, R", "Ω")
_UNIT_RE = re.compile(r"^(.*?)\s*\(([^()]+)\)\s*$")


def _split_name_unit(label: str):
    m = _UNIT_RE.match(label.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return label.strip(), None


class _EngAxisItem(pg.AxisItem):
    """แกนตัวเลข (ใช้ได้ทั้งแกน X และ Y): ย่อหน่วย k, M, G, m, µ, n, p ให้อัตโนมัติ
    เลือก 'หน่วยเดียว' ให้ใช้ร่วมกันทั้งชุด tick ที่กำลังวาด (ดูจากค่าที่มากที่สุดในชุดนั้น)
    และป้องกัน OverflowError ตอนสลับ Linear/Log แล้ว pyqtgraph ส่งค่า tick ที่ใหญ่ผิดปกติมา
    (คัดลอกแนวทางเดียวกับ freq_summary_graph.py / ppm_summary_graph.py เพื่อความสม่ำเสมอ)"""

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

        factor, suffix, tier_idx = 1, '', 3  # index 3 = (1, '') ในตาราง _SUFFIXES ด้านล่าง
        for i, (f, s) in enumerate(self._SUFFIXES):
            if max_abs >= f:
                factor, suffix, tier_idx = f, s, i
                break

        # [แก้ไข] เดิมเลือกหน่วยจากค่ามากสุด (max_abs) เพียงอย่างเดียว ทำให้ช่วงค่าที่
        # "คาบเส้นแบ่งหน่วยพอดี" เช่น 999.96-1000.06 Ω (คาบ 1000 ซึ่งเป็นเส้นแบ่งของ 'k')
        # ถูกบังคับหารด้วย 1000 ทั้งชุด กลายเป็นตัวเลขเศษส่วนอ่านยากอย่าง "0.99998k"
        # ทั้งที่แสดงแบบเลขล้วน "999.98" อ่านง่ายกว่ามาก — ตอนนี้เช็คค่าที่เล็กที่สุด
        # (min_abs) ด้วย ถ้าเมื่อย่อหน่วยแล้วเหลือน้อยกว่า 1 (กลายเป็นเศษส่วน) ให้ถอย
        # กลับไปใช้หน่วยที่เล็กลงเรื่อยๆ จนกว่าค่าทุกจุดจะแสดงเป็นเลขเต็ม (>= 1) ในหน่วยนั้น
        nonzero_vals = [abs(rv) for rv in finite_vals if rv != 0]
        min_abs = min(nonzero_vals) if nonzero_vals else max_abs
        while tier_idx < len(self._SUFFIXES) - 1 and factor > 0 and (min_abs / factor) < 1:
            tier_idx += 1
            factor, suffix = self._SUFFIXES[tier_idx]

        if self.logMode and len(finite_vals) >= 2:
            sorted_vals = sorted(set(round(rv, 12) for rv in finite_vals))
            diffs = [b - a for a, b in zip(sorted_vals, sorted_vals[1:]) if b - a > 0]
            step = min(diffs) if diffs else max_abs
        else:
            step = spacing * scale

        if factor and step > 0:
            step_in_units = step / factor
            decimals = 0 if step_in_units >= 1 else max(0, math.ceil(-math.log10(step_in_units)))
        else:
            decimals = 0

        # [แก้ไข] เดิม cap ทศนิยมไว้ที่ 4 ตำแหน่งเสมอ ทำให้ช่วงค่าที่แคบมากๆ (เช่น
        # 999.95-1000.05 Ω ที่ถูกย่อเป็นหน่วย k) ปัดชนกันจนโชว์ label ซ้ำกัน (ทั้งคู่
        # กลายเป็น "1.0000k") ดูเหมือนแกนผิดเพี้ยนไม่ตรงกับกราฟ
        # ตอนนี้เพิ่มทศนิยมทีละ 1 จนกว่า label ของทุก tick จะไม่ซ้ำกันแล้ว (หรือชน
        # เพดานความปลอดภัยที่ 6 ตำแหน่ง กันเคสหลุดจริงๆ ไม่ให้ตัวเลขยาวจนอ่านไม่ได้)
        if factor and finite_vals:
            scaled_vals = [rv / factor for rv in finite_vals]
            while decimals < 6:
                seen = set()
                collided = False
                for sv in scaled_vals:
                    label = f"{sv:.{decimals}f}"
                    if label in seen:
                        collided = True
                        break
                    seen.add(label)
                if not collided:
                    break
                decimals += 1

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


class GraphDisplay(QWidget):
    # สีให้ตรงกับกราฟสรุปอื่นๆ (freq_summary_graph.py / ppm_summary_graph.py)
    COLOR_PRIMARY = '#789CCE'    # น้ำเงิน
    COLOR_SECONDARY = '#E27A9B'  # แดงอมชมพู

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label_style = {'color': '#1e293b', 'font-size': '10pt', 'font-weight': 'normal'}

        # ชื่อพารามิเตอร์จริงตาม SCPI mode (อัปเดตผ่าน set_axis_labels)
        self.pri_name = "Primary Value"
        self.sec_name = "Secondary Value"
        self.x_label = "Points / Frequency (Hz)"

        # ข้อมูลปัจจุบันของกราฟ
        self._x_data, self._pri_y, self._sec_y = [], [], []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # ==========================================
        # แถบควบคุม: Plot Display Options
        # ==========================================
        group_opts = QGroupBox("Plot Display Options")
        opts_layout = QHBoxLayout()
        opts_layout.setSpacing(12)

        self.combo_plot_select = NoScrollComboBox()
        self.combo_plot_select.addItem("Plot Primary", userData="PRI")
        self.combo_plot_select.addItem("Plot Secondary", userData="SEC")
        self.combo_plot_select.addItem("Plot Both", userData="BOTH")
        self.combo_plot_select.setCurrentIndex(2)  # ค่าเริ่มต้น = Plot Both (เหมือนพฤติกรรมเดิมที่โชว์ทั้งคู่)

        self.chk_data_labels = QCheckBox("Show Data Labels")
        self.chk_data_labels.setChecked(False)
        self.chk_show_legend = QCheckBox("Show Legend")
        self.chk_show_legend.setChecked(True)

        opts_layout.addWidget(QLabel("Plot:"))
        opts_layout.addWidget(self.combo_plot_select)
        opts_layout.addWidget(self.chk_data_labels)
        opts_layout.addWidget(self.chk_show_legend)

        opts_layout.addStretch(1)

        opts_layout.addWidget(QLabel("Frequency Scale:"))
        self.combo_x_scale = NoScrollComboBox()
        self.combo_x_scale.addItems(["Linear", "Log"])
        opts_layout.addWidget(self.combo_x_scale)

        group_opts.setLayout(opts_layout)
        main_layout.addWidget(group_opts)

        # ==========================================
        # แถบ Progress / Current Reading
        # ==========================================
        status_bar = QHBoxLayout()
        lbl_progress_title = QLabel("Progress:")
        lbl_progress_title.setStyleSheet("color: #2C3A5C;")
        status_bar.addWidget(lbl_progress_title)
        self.lbl_progress = QLabel("Idle")
        self.lbl_progress.setStyleSheet("font-weight: bold; color: #2C3A5C;")
        status_bar.addWidget(self.lbl_progress)

        status_bar.addSpacing(20)

        lbl_current_reading_title = QLabel("Current Reading:")
        lbl_current_reading_title.setStyleSheet("color: #2C3A5C;")
        status_bar.addWidget(lbl_current_reading_title)
        self.lbl_current_reading = QLabel("--")
        self.lbl_current_reading.setStyleSheet("font-weight: bold; color: #2C3A5C;")
        status_bar.addWidget(self.lbl_current_reading)

        status_bar.addStretch(1)
        main_layout.addLayout(status_bar)

        # ==========================================
        # แถบ Graph Title + ปุ่ม Save เป็น JPEG
        # ==========================================
        title_bar = QHBoxLayout()
        lbl_graph_title = QLabel("Graph Title:")
        lbl_graph_title.setStyleSheet("color: #2C3A5C;")
        title_bar.addWidget(lbl_graph_title)
        self.input_graph_title = QLineEdit()
        self.input_graph_title.setPlaceholderText("กรอกชื่อกราฟที่ต้องการ")
        title_bar.addWidget(self.input_graph_title, stretch=1)

        self.btn_save_jpeg = QPushButton("💾 Save as JPEG")
        title_bar.addWidget(self.btn_save_jpeg)
        main_layout.addLayout(title_bar)

        # ==========================================
        # กราฟหลัก (Primary/Secondary รวมในแกน Y เดียวกัน)
        # ==========================================
        self.plot_widget = pg.PlotWidget(
            title="Live Trend",
            axisItems={
                'bottom': _EngAxisItem(orientation='bottom'),
                'left':   _EngAxisItem(orientation='left'),
            }
        )
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._style_axes_dark(self.plot_widget)
        self.plot_widget.setLabel('bottom', self.x_label, **self.label_style)
        self.plot_widget.setLabel('left', 'Value', **self.label_style)

        vb = self.plot_widget.getViewBox()
        vb.setLimits(xMin=0)  # ล็อคไม่ให้เลื่อนซ้ายทะลุเลข 0 ไปติดลบ
        vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot_widget.setXRange(0, 10)  # เปิดโปรแกรมมาให้โชว์สเกล 0 ถึง 10
        self.plot_widget.setYRange(0, 1)   # ป้องกัน pyqtgraph คำนวณขอบเขตเป็น NaN ตอนยังไม่มีข้อมูล

        # legend มุมขวาบนของกราฟ — เพิ่ม/ลบ item เองแบบ dynamic ตามเส้นที่เปิด/ปิดจริง
        self.legend = pg.LegendItem(offset=None)
        self.legend.setParentItem(self.plot_widget.plotItem)
        self.legend.anchor(itemPos=(1, 0), parentPos=(1, 0), offset=(-10, 10))

        self.curve_primary = self.plot_widget.plot(
            pen=pg.mkPen(self.COLOR_PRIMARY, width=2), symbol='o',
            symbolSize=6, symbolBrush=self.COLOR_PRIMARY
        )
        self.curve_secondary = self.plot_widget.plot(
            pen=pg.mkPen(self.COLOR_SECONDARY, width=2), symbol='o',
            symbolSize=6, symbolBrush=self.COLOR_SECONDARY
        )

        self._data_label_items = []  # เก็บ TextItem ไว้ลบทิ้งตอน redraw

        main_layout.addWidget(self.plot_widget, stretch=1)

        # ==========================================
        # Signal เชื่อมต่อ: เปลี่ยนตัวเลือกแล้ว redraw ทันที
        # ==========================================
        for w in (self.chk_data_labels, self.chk_show_legend):
            w.stateChanged.connect(self._redraw)
        self.combo_plot_select.currentIndexChanged.connect(self._redraw)
        self.combo_x_scale.currentTextChanged.connect(self._on_scale_changed)
        self.input_graph_title.textChanged.connect(self._redraw)
        self.btn_save_jpeg.clicked.connect(self.save_as_jpeg)

        self._redraw()

    # --------------------------------------------------------
    def is_plot_primary_enabled(self) -> bool:
        return self.combo_plot_select.currentData() in ("PRI", "BOTH")

    def is_plot_secondary_enabled(self) -> bool:
        return self.combo_plot_select.currentData() in ("SEC", "BOTH")

    # --------------------------------------------------------
    def _style_axes_dark(self, plot_widget):
        """ปรับสีเส้นแกนและตัวเลขสเกลให้เป็นสีเข้ม อ่านง่ายบนพื้นหลังสีขาว"""
        for axis_name in ('left', 'bottom'):
            axis = plot_widget.getAxis(axis_name)
            axis.setPen(pg.mkPen('#334155'))
            axis.setTextPen(pg.mkPen('#1e293b'))

    # --------------------------------------------------------
    def _on_scale_changed(self, *args):
        """สลับ Linear/Log แกน X — ต้องรีเซ็ต view range ก่อน redraw เสมอ กัน pyqtgraph
        เก็บ range เก่ามาตีความผิดเป็น log-space จนได้ tick ค่ามหาศาลแล้ว overflow ตอน 10**v"""
        is_log = (self.combo_x_scale.currentText().lower() == 'log')
        # แกน X เป็นค่า "จุด/ความถี่" เท่านั้น (>0 เสมอ) จึงใช้ log mode กับแกน X ได้อย่างเดียว
        self.plot_widget.setLogMode(x=is_log, y=False)
        if len(self._x_data) == 0:
            if is_log:
                self.plot_widget.setXRange(0, 1)
            else:
                self.plot_widget.setXRange(0, 10)
        self._redraw()

    # --------------------------------------------------------
    def set_axis_labels(self, x_label: str, pri_y_label: str, sec_y_label: str, is_single_mode: bool):
        """ตั้งชื่อแกน และปรับรูปแบบสเกล"""
        self.x_label = x_label
        self.pri_name = pri_y_label
        self.sec_name = sec_y_label
        self._redraw()

    # --------------------------------------------------------
    def _group_y_label(self, show_pri: bool, show_sec: bool) -> str:
        """ตั้งชื่อแกน Y ตาม 'กลุ่มพารามิเตอร์' ที่เลือกอยู่จริง ถ้าหน่วยเหมือนกันทั้งคู่
        (เช่น Re/Im เป็น Ω ทั้งคู่) ให้รวมเป็นกลุ่มเดียว แทนที่จะเขียนหน่วยซ้ำสองรอบ"""
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
        return "Value"

    # --------------------------------------------------------
    def update_plots(self, x_data: list, pri_y_data: list, sec_y_data: list):
        """อัปเดตเส้นกราฟ"""
        self._x_data = x_data
        self._pri_y = pri_y_data
        self._sec_y = sec_y_data
        self._redraw()

    # --------------------------------------------------------
    def _redraw(self, *args):
        # ล้าง data label เก่าทุกครั้ง
        for item in self._data_label_items:
            self.plot_widget.removeItem(item)
        self._data_label_items.clear()

        # ล้าง legend เก่าทุกครั้ง แล้วค่อยเติมเฉพาะเส้นที่ "เปิด" ตอนนี้จริงๆ
        self.legend.clear()

        title = self.input_graph_title.text().strip()
        self.plot_widget.setTitle(title if title else "Live Trend")

        self.plot_widget.setLabel('bottom', self.x_label, **self.label_style)

        x = np.array(self._x_data, dtype=float) if self._x_data else np.array([])

        # [แก้ไข] บั๊ก Log Scale ผิดเพี้ยน: PlotDataItem (เส้นกราฟ) ทำ log10() ให้ข้อมูล
        # "อัตโนมัติ" อยู่แล้วเมื่อ setLogMode(x=True) เปิดอยู่ จึงต้องป้อนค่า x ดิบให้มันเสมอ
        # แต่ TextItem (Data Labels) ไม่ได้อยู่ใน pipeline auto-log นี้ (แค่ setPos ธรรมดา)
        # ถ้าป้อน x ดิบให้ TextItem ตอน Log mode เปิดอยู่ ViewBox จะตีความค่า x ดิบเป็น
        # ตำแหน่ง "log-space" ตรงๆ (เช่น x=20 กลายเป็น 10**20) ทำให้ autoRange() พังยับ
        # ต้องคำนวณตำแหน่ง x ของ TextItem เป็น log10(x) เองเสมอเมื่อ Log mode เปิดอยู่
        is_log = (self.combo_x_scale.currentText().lower() == 'log')
        label_x = np.log10(x) if (is_log and len(x)) else x

        show_pri = self.is_plot_primary_enabled() and len(x) > 0
        show_sec = self.is_plot_secondary_enabled() and len(x) > 0

        self.plot_widget.setLabel('left', self._group_y_label(show_pri, show_sec), **self.label_style)

        # ---- Primary ----
        if show_pri:
            pri_y = np.array(self._pri_y, dtype=float)
            self.curve_primary.setData(x, pri_y)
            self.curve_primary.setVisible(True)
            if self.chk_show_legend.isChecked():
                self.legend.addItem(self.curve_primary, self.pri_name)
            if self.chk_data_labels.isChecked():
                # [แก้ไข] เดิมคำนวณหน่วยเดียวใช้ร่วมกันทั้งเส้น (pick_series_unit(pri_y.tolist()))
                # ถ้าเส้นนี้มีค่ากวาดข้ามหลายสิบเท่าตัว (เช่น SWEEP/LIST mode ที่ค่าดิบมาจาก
                # หลายความถี่ต่างกันมาก) หน่วยจะถูกบังคับให้เล็กลงตามจุดที่เล็กที่สุดในเส้น
                # (ดู pick_series_unit()) ทำให้จุดที่ค่าใหญ่ถูกหารด้วยหน่วยที่เล็กเกินไป
                # มหาศาล กลายเป็นตัวเลขบวมผิดปกติ ไม่ตรงกับค่าจริงในตารางสถิติ (ดูปัญหา
                # เดียวกันใน freq_summary_graph.py) ตอนนี้เลือกหน่วยแยก "ทีละจุด" แทน
                for xi, yi in zip(label_x, pri_y):
                    factor, suffix, decimals = pick_series_unit([yi])
                    t = pg.TextItem(format_with_unit(yi, factor, suffix, decimals, show_suffix=False), color='#0a3d91', anchor=(0.5, 1.2))
                    t.setPos(xi, yi)
                    self.plot_widget.addItem(t)
                    self._data_label_items.append(t)
        else:
            self.curve_primary.setVisible(False)

        # ---- Secondary ----
        if show_sec:
            sec_y = np.array(self._sec_y, dtype=float)
            self.curve_secondary.setData(x, sec_y)
            self.curve_secondary.setVisible(True)
            if self.chk_show_legend.isChecked():
                self.legend.addItem(self.curve_secondary, self.sec_name)
            if self.chk_data_labels.isChecked():
                # [แก้ไข] เหตุผลเดียวกับ Primary ด้านบน — เลือกหน่วยทีละจุดแทนหน่วยเดียว
                # ร่วมทั้งเส้น กัน label บวมผิดปกติเมื่อเส้นมีค่ากวาดข้ามหลายสิบเท่าตัว
                for xi, yi in zip(label_x, sec_y):
                    factor, suffix, decimals = pick_series_unit([yi])
                    t = pg.TextItem(format_with_unit(yi, factor, suffix, decimals, show_suffix=False), color='#8f0050', anchor=(0.5, -0.2))
                    t.setPos(xi, yi)
                    self.plot_widget.addItem(t)
                    self._data_label_items.append(t)
        else:
            self.curve_secondary.setVisible(False)

        # legend ไม่มีอะไรเปิดเลย (หรือผู้ใช้ปิด Show Legend) ให้ซ่อนกล่อง legend ไปเลย
        self.legend.setVisible(self.chk_show_legend.isChecked() and (show_pri or show_sec))

        # บังคับให้ขยับสเกลอัตโนมัติตลอดเวลา (Force Auto-Scale) เฉพาะตอนมีข้อมูลจริงแล้ว
        if len(x) > 0:
            vb = self.plot_widget.getViewBox()
            vb.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
            vb.autoRange()

    # --------------------------------------------------------
    def clear_plots(self):
        """ล้างข้อมูลบนกราฟ"""
        self._x_data, self._pri_y, self._sec_y = [], [], []
        self._redraw()

        # รีเซ็ตกราฟกลับไปที่ระยะเริ่มต้นเหมือนตอนเปิดโปรแกรมใหม่
        is_log = (self.combo_x_scale.currentText().lower() == 'log')
        if is_log:
            self.plot_widget.setXRange(0, 1)
        else:
            self.plot_widget.setXRange(0, 10)
        self.plot_widget.setYRange(0, 1)

        self.set_progress("Idle")
        self.set_current_reading("--")

    # --------------------------------------------------------
    def set_progress(self, text: str):
        """เรียกจาก app_controller ระหว่างวัด เพื่อบอกสถานะภาพรวม"""
        self.lbl_progress.setText(text)

    def set_current_reading(self, text: str):
        """เรียกจาก app_controller ทุกครั้งที่มีจุดข้อมูลใหม่เข้ามา เพื่อบอกค่าที่อ่านได้ล่าสุด"""
        self.lbl_current_reading.setText(text)

    # --------------------------------------------------------
    def save_as_jpeg(self):
        """เซฟกราฟที่กำลังแสดงอยู่เป็นไฟล์ JPEG โดย default ให้เปิดที่โฟลเดอร์ Downloads
        ของเครื่องผู้ใช้เสมอ (ใช้ QStandardPaths ซึ่งรองรับ Windows/macOS/Linux ให้เอง)"""
        downloads_dir = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
        if not downloads_dir or not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")

        default_name = (self.input_graph_title.text().strip() or "live_trend_graph") + ".jpg"
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