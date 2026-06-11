from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem


class ImageViewer(QGraphicsView):

    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        self.zoom_factor = 1.0

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.setStyleSheet("background: #2b2b2b; border: none;")

    def load_image(self, image_path: str) -> bool:
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return False
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self.pixmap_item)
        self.zoom_factor = 1.0
        return True

    def load_pixmap(self, pixmap: QPixmap) -> bool:
        if pixmap.isNull():
            return False
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self.pixmap_item)
        self.zoom_factor = 1.0
        return True

    def zoom_in(self):
        if self.zoom_factor < 10:
            self.scale(1.25, 1.25)
            self.zoom_factor *= 1.25

    def zoom_out(self):
        if self.zoom_factor > 0.1:
            self.scale(0.8, 0.8)
            self.zoom_factor *= 0.8

    def rotate_left(self):
        self.rotate(-90)

    def rotate_right(self):
        self.rotate(90)

    def fit_image(self):
        self.resetTransform()
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoom_factor = 1.0

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_in()
        else:
            self.zoom_out()
