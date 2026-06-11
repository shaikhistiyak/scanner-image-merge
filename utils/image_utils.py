import cv2
import numpy as np
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt


def numpy_to_pixmap(image: np.ndarray) -> QPixmap:
    """Convert OpenCV numpy image to QPixmap."""
    if image is None:
        return QPixmap()

    if image.ndim == 2:
        rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    elif image.shape[2] == 4:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
    else:
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    qt_image = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
    return QPixmap.fromImage(qt_image)


def pixmap_thumbnail(file_path: str, size: tuple) -> QPixmap:
    """Load image and return a thumbnail QPixmap."""
    pixmap = QPixmap(file_path)
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        size[0],
        size[1],
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )


def is_valid_image(file_path: str) -> bool:
    """Check if file is a readable image."""
    img = cv2.imread(str(file_path))
    return img is not None
