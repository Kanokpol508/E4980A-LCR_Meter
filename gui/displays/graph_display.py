# วาดกราฟด้วย pyqtgraph (วาดแกน Y แยกอิสระ)


from PyQt6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg

class GraphDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # ปรับขนาดฟอนต์ให้ใหญ่ขึ้นเพื่อให้อ่านง่าย
        self.label_style = {'font-size': '12pt', 'font-weight': 'bold'}
        
        # ==========================================
        # 1. กราฟพารามิเตอร์หลัก (Primary Graph)
        # ==========================================
        self.plot_primary = pg.PlotWidget(title="Primary Parameter")
        self.plot_primary.showGrid(x=True, y=True, alpha=0.3)
        
        # เปิดระบบ Auto-Scale อัตโนมัติ (ซูมพอดีกับข้อมูลเสมอ)
        self.plot_primary.getViewBox().enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        
        # เส้นกราฟ (ใช้สีฟ้า Cyan ตัดกับพื้นหลังมืด)
        self.curve_primary = self.plot_primary.plot(
            pen=pg.mkPen('c', width=2),     
            symbol='o', symbolSize=6,       
            symbolBrush='c'
        )
        layout.addWidget(self.plot_primary, stretch=2)


        # ==========================================
        # 2. กราฟพารามิเตอร์รอง (Secondary Graph)
        # ==========================================
        self.plot_secondary = pg.PlotWidget(title="Secondary Parameter")
        self.plot_secondary.showGrid(x=True, y=True, alpha=0.3)
        
        # เปิดระบบ Auto-Scale อัตโนมัติ
        self.plot_secondary.getViewBox().enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        
        # เส้นกราฟ (ใช้สีม่วงแดง Magenta ตัดกับพื้นหลังมืด)
        self.curve_secondary = self.plot_secondary.plot(
            pen=pg.mkPen('m', width=2),     
            symbol='o', symbolSize=6,
            symbolBrush='m'
        )
        layout.addWidget(self.plot_secondary, stretch=2)

    def set_axis_labels(self, x_label: str, pri_y_label: str, sec_y_label: str, is_log_x: bool, is_single_mode: bool):
        """ตั้งชื่อแกน และปรับรูปแบบสเกล (Log/Linear หรือ จำนวนเต็ม)"""
        
        # ตั้งชื่อแกนพร้อมสไตล์
        self.plot_primary.setLabel('bottom', x_label, **self.label_style)
        self.plot_primary.setLabel('left', pri_y_label, **self.label_style)
        
        self.plot_secondary.setLabel('bottom', x_label, **self.label_style)
        self.plot_secondary.setLabel('left', sec_y_label, **self.label_style)

        # การปรับสเกลแกน X เป็น Logarithmic (ถ้าโหมด Sweep เลือก Log ไว้)
        self.plot_primary.setLogMode(x=is_log_x, y=False)
        self.plot_secondary.setLogMode(x=is_log_x, y=False)

        # การปรับรูปแบบตัวเลขแกน X
        axis_pri = self.plot_primary.getAxis('bottom')
        axis_sec = self.plot_secondary.getAxis('bottom')
        
        if is_single_mode:
            # โหมดจุดเดียว แกน X เป็น "ครั้งที่" (Measurement Count) บังคับให้โชว์เลขจำนวนเต็ม (1, 2, 3...)
            axis_pri.setTickSpacing(major=1, minor=1)
            axis_sec.setTickSpacing(major=1, minor=1)
        else:
            # โหมด Sweep ให้ pyqtgraph จัดการความห่างของความถี่ให้เหมาะสมอัตโนมัติ
            # แก้ไขจาก setTickSpacing() เป็น setTicks(None) เพื่อป้องกันบั๊กในบางเวอร์ชัน
            axis_pri.setTicks(None) 
            axis_sec.setTicks(None)

    def update_plots(self, x_data: list, pri_y_data: list, sec_y_data: list):
        """รับข้อมูลลิสต์มาพล็อตกราฟ และให้ Auto-Scale ทำงาน"""
        self.curve_primary.setData(x_data, pri_y_data)
        self.curve_secondary.setData(x_data, sec_y_data)

    def clear_plots(self):
        """ล้างข้อมูลบนกราฟ (ใช้ก่อนเริ่มการวัดใหม่)"""
        self.curve_primary.setData([], [])
        self.curve_secondary.setData([], [])