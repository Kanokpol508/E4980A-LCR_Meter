# กล่องปุ่ม START, STOP, โหมด Single/Sweep

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGridLayout, QHBoxLayout, QPushButton, QButtonGroup, QLabel, QSizePolicy
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

        h_run_mode = QHBoxLayout()
        h_run_mode.setSpacing(0)
        self.btn_mode_single = QPushButton("วัดจุดเดียว")
        self.btn_mode_sweep = QPushButton("สแกนความถี่")
        self.btn_mode_single.setCheckable(True)
        self.btn_mode_sweep.setCheckable(True)
        self.btn_mode_sweep.setChecked(True)
        
        self.run_mode_group = QButtonGroup()
        self.run_mode_group.addButton(self.btn_mode_single)
        self.run_mode_group.addButton(self.btn_mode_sweep)
        
        h_run_mode.addWidget(self.btn_mode_single)
        h_run_mode.addWidget(self.btn_mode_sweep)
        grid_run.addLayout(h_run_mode, 0, 0)

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

        self.lbl_warn_visa = QLabel("⚠️ กรุณาเลือกเครื่องมือวัด (VISA)")
        self.lbl_warn_dc_start = QLabel("⚠️ ตั้งค่า DC Bias ไม่ถูกต้อง")
        self.lbl_warn_dev_start = QLabel("⚠️ ต้องกรอก Primary Ref ก่อน")
        
        self.lbl_warn_visa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_dc_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_warn_dev_start.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_warn_visa.setVisible(False)
        self.lbl_warn_dc_start.setVisible(False)
        self.lbl_warn_dev_start.setVisible(False)
        
        v_warn = QVBoxLayout()
        v_warn.addWidget(self.lbl_warn_visa)
        v_warn.addWidget(self.lbl_warn_dc_start)
        v_warn.addWidget(self.lbl_warn_dev_start)
        grid_run.addLayout(v_warn, 2, 0)

        layout.addLayout(grid_run)