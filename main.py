import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont
from presentation.main_window import MainWindow
from utils.config import APP_NAME


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont("Segoe UI", 10))

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
