# กล่องปุ่ม Verify & Apply, Clear Data, START, STOP

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QPushButton, QLabel, QSizePolicy
from PyQt6.QtCore import Qt

class ControlPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(5)

        grid_run = QGridLayout()
        grid_run.setColumnStretch(0, 1)
        grid_run.setColumnStretch(1, 1)
        grid_run.setVerticalSpacing(5)

        # แถวบน: Verify & Apply (เหนือ Start) / Clear Data (เหนือ Stop)
        self.btn_verify = QPushButton("Verify & Apply")
        self.btn_verify.setObjectName("btnVerify")
        self.btn_verify.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_verify.setMinimumHeight(30)
        grid_run.addWidget(self.btn_verify, 0, 0)

        self.btn_clear = QPushButton("Clear Data")
        self.btn_clear.setObjectName("btnClearData")
        self.btn_clear.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_clear.setMinimumHeight(30)
        grid_run.addWidget(self.btn_clear, 0, 1)

        # แถวล่าง: ปุ่ม START และ STOP
        self.btn_start = QPushButton("START")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.btn_start.setMinimumHeight(60)

        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.btn_stop.setMinimumHeight(60)
        self.btn_stop.setEnabled(False)

        grid_run.addWidget(self.btn_start, 1, 0)
        grid_run.addWidget(self.btn_stop, 1, 1)

        # Label แจ้งเตือนข้อผิดพลาด
        self.lbl_warn_visa = QLabel("⚠️ กรุณาเลือกเครื่องมือวัด (VISA)")
        self.lbl_warn_dev_start = QLabel("⚠️ ต้องกรอก Primary Ref หรือ Secondary Ref อย่างน้อย 1 ค่า")
        self.lbl_warn_freqlist_start = QLabel("⚠️ กรุณากรอกรายการความถี่ (Frequency List) ก่อนเริ่มวัด")

        self.lbl_warn_visa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_dev_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_dev_start.setWordWrap(True)
        self.lbl_warn_freqlist_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_freqlist_start.setWordWrap(True)

        self.lbl_warn_visa.setVisible(False)
        self.lbl_warn_dev_start.setVisible(False)
        self.lbl_warn_freqlist_start.setVisible(False)

        self.lbl_warn_visa.setStyleSheet("color: #ff4444; font-weight: bold;")
        self.lbl_warn_dev_start.setStyleSheet("color: #ff4444; font-weight: bold;")
        self.lbl_warn_freqlist_start.setStyleSheet("color: #ff4444; font-weight: bold;")

        layout.addLayout(grid_run)
        layout.addWidget(self.lbl_warn_visa)
        layout.addWidget(self.lbl_warn_dev_start)
        layout.addWidget(self.lbl_warn_freqlist_start)