# กล่องเลือกพอร์ต USB/LAN และปุ่ม Connect

from PyQt6.QtWidgets import QWidget, QGroupBox, QHBoxLayout, QComboBox, QPushButton, QSizePolicy

class ConnectionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        group_visa = QGroupBox("VISA Resource")
        h_visa = QHBoxLayout()
        
        self.combo_visa = QComboBox()
        self.combo_visa.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.btn_refresh = QPushButton("REFRESH")
        
        h_visa.addWidget(self.combo_visa, stretch=1)
        h_visa.addWidget(self.btn_refresh)
        group_visa.setLayout(h_visa)
        
        layout.addWidget(group_visa)