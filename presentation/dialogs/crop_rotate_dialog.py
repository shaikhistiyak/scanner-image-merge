"""
CropRotateDialog — interactive crop + rotate tool for scanned images.

Features:
  • Drag handles to resize crop rectangle
  • Rotation slider (-45° to +45°)
  • Fine-tune with spin box
  • Live preview of final result
  • Keyboard shortcuts: R=reset, Enter=apply, Esc=cancel
"""

import cv2
import numpy as np

from PyQt5.QtCore import Qt, QRect, QPoint, QSize, pyqtSignal, QRectF
from PyQt5.QtGui import (
    QPainter, QPixmap, QImage, QColor, QPen, QBrush,
    QCursor, QFont, QPainterPath,
)
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSlider, QDoubleSpinBox, QWidget,
    QSizePolicy, QFrame, QShortcut,
)
from PyQt5.QtGui import QKeySequence


# ──────────────────────────────────────────────────────────────────────
# Handle IDs
# ──────────────────────────────────────────────────────────────────────
HANDLE_NONE        = 0
HANDLE_TL          = 1
HANDLE_T           = 2
HANDLE_TR          = 3
HANDLE_R           = 4
HANDLE_BR          = 5
HANDLE_B           = 6
HANDLE_BL          = 7
HANDLE_L           = 8
HANDLE_MOVE        = 9

HANDLE_SIZE = 10   # px radius of corner/edge handles


class CropCanvas(QWidget):
    """
    Widget that shows the image and lets the user drag a crop rectangle.
    """

    crop_changed = pyqtSignal(QRect)

    def __init__(self, pixmap: QPixmap, parent=None):
        super().__init__(parent)
        self._orig_pixmap = pixmap
        self._display_pixmap = pixmap
        self._rotation = 0.0

        self._img_rect  = QRect()   # where image is drawn inside widget
        self._crop_rect = QRect()   # in image-local coordinates

        self._active_handle = HANDLE_NONE
        self._drag_start    = QPoint()
        self._drag_orig_rect = QRect()

        self.setMinimumSize(400, 400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)

    # ── public API ──────────────────────────────────────────────────

    def set_rotation(self, degrees: float):
        self._rotation = degrees
        self._rebuild_display_pixmap()
        self.update()

    def get_crop_rect_image_coords(self) -> QRect:
        """Return crop rect in original (pre-rotation) image coordinates."""
        if self._img_rect.isEmpty():
            return QRect()
        sx = self._orig_pixmap.width()  / self._img_rect.width()
        sy = self._orig_pixmap.height() / self._img_rect.height()
        r  = self._crop_rect.translated(-self._img_rect.topLeft())
        return QRect(
            int(r.x() * sx), int(r.y() * sy),
            int(r.width() * sx), int(r.height() * sy),
        )

    def reset_crop(self):
        self._crop_rect = QRect(self._img_rect)
        self.update()
        self.crop_changed.emit(self._crop_rect)

    # ── internal ────────────────────────────────────────────────────

    def _rebuild_display_pixmap(self):
        """Rotate the pixmap and reset the display."""
        if self._rotation == 0.0:
            self._display_pixmap = self._orig_pixmap
            return
        img = self._qpixmap_to_cv(self._orig_pixmap)
        h, w = img.shape[:2]
        cx, cy = w / 2, h / 2
        M  = cv2.getRotationMatrix2D((cx, cy), -self._rotation, 1.0)
        cos, sin = abs(M[0, 0]), abs(M[0, 1])
        nw = int(h * sin + w * cos)
        nh = int(h * cos + w * sin)
        M[0, 2] += (nw - w) / 2
        M[1, 2] += (nh - h) / 2
        rotated = cv2.warpAffine(img, M, (nw, nh),
                                  flags=cv2.INTER_LINEAR,
                                  borderValue=(220, 220, 220))
        self._display_pixmap = self._cv_to_qpixmap(rotated)

    def _recalc_img_rect(self):
        """Fit display pixmap into widget keeping aspect ratio."""
        pw, ph = self._display_pixmap.width(), self._display_pixmap.height()
        ww, wh = self.width(), self.height()
        scale  = min(ww / pw, wh / ph) * 0.95
        nw, nh = int(pw * scale), int(ph * scale)
        x = (ww - nw) // 2
        y = (wh - nh) // 2
        new_rect = QRect(x, y, nw, nh)
        if new_rect != self._img_rect:
            self._img_rect = new_rect
            self._crop_rect = QRect(self._img_rect)
        return self._img_rect

    # ── painting ────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor(40, 40, 40))

        if self._display_pixmap.isNull():
            return

        ir = self._recalc_img_rect()

        # Draw image
        painter.drawPixmap(ir, self._display_pixmap)

        cr = self._crop_rect
        if cr.isEmpty():
            return

        # Dim outside crop
        dim = QColor(0, 0, 0, 140)
        painter.fillRect(QRect(ir.left(), ir.top(), ir.width(), cr.top() - ir.top()), dim)
        painter.fillRect(QRect(ir.left(), cr.bottom(), ir.width(), ir.bottom() - cr.bottom()), dim)
        painter.fillRect(QRect(ir.left(), cr.top(), cr.left() - ir.left(), cr.height()), dim)
        painter.fillRect(QRect(cr.right(), cr.top(), ir.right() - cr.right(), cr.height()), dim)

        # Crop border
        pen = QPen(QColor(255, 255, 255), 2, Qt.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(cr)

        # Rule-of-thirds grid
        pen_grid = QPen(QColor(255, 255, 255, 60), 1, Qt.DashLine)
        painter.setPen(pen_grid)
        for i in (1, 2):
            x = cr.left() + cr.width() * i // 3
            painter.drawLine(x, cr.top(), x, cr.bottom())
            y = cr.top() + cr.height() * i // 3
            painter.drawLine(cr.left(), y, cr.right(), y)

        # Handles
        painter.setPen(QPen(QColor(255, 200, 0), 2))
        painter.setBrush(QBrush(QColor(255, 200, 0, 200)))
        for hx, hy in self._handle_positions():
            painter.drawEllipse(QPoint(hx, hy), HANDLE_SIZE, HANDLE_SIZE)

        painter.end()

    def _handle_positions(self):
        cr = self._crop_rect
        mx, my = cr.center().x(), cr.center().y()
        return [
            (cr.left(),   cr.top()),     # TL
            (mx,          cr.top()),     # T
            (cr.right(),  cr.top()),     # TR
            (cr.right(),  my),           # R
            (cr.right(),  cr.bottom()),  # BR
            (mx,          cr.bottom()),  # B
            (cr.left(),   cr.bottom()),  # BL
            (cr.left(),   my),           # L
        ]

    def _handle_at(self, pos: QPoint) -> int:
        for idx, (hx, hy) in enumerate(self._handle_positions()):
            if abs(pos.x() - hx) <= HANDLE_SIZE + 2 and abs(pos.y() - hy) <= HANDLE_SIZE + 2:
                return idx + 1   # 1-based = TL..L
        if self._crop_rect.contains(pos):
            return HANDLE_MOVE
        return HANDLE_NONE

    # ── mouse ───────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._active_handle = self._handle_at(event.pos())
            self._drag_start    = event.pos()
            self._drag_orig_rect = QRect(self._crop_rect)

    def mouseMoveEvent(self, event):
        h = self._handle_at(event.pos())
        cursors = {
            HANDLE_TL: Qt.SizeFDiagCursor, HANDLE_BR: Qt.SizeFDiagCursor,
            HANDLE_TR: Qt.SizeBDiagCursor, HANDLE_BL: Qt.SizeBDiagCursor,
            HANDLE_T:  Qt.SizeVerCursor,   HANDLE_B:  Qt.SizeVerCursor,
            HANDLE_L:  Qt.SizeHorCursor,   HANDLE_R:  Qt.SizeHorCursor,
            HANDLE_MOVE: Qt.SizeAllCursor,
        }
        self.setCursor(QCursor(cursors.get(h, Qt.CrossCursor)))

        if self._active_handle == HANDLE_NONE:
            return

        dx = event.pos().x() - self._drag_start.x()
        dy = event.pos().y() - self._drag_start.y()
        r  = QRect(self._drag_orig_rect)
        ir = self._img_rect
        MIN = 30

        if self._active_handle == HANDLE_MOVE:
            r.translate(dx, dy)
            r = self._clamp_rect(r, ir)

        elif self._active_handle == HANDLE_TL:
            r.setLeft(min(r.left() + dx, r.right() - MIN))
            r.setTop( min(r.top()  + dy, r.bottom() - MIN))
        elif self._active_handle == HANDLE_T:
            r.setTop(min(r.top() + dy, r.bottom() - MIN))
        elif self._active_handle == HANDLE_TR:
            r.setRight(max(r.right() + dx, r.left() + MIN))
            r.setTop(  min(r.top()   + dy, r.bottom() - MIN))
        elif self._active_handle == HANDLE_R:
            r.setRight(max(r.right() + dx, r.left() + MIN))
        elif self._active_handle == HANDLE_BR:
            r.setRight( max(r.right()  + dx, r.left() + MIN))
            r.setBottom(max(r.bottom() + dy, r.top()  + MIN))
        elif self._active_handle == HANDLE_B:
            r.setBottom(max(r.bottom() + dy, r.top() + MIN))
        elif self._active_handle == HANDLE_BL:
            r.setLeft(  min(r.left()   + dx, r.right()  - MIN))
            r.setBottom(max(r.bottom() + dy, r.top()    + MIN))
        elif self._active_handle == HANDLE_L:
            r.setLeft(min(r.left() + dx, r.right() - MIN))

        # Clamp to image bounds
        r.setLeft(  max(r.left(),   ir.left()))
        r.setTop(   max(r.top(),    ir.top()))
        r.setRight( min(r.right(),  ir.right()))
        r.setBottom(min(r.bottom(), ir.bottom()))

        self._crop_rect = r
        self.update()
        self.crop_changed.emit(r)

    def mouseReleaseEvent(self, event):
        self._active_handle = HANDLE_NONE

    def resizeEvent(self, event):
        self._recalc_img_rect()
        self._crop_rect = QRect(self._img_rect)
        self.update()

    def _clamp_rect(self, r: QRect, bounds: QRect) -> QRect:
        if r.left() < bounds.left():
            r.translate(bounds.left() - r.left(), 0)
        if r.top() < bounds.top():
            r.translate(0, bounds.top() - r.top())
        if r.right() > bounds.right():
            r.translate(bounds.right() - r.right(), 0)
        if r.bottom() > bounds.bottom():
            r.translate(0, bounds.bottom() - r.bottom())
        return r

    # ── helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _qpixmap_to_cv(pixmap: QPixmap) -> np.ndarray:
        img  = pixmap.toImage().convertToFormat(QImage.Format_RGB888)
        ptr  = img.bits()
        ptr.setsize(img.byteCount())
        arr  = np.frombuffer(ptr, dtype=np.uint8).reshape(img.height(), img.width(), 3)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

    @staticmethod
    def _cv_to_qpixmap(img: np.ndarray) -> QPixmap:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qt)


# ──────────────────────────────────────────────────────────────────────
# Main Dialog
# ──────────────────────────────────────────────────────────────────────

class CropRotateDialog(QDialog):
    """
    Dialog with:
      • Interactive crop canvas (drag handles)
      • Rotation slider + spin box
      • Reset / Apply / Cancel buttons
    """

    def __init__(self, image_path: str, parent=None):
        super().__init__(parent)
        self.image_path  = image_path
        self.result_image: np.ndarray = None

        self._orig_cv = cv2.imread(image_path)
        if self._orig_cv is None:
            raise ValueError(f"Cannot load image: {image_path}")

        self.setWindowTitle("Crop & Rotate")
        self.setModal(True)
        self.resize(1000, 780)
        self._apply_style()
        self._setup_ui()
        self._setup_shortcuts()

    # ── style ───────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog   { background:#1e1e1e; color:#e0e0e0; }
            QWidget   { background:#1e1e1e; color:#e0e0e0; font-size:13px; }
            QFrame    { background:#252525; border-radius:6px; }
            QLabel    { background:transparent; }
            QPushButton {
                background:#3a3a3a; color:#e0e0e0;
                border:1px solid #555; border-radius:5px;
                padding:7px 18px; font-size:13px;
            }
            QPushButton:hover  { background:#4a4a4a; }
            QPushButton#apply  { background:#16a34a; color:white; border-color:#15803d; font-weight:bold; }
            QPushButton#apply:hover  { background:#15803d; }
            QPushButton#cancel { background:#dc2626; color:white; border-color:#b91c1c; }
            QPushButton#cancel:hover { background:#b91c1c; }
            QPushButton#reset  { background:#d97706; color:white; border-color:#b45309; }
            QPushButton#reset:hover  { background:#b45309; }
            QSlider::groove:horizontal {
                background:#444; height:6px; border-radius:3px;
            }
            QSlider::handle:horizontal {
                background:#2563eb; width:18px; height:18px;
                margin:-6px 0; border-radius:9px;
            }
            QSlider::sub-page:horizontal { background:#2563eb; border-radius:3px; }
            QDoubleSpinBox {
                background:#3a3a3a; border:1px solid #555;
                border-radius:4px; padding:4px 8px; color:#e0e0e0;
            }
        """)

    # ── UI ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # ── Canvas ──
        pixmap = self._cv_to_qpixmap(self._orig_cv)
        self.canvas = CropCanvas(pixmap)
        self.canvas.crop_changed.connect(self._on_crop_changed)
        root.addWidget(self.canvas, stretch=1)

        # ── Controls bar ──
        ctrl = QFrame()
        ctrl.setFixedHeight(100)
        ctrl_layout = QVBoxLayout(ctrl)
        ctrl_layout.setSpacing(6)
        ctrl_layout.setContentsMargins(12, 8, 12, 8)

        # Row 1: Rotation label + slider + spinbox
        row1 = QHBoxLayout()

        lbl = QLabel("↻  Rotation:")
        lbl.setFixedWidth(90)
        row1.addWidget(lbl)

        self.rot_slider = QSlider(Qt.Horizontal)
        self.rot_slider.setRange(-450, 450)   # ×10 for 0.1° steps
        self.rot_slider.setValue(0)
        self.rot_slider.setFixedHeight(30)
        row1.addWidget(self.rot_slider, stretch=1)

        self.rot_spin = QDoubleSpinBox()
        self.rot_spin.setRange(-45.0, 45.0)
        self.rot_spin.setSingleStep(0.1)
        self.rot_spin.setDecimals(1)
        self.rot_spin.setSuffix("°")
        self.rot_spin.setFixedWidth(90)
        row1.addWidget(self.rot_spin)

        # Quick rotation buttons
        for label, delta in [("-90°", -90), ("-1°", -1), ("+1°", +1), ("+90°", +90)]:
            btn = QPushButton(label)
            btn.setFixedWidth(52)
            btn.clicked.connect(lambda _, d=delta: self._adjust_rotation(d))
            row1.addWidget(btn)

        ctrl_layout.addLayout(row1)

        # Row 2: info label + action buttons
        row2 = QHBoxLayout()

        self.info_label = QLabel("Drag handles to crop  •  Use slider or buttons to rotate")
        self.info_label.setStyleSheet("color:#888; font-size:11px;")
        row2.addWidget(self.info_label, stretch=1)

        reset_btn = QPushButton("↺  Reset")
        reset_btn.setObjectName("reset")
        reset_btn.clicked.connect(self._reset)
        row2.addWidget(reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        row2.addWidget(cancel_btn)

        apply_btn = QPushButton("✔  Apply Crop & Rotate")
        apply_btn.setObjectName("apply")
        apply_btn.clicked.connect(self._apply)
        row2.addWidget(apply_btn)

        ctrl_layout.addLayout(row2)
        root.addWidget(ctrl)

        # Wire rotation controls
        self.rot_slider.valueChanged.connect(self._on_slider_changed)
        self.rot_spin.valueChanged.connect(self._on_spin_changed)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Return), self, self._apply)
        QShortcut(QKeySequence(Qt.Key_Enter),  self, self._apply)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.reject)
        QShortcut(QKeySequence("R"),           self, self._reset)

    # ── slots ───────────────────────────────────────────────────────

    def _on_slider_changed(self, value: int):
        degrees = value / 10.0
        self.rot_spin.blockSignals(True)
        self.rot_spin.setValue(degrees)
        self.rot_spin.blockSignals(False)
        self.canvas.set_rotation(degrees)

    def _on_spin_changed(self, value: float):
        self.rot_slider.blockSignals(True)
        self.rot_slider.setValue(int(value * 10))
        self.rot_slider.blockSignals(False)
        self.canvas.set_rotation(value)

    def _adjust_rotation(self, delta: float):
        new_val = max(-45.0, min(45.0, self.rot_spin.value() + delta))
        self.rot_spin.setValue(new_val)

    def _on_crop_changed(self, rect: QRect):
        if rect.isEmpty():
            return
        self.info_label.setText(
            f"Crop: {rect.width()}×{rect.height()} px  |  "
            f"Rotation: {self.rot_spin.value():.1f}°  |  "
            "Enter = Apply"
        )

    def _reset(self):
        self.rot_slider.setValue(0)
        self.rot_spin.setValue(0.0)
        self.canvas.set_rotation(0.0)
        self.canvas.reset_crop()
        self.info_label.setText("Drag handles to crop  •  Use slider or buttons to rotate")

    def _apply(self):
        """Rotate the original CV image then crop."""
        angle = self.rot_spin.value()
        img   = self._orig_cv.copy()

        # Rotate
        if abs(angle) > 0.05:
            h, w  = img.shape[:2]
            cx, cy = w / 2, h / 2
            M    = cv2.getRotationMatrix2D((cx, cy), -angle, 1.0)
            cos, sin = abs(M[0, 0]), abs(M[0, 1])
            nw   = int(h * sin + w * cos)
            nh   = int(h * cos + w * sin)
            M[0, 2] += (nw - w) / 2
            M[1, 2] += (nh - h) / 2
            img  = cv2.warpAffine(img, M, (nw, nh),
                                   flags=cv2.INTER_LINEAR,
                                   borderValue=(255, 255, 255))

        # Crop
        crop_rect = self.canvas.get_crop_rect_image_coords()
        if not crop_rect.isEmpty():
            ih, iw = img.shape[:2]
            x = max(0, crop_rect.x())
            y = max(0, crop_rect.y())
            w = min(crop_rect.width(),  iw - x)
            h = min(crop_rect.height(), ih - y)
            if w > 10 and h > 10:
                img = img[y:y+h, x:x+w]

        self.result_image = img
        self.accept()

    # ── helper ──────────────────────────────────────────────────────

    @staticmethod
    def _cv_to_qpixmap(img: np.ndarray) -> QPixmap:
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qt)
