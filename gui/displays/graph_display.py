# วาดกราฟด้วย pyqtgraph (วาดแกน Y แยกอิสระ)

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
import pyqtgraph as pg

class GraphDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ปรับฟอนต์ให้เล็กลง บางลง และสีเข้มพอดี อ่านง่ายบนพื้นหลังสีขาว
        self.label_style = {'color': '#1e293b', 'font-size': '10pt', 'font-weight': 'normal'}
        
        # ==========================================
        # 1. กราฟพารามิเตอร์หลัก (Primary)
        # ==========================================
        h_layout_pri = QHBoxLayout()
        
        self.plot_primary = pg.PlotWidget(title="Primary Parameter")
        self.plot_primary.setBackground('w')  # พื้นหลังกราฟสีขาว
        self.plot_primary.showGrid(x=True, y=True, alpha=0.3)
        self.plot_primary.getViewBox().enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot_primary.getViewBox().setLimits(xMin=0) # ล็อคไม่ให้เลื่อนซ้ายทะลุเลข 0 ไปติดลบ
        self.plot_primary.setXRange(0, 10)               # เปิดโปรแกรมมาให้โชว์สเกล 0 ถึง 10
        # [แก้ไข] ตั้งค่าเริ่มต้นแกน Y ด้วย ป้องกัน pyqtgraph คำนวณขอบเขตเป็น NaN
        # ตอนยังไม่มีข้อมูล (กราฟว่าง) แล้วผู้ใช้ scroll/ลากกราฟ จะ throw
        # "Cannot set range [nan, nan]" รัวๆ — พอมีข้อมูลจริงเข้ามา autoRange() ใน
        # update_plots() จะปรับสเกลให้เข้ากับข้อมูลอัตโนมัติตามเดิมอยู่แล้ว
        self.plot_primary.setYRange(0, 1)
        self.curve_primary = self.plot_primary.plot(pen=pg.mkPen('#0066CC', width=2), symbol='o', symbolSize=6, symbolBrush='#0066CC')
        self._style_axes_dark(self.plot_primary)
        
        # ใส่ชื่อแกนเริ่มต้น (Default Labels) ทันทีที่เปิดโปรแกรม
        self.plot_primary.setLabel('left', 'Primary Value', **self.label_style)
        self.plot_primary.setLabel('bottom', 'Points / Frequency (Hz)', **self.label_style)
        
        h_layout_pri.addWidget(self.plot_primary, stretch=1)
        main_layout.addLayout(h_layout_pri, stretch=1)

        # ==========================================
        # 2. กราฟพารามิเตอร์รอง (Secondary)
        # ==========================================
        h_layout_sec = QHBoxLayout()
        
        self.plot_secondary = pg.PlotWidget(title="Secondary Parameter")
        self.plot_secondary.setBackground('w')  # พื้นหลังกราฟสีขาว
        self.plot_secondary.showGrid(x=True, y=True, alpha=0.3)
        self.plot_secondary.getViewBox().enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot_secondary.getViewBox().setLimits(xMin=0) # ล็อคไม่ให้เลื่อนซ้ายทะลุเลข 0 ไปติดลบ
        self.plot_secondary.setXRange(0, 10)               # เปิดโปรแกรมมาให้โชว์สเกล 0 ถึง 10
        # [แก้ไข] ตั้งค่าเริ่มต้นแกน Y ด้วย เหตุผลเดียวกับกราฟ Primary ด้านบน
        self.plot_secondary.setYRange(0, 1)
        self.curve_secondary = self.plot_secondary.plot(pen=pg.mkPen('#CC0066', width=2), symbol='o', symbolSize=6, symbolBrush='#CC0066')
        self._style_axes_dark(self.plot_secondary)
        
        # ใส่ชื่อแกนเริ่มต้น (Default Labels) ทันทีที่เปิดโปรแกรม
        self.plot_secondary.setLabel('left', 'Secondary Value', **self.label_style)
        self.plot_secondary.setLabel('bottom', 'Points / Frequency (Hz)', **self.label_style)
        
        h_layout_sec.addWidget(self.plot_secondary, stretch=1)
        main_layout.addLayout(h_layout_sec, stretch=1)

    def _style_axes_dark(self, plot_widget):
        """ปรับสีเส้นแกนและตัวเลขสเกลให้เป็นสีเข้ม อ่านง่ายบนพื้นหลังสีขาว"""
        for axis_name in ('left', 'bottom'):
            axis = plot_widget.getAxis(axis_name)
            axis.setPen(pg.mkPen('#334155'))
            axis.setTextPen(pg.mkPen('#1e293b'))

    def set_axis_labels(self, x_label: str, pri_y_label: str, sec_y_label: str, is_single_mode: bool):
        """ตั้งชื่อแกน และปรับรูปแบบสเกล"""
        self.plot_primary.setLabel('bottom', x_label, **self.label_style)
        self.plot_primary.setLabel('left', pri_y_label, **self.label_style)
        
        self.plot_secondary.setLabel('bottom', x_label, **self.label_style)
        self.plot_secondary.setLabel('left', sec_y_label, **self.label_style)

        # ลบการบังคับขีดทีละ 1 ทิ้ง เพื่อให้ pyqtgraph คำนวณ 5, 10, 15 อัตโนมัติเมื่อซูมออก
        # ป้องกันตัวเลขทับกันจนอ่านไม่ออก
        self.plot_primary.getAxis('bottom').setTicks(None)
        self.plot_secondary.getAxis('bottom').setTicks(None)

    def update_plots(self, x_data: list, pri_y_data: list, sec_y_data: list):
        """อัปเดตเส้นกราฟ"""
        self.curve_primary.setData(x_data, pri_y_data)
        self.curve_secondary.setData(x_data, sec_y_data)
        
        # บังคับให้ขยับสเกลอัตโนมัติตลอดเวลา (Force Auto-Scale)
        self.plot_primary.getViewBox().autoRange()
        self.plot_secondary.getViewBox().autoRange()

    def clear_plots(self):
        """ล้างข้อมูลบนกราฟ"""
        self.curve_primary.setData([], [])
        self.curve_secondary.setData([], [])
        
        # รีเซ็ตกราฟกลับไปที่ระยะ 0-10 เหมือนตอนเปิดโปรแกรมใหม่
        self.plot_primary.setXRange(0, 10)
        self.plot_secondary.setXRange(0, 10)
        # [แก้ไข] รีเซ็ตแกน Y ด้วย ป้องกัน NaN range เหมือนตอนเปิดโปรแกรม (ดู __init__)
        self.plot_primary.setYRange(0, 1)
        self.plot_secondary.setYRange(0, 1)