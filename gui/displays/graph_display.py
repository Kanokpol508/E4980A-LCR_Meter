# วาดกราฟด้วย pyqtgraph (วาดแกน Y แยกอิสระ) พร้อมแสดงสถิติ

import math
import statistics
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox
from PyQt6.QtCore import Qt
import pyqtgraph as pg

class StatPanel(QGroupBox):
    """คอมโพเนนต์ย่อยสำหรับแสดงสถิติข้างกราฟ (SD, Type A)"""
    def __init__(self, title, parent=None):
        super().__init__(title, parent)
        self.setFixedWidth(240)  
        self.setObjectName("statGroup") 
        
        layout = QVBoxLayout(self) 
        layout.setSpacing(2)
        layout.setContentsMargins(15, 10, 15, 15)
        
        # 1. SD
        lbl_title_sd = QLabel("Standard Deviation (SD):")
        lbl_title_sd.setObjectName("lblStatTitle")
        layout.addWidget(lbl_title_sd)
        
        self.lbl_sd = QLabel("-")
        self.lbl_sd.setObjectName("lblStatValue")
        self.lbl_sd.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_sd)
        
        # 2. Type A
        lbl_title_type_a = QLabel("Type A (ppm):")
        lbl_title_type_a.setObjectName("lblStatTitle")
        layout.addWidget(lbl_title_type_a)
        
        self.lbl_type_a = QLabel("-")
        self.lbl_type_a.setObjectName("lblStatValue")
        self.lbl_type_a.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.lbl_type_a)
        
        layout.addStretch() 

    def update_stats(self, raw_data: list, is_single_mode: bool):
        """คำนวณและอัปเดตสถิติจากค่าดิบ"""
        if not is_single_mode or not raw_data:
            self.lbl_sd.setText("-")
            self.lbl_type_a.setText("-")
            return
            
        n = len(raw_data)
        if n < 2:
            self.lbl_sd.setText("-")
            self.lbl_type_a.setText("-")
            return
            
        try:
            sd = statistics.stdev(raw_data)
            mean = statistics.mean(raw_data)
            
            self.lbl_sd.setText(f"{sd:.5e}")
            
            if mean == 0:
                self.lbl_type_a.setText("N/A")
                self.lbl_type_a.setToolTip("Mean is 0, cannot calculate ppm")
            else:
                type_a_ppm = (sd / math.sqrt(n)) / abs(mean) * 1e6
                self.lbl_type_a.setText(f"{type_a_ppm:.2f}")
                
        except Exception:
            self.lbl_sd.setText("Error")
            self.lbl_type_a.setText("Error")


class GraphDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ปรับฟอนต์ให้เล็กลง บางลง และสีซอฟต์ลง เพื่อไม่ให้แย่งความสนใจจากเส้นกราฟ
        self.label_style = {'color': '#cbd5e1', 'font-size': '10pt', 'font-weight': 'normal'}
        
        # ==========================================
        # 1. กราฟพารามิเตอร์หลัก (Primary) + สถิติ
        # ==========================================
        h_layout_pri = QHBoxLayout()
        
        self.plot_primary = pg.PlotWidget(title="Primary Parameter")
        self.plot_primary.showGrid(x=True, y=True, alpha=0.3)
        self.plot_primary.getViewBox().enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot_primary.getViewBox().setLimits(xMin=0) # ล็อคไม่ให้เลื่อนซ้ายทะลุเลข 0 ไปติดลบ
        self.plot_primary.setXRange(0, 10)               # เปิดโปรแกรมมาให้โชว์สเกล 0 ถึง 10
        self.curve_primary = self.plot_primary.plot(pen=pg.mkPen('c', width=2), symbol='o', symbolSize=6, symbolBrush='c')
        
        # ใส่ชื่อแกนเริ่มต้น (Default Labels) ทันทีที่เปิดโปรแกรม
        self.plot_primary.setLabel('left', 'Primary Value', **self.label_style)
        self.plot_primary.setLabel('bottom', 'Points / Frequency (Hz)', **self.label_style)
        
        self.stat_primary = StatPanel("Primary Statistics")
        
        h_layout_pri.addWidget(self.plot_primary, stretch=1)
        h_layout_pri.addWidget(self.stat_primary)
        main_layout.addLayout(h_layout_pri, stretch=1)

        # ==========================================
        # 2. กราฟพารามิเตอร์รอง (Secondary) + สถิติ
        # ==========================================
        h_layout_sec = QHBoxLayout()
        
        self.plot_secondary = pg.PlotWidget(title="Secondary Parameter")
        self.plot_secondary.showGrid(x=True, y=True, alpha=0.3)
        self.plot_secondary.getViewBox().enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)
        self.plot_secondary.getViewBox().setLimits(xMin=0) # ล็อคไม่ให้เลื่อนซ้ายทะลุเลข 0 ไปติดลบ
        self.plot_secondary.setXRange(0, 10)               # เปิดโปรแกรมมาให้โชว์สเกล 0 ถึง 10
        self.curve_secondary = self.plot_secondary.plot(pen=pg.mkPen('m', width=2), symbol='o', symbolSize=6, symbolBrush='m')
        
        # ใส่ชื่อแกนเริ่มต้น (Default Labels) ทันทีที่เปิดโปรแกรม
        self.plot_secondary.setLabel('left', 'Secondary Value', **self.label_style)
        self.plot_secondary.setLabel('bottom', 'Points / Frequency (Hz)', **self.label_style)
        
        self.stat_secondary = StatPanel("Secondary Statistics")
        
        h_layout_sec.addWidget(self.plot_secondary, stretch=1)
        h_layout_sec.addWidget(self.stat_secondary)
        main_layout.addLayout(h_layout_sec, stretch=1)

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

    def set_stats_visible(self, visible: bool):
        """
        แสดง/ซ่อน StatPanel ทั้งสองข้างกราฟ
        ซ่อนเมื่ออยู่โหมด SWEEP เพราะ N=1 ไม่มีสถิติที่มีความหมาย
        ทำให้พื้นที่กราฟขยายเต็มความกว้างแทน
        """
        self.stat_primary.setVisible(visible)
        self.stat_secondary.setVisible(visible)

    def update_plots(self, x_data: list, pri_y_data: list, sec_y_data: list):
        """อัปเดตเส้นกราฟ"""
        self.curve_primary.setData(x_data, pri_y_data)
        self.curve_secondary.setData(x_data, sec_y_data)
        
        # บังคับให้ขยับสเกลอัตโนมัติตลอดเวลา (Force Auto-Scale)
        self.plot_primary.getViewBox().autoRange()
        self.plot_secondary.getViewBox().autoRange()

    def update_statistics(self, raw_pri_data: list, raw_sec_data: list, is_single_mode: bool):
        """ส่งค่าดิบไปให้ Panel สถิติคำนวณ"""
        self.stat_primary.update_stats(raw_pri_data, is_single_mode)
        self.stat_secondary.update_stats(raw_sec_data, is_single_mode)

    def clear_plots(self):
        """ล้างข้อมูลบนกราฟและสถิติ"""
        self.curve_primary.setData([], [])
        self.curve_secondary.setData([], [])
        self.update_statistics([], [], True)
        
        # รีเซ็ตกราฟกลับไปที่ระยะ 0-10 เหมือนตอนเปิดโปรแกรมใหม่
        self.plot_primary.setXRange(0, 10)
        self.plot_secondary.setXRange(0, 10)