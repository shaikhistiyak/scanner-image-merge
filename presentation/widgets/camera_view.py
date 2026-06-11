from PyQt6.QtWidgets import QLabel
from PyQt6.QtCore import Qt


class CameraView(QLabel):
    def __init__(self):
        super().__init__()

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Camera Preview")

        self.setStyleSheet("""
            border: 1px solid #999;
            background: #222;
            color: white;
        """)