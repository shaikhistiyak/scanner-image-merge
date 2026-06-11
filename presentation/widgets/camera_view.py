from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt


class CameraView(QLabel):
    def __init__(self):
        super().__init__()

        self.setAlignment(Qt.AlignCenter)
        self.setText("Camera Preview")

        self.setStyleSheet("""
            border: 1px solid #999;
            background: #222;
            color: white;
        """)
