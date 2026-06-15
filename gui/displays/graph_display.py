# วาดกราฟด้วย pyqtgraph (วาดแกน Y แยกอิสระ)

from PyQt6.QtWidgets import QWidget, QVBoxLayout
import pyqtgraph as pg

class GraphDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot_primary = pg.PlotWidget(title="กราฟ Primary")
        self.plot_primary.showGrid(x=True, y=True)
        layout.addWidget(self.plot_primary, stretch=2)

        self.plot_secondary = pg.PlotWidget(title="กราฟ Secondary")
        self.plot_secondary.showGrid(x=True, y=True)
        layout.addWidget(self.plot_secondary, stretch=2)