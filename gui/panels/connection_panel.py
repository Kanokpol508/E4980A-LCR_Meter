# กล่องเลือกพอร์ต USB/LAN และปุ่ม Connect/Disconnect

from PyQt6.QtWidgets import (QWidget, QGroupBox, QHBoxLayout, QVBoxLayout,
                             QComboBox, QPushButton, QLabel, QSizePolicy)
from utils.helpers import NoScrollComboBox

class ConnectionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        group_visa = QGroupBox("VISA Resource")
        v_visa = QVBoxLayout()

        # --- แถวบน: Dropdown เลือกพอร์ต + ปุ่ม Refresh ---
        h_visa = QHBoxLayout()

        self.combo_visa = NoScrollComboBox()
        self.combo_visa.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_refresh = QPushButton("REFRESH")

        h_visa.addWidget(self.combo_visa, stretch=1)
        h_visa.addWidget(self.btn_refresh)
        v_visa.addLayout(h_visa)

        # --- แถวล่าง: ปุ่ม Connect / Disconnect + สถานะการเชื่อมต่อ ---
        h_conn = QHBoxLayout()

        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.setObjectName("btnConnect")
        self.btn_connect.setMinimumHeight(32)
        self.btn_connect.setStyleSheet(
            "QPushButton#btnConnect { background-color: #A8E6C1; color: #14532D; "
            "border-radius: 6px; font-weight: bold; border: 1px solid #7FD9A0; }"
            "QPushButton#btnConnect:hover { background-color: #7FD9A0; }"
            "QPushButton#btnConnect:disabled { background-color: #E5E7EB; border: 1px solid #D1D5DB; color: #A3ADC2; }"
        )

        self.btn_disconnect = QPushButton("DISCONNECT")
        self.btn_disconnect.setObjectName("btnDisconnect")
        self.btn_disconnect.setMinimumHeight(32)
        self.btn_disconnect.setEnabled(False)  # ปิดไว้ก่อน จนกว่าจะเชื่อมต่อสำเร็จ
        self.btn_disconnect.setStyleSheet(
            "QPushButton#btnDisconnect { background-color: #FDAFAB; color: #7A1F1B; "
            "border-radius: 6px; font-weight: bold; border: 1px solid #F58E89; }"
            "QPushButton#btnDisconnect:hover { background-color: #F58E89; }"
            "QPushButton#btnDisconnect:disabled { background-color: #E5E7EB; border: 1px solid #D1D5DB; color: #A3ADC2; }"
        )

        self.lbl_status = QLabel("\u26aa Not Connected")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #8B95A8;")

        h_conn.addWidget(self.btn_connect)
        h_conn.addWidget(self.btn_disconnect)
        h_conn.addWidget(self.lbl_status, stretch=1)
        v_visa.addLayout(h_conn)

        group_visa.setLayout(v_visa)
        layout.addWidget(group_visa)

    def set_connected_ui(self, connected: bool, resource_text: str = ""):
        """ปรับหน้าตาปุ่ม/สถานะให้ตรงกับสถานะการเชื่อมต่อปัจจุบัน"""
        if connected:
            self.lbl_status.setText("\U0001F7E2 Connected")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #3E8E5E;")
        else:
            self.lbl_status.setText("\u26aa Not Connected")
            self.lbl_status.setStyleSheet("font-weight: bold; color: #8B95A8;")

        self.btn_connect.setEnabled(not connected)
        self.btn_disconnect.setEnabled(connected)
        self.combo_visa.setEnabled(not connected)
        self.btn_refresh.setEnabled(not connected)