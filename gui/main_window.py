# หน้าต่างหลัก (ประกอบจิ๊กซอว์ทุก panel เข้าด้วยกัน)

from PyQt6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QScrollArea, QTabWidget
from PyQt6.QtCore import Qt, QLocale

from gui.panels.connection_panel import ConnectionPanel
from gui.panels.input_panel import InputPanel
from gui.panels.advanced_panel import AdvancedPanel
from gui.panels.control_panel import ControlPanel
from gui.displays.graph_display import GraphDisplay
from gui.displays.freq_summary_graph import FreqSummaryGraph
from gui.displays.ppm_summary_graph import PpmSummaryGraph
from gui.displays.lcd_display import LcdDisplay
from gui.displays.statistics_table import StatisticsTable
from gui.displays.log_display import LogDisplay
from gui.displays.raw_data_table import RawDataTable 

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("E4980A(20Hz-2MHz) Precision LCR Meter Controller")
        self.resize(1280, 720)
        self.setLocale(QLocale(QLocale.Language.English, QLocale.Country.UnitedStates))

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # ─────────────── ฝั่งซ้าย: แผงควบคุม ─────────────────────────────
        left_panel_container = QWidget()
        left_panel_container.setMinimumWidth(450)
        left_panel_container.setMaximumWidth(500)
        left_main_layout = QVBoxLayout(left_panel_container)
        left_main_layout.setContentsMargins(0, 0, 0, 0)

        self.left_scroll = QScrollArea()
        self.left_scroll.setWidgetResizable(True)
        self.left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.left_content = QWidget()
        left_layout = QVBoxLayout(self.left_content)

        self.conn_panel  = ConnectionPanel()
        self.input_panel = InputPanel()
        self.adv_panel   = AdvancedPanel()
        self.ctrl_panel  = ControlPanel()

        left_layout.addWidget(self.conn_panel)
        left_layout.addWidget(self.input_panel)
        left_layout.addWidget(self.adv_panel)
        left_layout.addStretch(1)

        self.left_scroll.setWidget(self.left_content)
        left_main_layout.addWidget(self.left_scroll, stretch=1)
        left_main_layout.addWidget(self.ctrl_panel,  stretch=0)

        main_layout.addWidget(left_panel_container)

        # ─────────────── ฝั่งขวา: กราฟ / ตารางสถิติ / ข้อมูลดิบ / Log และจอ LCD ──────────────────
        right_layout = QVBoxLayout()

        self.graph_display = GraphDisplay()
        self.freq_summary_graph = FreqSummaryGraph()
        self.ppm_summary_graph = PpmSummaryGraph()
        self.stats_table   = StatisticsTable()
        self.raw_table     = RawDataTable()
        self.log_display   = LogDisplay() 

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.graph_display, "Live Trend Graph")
        self.freq_graph_tab_index = self.right_tabs.addTab(
            self.freq_summary_graph, "Parameter vs Frequency Graph"
        )
        self.ppm_graph_tab_index = self.right_tabs.addTab(
            self.ppm_summary_graph, "PPM vs Frequency Graph"
        )
        self.right_tabs.addTab(self.stats_table,   "Statistics Table")
        self.right_tabs.addTab(self.raw_table,     "Raw Data Table")
        self.right_tabs.addTab(self.log_display,   "Log Display")

        self.lcd_display = LcdDisplay()

        right_layout.addWidget(self.right_tabs,    stretch=1)
        right_layout.addWidget(self.lcd_display,   stretch=0)

        main_layout.addLayout(right_layout)