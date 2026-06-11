from PyQt5.QtCore import QTimer, Qt, QSize
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QComboBox, QListWidget,
    QListWidgetItem, QFrame, QFileDialog,
    QAbstractItemView, QMessageBox, QProgressBar,
    QSizePolicy, QSplitter,
)
from PyQt5.QtWidgets import QAction
from PyQt5.QtGui import QImage, QPixmap, QIcon

from pathlib import Path

from presentation.widgets.image_viewer import ImageViewer
from presentation.workers.scan_worker import ScanWorker, MergeWorker, BatchImageWorker

from services.device_service import DeviceService
from services.camera_service import CameraService
from services.image_service import ImageService
from services.workspace_service import WorkspaceService
from services.merge_service import MergeService
from services.export_service import ExportService

from utils.config import (
    APP_NAME, APP_VERSION,
    RESOLUTIONS, DEFAULT_RESOLUTION,
    COLOR_MODES, DEFAULT_COLOR_MODE,
    SUPPORTED_IMAGE_FORMATS, THUMBNAIL_SIZE,
)
from utils.image_utils import numpy_to_pixmap, pixmap_thumbnail
from utils.logger import get_logger

logger = get_logger(__name__)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.device_service = DeviceService()
        self.camera_service = CameraService()
        self.image_service = ImageService()
        self.workspace_service = WorkspaceService()
        self.merge_service = MergeService()
        self.export_service = ExportService()

        self.current_image_path = None
        self._scan_worker = None
        self._merge_worker = None
        self._batch_worker = None

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1500, 900)
        self._apply_style()
        self._setup_ui()
        self._setup_toolbar()
        self._connect_signals()

        self.refresh_devices()

        self.camera_timer = QTimer()
        self.camera_timer.timeout.connect(self._update_camera_frame)

        self.statusBar().showMessage("Ready")

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #1e1e1e; }
            QWidget { background: #1e1e1e; color: #e0e0e0; font-size: 13px; }
            QFrame { background: #252525; border-radius: 6px; }
            QPushButton {
                background: #3a3a3a; color: #e0e0e0;
                border: 1px solid #555; border-radius: 5px;
                padding: 6px 10px; font-size: 13px;
            }
            QPushButton:hover { background: #4a4a4a; border-color: #888; }
            QPushButton:pressed { background: #2a2a2a; }
            QPushButton#primary {
                background: #2563eb; color: white; border-color: #1d4ed8;
                font-weight: bold;
            }
            QPushButton#primary:hover { background: #1d4ed8; }
            QPushButton#success {
                background: #16a34a; color: white; border-color: #15803d;
                font-weight: bold;
            }
            QPushButton#success:hover { background: #15803d; }
            QPushButton#warning {
                background: #d97706; color: white; border-color: #b45309;
                font-weight: bold;
            }
            QPushButton#warning:hover { background: #b45309; }
            QComboBox {
                background: #3a3a3a; border: 1px solid #555;
                border-radius: 4px; padding: 4px 8px;
            }
            QComboBox::drop-down { border: none; }
            QListWidget {
                background: #1a1a1a; border: 1px solid #444;
                border-radius: 4px;
            }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #333; }
            QListWidget::item:selected { background: #2563eb; }
            QListWidget::item:hover { background: #333; }
            QLabel#section_header {
                font-weight: bold; font-size: 11px;
                color: #888; padding: 4px 0;
                text-transform: uppercase; letter-spacing: 1px;
            }
            QProgressBar {
                background: #333; border: none; border-radius: 3px; height: 6px;
            }
            QProgressBar::chunk { background: #2563eb; border-radius: 3px; }
            QSplitter::handle { background: #333; width: 2px; }
        """)

    # ------------------------------------------------------------------
    # UI Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(8, 8, 8, 8)

        main_layout.addWidget(self._build_left_panel())
        main_layout.addWidget(self._build_center_panel(), stretch=1)
        main_layout.addWidget(self._build_right_panel())

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("section_header")
        return lbl

    def _build_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(220)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        # Device
        layout.addWidget(self._section_label("Device"))
        self.device_combo = QComboBox()
        layout.addWidget(self.device_combo)
        self.refresh_btn = QPushButton("Refresh Devices")
        layout.addWidget(self.refresh_btn)

        layout.addSpacing(10)

        # Scan Settings
        layout.addWidget(self._section_label("Resolution"))
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([f"{r} DPI" for r in RESOLUTIONS])
        self.resolution_combo.setCurrentText(f"{DEFAULT_RESOLUTION} DPI")
        layout.addWidget(self.resolution_combo)

        layout.addWidget(self._section_label("Color Mode"))
        self.color_combo = QComboBox()
        self.color_combo.addItems(COLOR_MODES)
        self.color_combo.setCurrentText(DEFAULT_COLOR_MODE)
        layout.addWidget(self.color_combo)

        layout.addSpacing(10)

        # Scan / Camera buttons
        layout.addWidget(self._section_label("Capture"))
        self.scan_btn = QPushButton("Scan Document")
        self.scan_btn.setObjectName("primary")
        layout.addWidget(self.scan_btn)

        self.capture_btn = QPushButton("Capture Photo")
        layout.addWidget(self.capture_btn)

        self.start_camera_btn = QPushButton("Start Camera")
        self.stop_camera_btn = QPushButton("Stop Camera")
        layout.addWidget(self.start_camera_btn)
        layout.addWidget(self.stop_camera_btn)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)   # indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addStretch()
        return panel

    def _build_center_panel(self) -> QFrame:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.image_viewer = ImageViewer()
        layout.addWidget(self.image_viewer)
        return panel

    def _build_right_panel(self) -> QFrame:
        panel = QFrame()
        panel.setFixedWidth(260)
        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        layout.addWidget(self._section_label("Workspace Images"))

        self.workspace_list = QListWidget()
        self.workspace_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.workspace_list.setIconSize(QSize(*THUMBNAIL_SIZE))
        self.workspace_list.setSpacing(2)
        layout.addWidget(self.workspace_list)

        # Workspace actions
        ws_row = QHBoxLayout()
        self.remove_btn = QPushButton("Remove")
        self.clear_btn = QPushButton("Clear All")
        ws_row.addWidget(self.remove_btn)
        ws_row.addWidget(self.clear_btn)
        layout.addLayout(ws_row)

        layout.addSpacing(8)

        # ---- Merge Options ----
        layout.addWidget(self._section_label("Merge"))

        self.stitch_btn = QPushButton("Smart Stitch")
        self.stitch_btn.setObjectName("success")
        self.stitch_btn.setToolTip(
            "Seamlessly stitch selected scans into one image.\n"
            "Works for any document type. Requires overlapping sections."
        )
        layout.addWidget(self.stitch_btn)

        self.vertical_btn = QPushButton("Vertical Stack")
        self.horizontal_btn = QPushButton("Horizontal Stack")
        self.grid_btn = QPushButton("Grid Merge")
        layout.addWidget(self.vertical_btn)
        layout.addWidget(self.horizontal_btn)
        layout.addWidget(self.grid_btn)

        layout.addSpacing(8)

        # ---- Post-processing ----
        layout.addWidget(self._section_label("Post-Process"))

        self.smart_crop_btn = QPushButton("✂  Smart Crop")
        self.smart_crop_btn.setObjectName("warning")
        self.smart_crop_btn.setToolTip(
            "Remove scanner border shadows and black dead zones.\n"
            "Runs automatically on each selected image.\n"
            "Use this BEFORE stitching for best results."
        )
        layout.addWidget(self.smart_crop_btn)

        self.crop_btn = QPushButton("⬡  Auto Crop && Straighten")
        self.crop_btn.setToolTip(
            "Smart crop + perspective correction.\n"
            "Detects document boundary and warps it flat.\n"
            "Best for photos of documents on a desk."
        )
        layout.addWidget(self.crop_btn)

        layout.addSpacing(8)

        # ---- Export ----
        layout.addWidget(self._section_label("Export"))
        self.export_image_btn = QPushButton("Export as Image")
        self.export_pdf_btn = QPushButton("Export as PDF")
        layout.addWidget(self.export_image_btn)
        layout.addWidget(self.export_pdf_btn)

        layout.addStretch()
        return panel

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _setup_toolbar(self):
        toolbar = self.addToolBar("Tools")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(18, 18))

        actions = [
            ("Import", self._import_image),
            ("Zoom In", self.image_viewer.zoom_in),
            ("Zoom Out", self.image_viewer.zoom_out),
            ("Rotate L", self.image_viewer.rotate_left),
            ("Rotate R", self.image_viewer.rotate_right),
            ("Fit Screen", self.image_viewer.fit_image),
        ]

        for label, slot in actions:
            act = QAction(label, self)
            act.triggered.connect(slot)
            toolbar.addAction(act)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self):
        self.refresh_btn.clicked.connect(self.refresh_devices)
        self.scan_btn.clicked.connect(self._scan_document)
        self.capture_btn.clicked.connect(self._capture_image)
        self.start_camera_btn.clicked.connect(self._start_camera)
        self.stop_camera_btn.clicked.connect(self._stop_camera)

        self.workspace_list.itemClicked.connect(self._load_workspace_image)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn.clicked.connect(self._clear_workspace)

        self.stitch_btn.clicked.connect(self._merge_stitch)
        self.vertical_btn.clicked.connect(self._merge_vertical)
        self.horizontal_btn.clicked.connect(self._merge_horizontal)
        self.grid_btn.clicked.connect(self._merge_grid)

        self.smart_crop_btn.clicked.connect(self._smart_crop_selected)
        self.crop_btn.clicked.connect(self._auto_crop_selected)

        self.export_image_btn.clicked.connect(self._export_image)
        self.export_pdf_btn.clicked.connect(self._export_pdf)

    # ------------------------------------------------------------------
    # Device management
    # ------------------------------------------------------------------

    def refresh_devices(self):
        self.device_combo.clear()
        devices = self.device_service.get_devices()
        if not devices:
            self.device_combo.addItem("No Device Found")
            self.statusBar().showMessage("No devices detected")
            return
        self.device_combo.addItems(devices)
        self.statusBar().showMessage(f"{len(devices)} device(s) detected")

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def _get_selected_dpi(self) -> int:
        text = self.resolution_combo.currentText()
        return int(text.replace(" DPI", ""))

    def _get_selected_color_mode(self) -> str:
        return self.color_combo.currentText()

    def _scan_document(self):
        selected = self.device_combo.currentText()
        if not selected or selected in ("No Device Found",) or selected.startswith("Camera"):
            self._show_error("Please select a scanner from the device list.")
            return

        self._set_busy(True, "Scanning...")

        self._scan_worker = ScanWorker(
            scanner_service=self.device_service.scanner_service,
            scanner_name=selected,
            dpi=self._get_selected_dpi(),
            color_mode=self._get_selected_color_mode(),
        )
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_finished(self, file_path: str):
        self._set_busy(False)
        self._add_to_workspace(file_path)
        self.statusBar().showMessage(f"Scan complete: {Path(file_path).name}")

    def _on_scan_error(self, message: str):
        self._set_busy(False)
        self._show_error(f"Scan failed: {message}")

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def _start_camera(self):
        selected = self.device_combo.currentText()
        if not selected.startswith("Camera"):
            self.statusBar().showMessage("Select a camera device first")
            return
        index = int(selected.split()[-1])
        try:
            self.camera_service.start_camera(index)
            self.camera_timer.start(30)
            self.statusBar().showMessage(f"Camera {index} live")
        except Exception as exc:
            self._show_error(f"Camera start failed: {exc}")

    def _stop_camera(self):
        self.camera_timer.stop()
        self.camera_service.stop_camera()
        self.statusBar().showMessage("Camera stopped")

    def _update_camera_frame(self):
        frame = self.camera_service.read_frame()
        if frame is None:
            return
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img)
        self.image_viewer.pixmap_item.setPixmap(pixmap)
        self.image_viewer.scene.setSceneRect(
            self.image_viewer.pixmap_item.boundingRect()
        )

    def _capture_image(self):
        frame = self.camera_service.read_frame()
        if frame is None:
            self.statusBar().showMessage("No camera frame available")
            return
        try:
            file_path = self.image_service.save_frame(frame)
            self._add_to_workspace(file_path)
            self.statusBar().showMessage(f"Captured: {Path(file_path).name}")
        except Exception as exc:
            self._show_error(f"Capture failed: {exc}")

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def _import_image(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Images", "", SUPPORTED_IMAGE_FORMATS
        )
        if not file_paths:
            return
        count = 0
        for fp in file_paths:
            if self._add_to_workspace(fp):
                count += 1
        self.statusBar().showMessage(f"{count} image(s) imported")

    # ------------------------------------------------------------------
    # Workspace helpers
    # ------------------------------------------------------------------

    def _add_to_workspace(self, file_path: str) -> bool:
        try:
            image = self.workspace_service.add_image(file_path)
        except Exception as e:
            self._show_error(str(e))
            return False

        # Check duplicate in list
        for i in range(self.workspace_list.count()):
            if self.workspace_list.item(i).data(Qt.UserRole) == image.file_path:
                return False

        # Thumbnail
        thumb = pixmap_thumbnail(image.file_path, THUMBNAIL_SIZE)
        item = QListWidgetItem(image.file_name)
        item.setData(Qt.UserRole, image.file_path)
        if not thumb.isNull():
            item.setIcon(QIcon(thumb))
        self.workspace_list.addItem(item)

        # Show in viewer
        self.image_viewer.load_image(image.file_path)
        self.current_image_path = image.file_path
        return True

    def _load_workspace_image(self, item: QListWidgetItem):
        file_path = item.data(Qt.UserRole)
        if file_path and self.image_viewer.load_image(file_path):
            self.current_image_path = file_path

    def _get_selected_paths(self) -> list:
        return [
            item.data(Qt.UserRole)
            for item in self.workspace_list.selectedItems()
            if item.data(Qt.UserRole)
        ]

    def _remove_selected(self):
        for item in self.workspace_list.selectedItems():
            fp = item.data(Qt.UserRole)
            self.workspace_service.remove_image(fp)
            self.workspace_list.takeItem(self.workspace_list.row(item))

    def _clear_workspace(self):
        self.workspace_list.clear()
        self.workspace_service.clear()
        self.statusBar().showMessage("Workspace cleared")

    # ------------------------------------------------------------------
    # Merge operations
    # ------------------------------------------------------------------

    def _merge_stitch(self):
        self._run_merge(self.merge_service.merge_stitch, "Smart Stitch")

    def _merge_vertical(self):
        self._run_merge(self.merge_service.merge_vertical, "Vertical Stack")

    def _merge_horizontal(self):
        self._run_merge(self.merge_service.merge_horizontal, "Horizontal Stack")

    def _merge_grid(self):
        self._run_merge(self.merge_service.merge_grid, "Grid Merge")

    def _run_merge(self, merge_func, label: str):
        paths = self._get_selected_paths()
        if len(paths) < 2:
            self._show_error("Select at least 2 images from the workspace.")
            return

        self._set_busy(True, f"{label} in progress...")

        self._merge_worker = MergeWorker(merge_func, paths)
        self._merge_worker.finished.connect(
            lambda img: self._on_merge_finished(img, label)
        )
        self._merge_worker.error.connect(self._on_merge_error)
        self._merge_worker.start()

    def _on_merge_finished(self, image, label: str):
        self._set_busy(False)
        try:
            file_path = self.image_service.save_image(image)
            self._add_to_workspace(file_path)
            self.statusBar().showMessage(f"{label} complete: {Path(file_path).name}")
        except Exception as e:
            self._show_error(str(e))

    def _on_merge_error(self, message: str):
        self._set_busy(False)
        self._show_error(f"Merge failed: {message}")

    # ------------------------------------------------------------------
    # Smart Crop (border removal) & Auto Crop & Straighten
    # ------------------------------------------------------------------

    def _smart_crop_selected(self):
        """Remove scanner dark borders from selected images."""
        paths = self._get_selected_paths()
        if not paths:
            self._show_error("Select at least one image from the workspace.")
            return
        self._set_busy(True, "Smart crop — removing scanner borders...")
        self._batch_worker = BatchImageWorker(
            self.merge_service.smart_crop_paths, paths
        )
        self._batch_worker.finished.connect(self._on_auto_crop_finished)
        self._batch_worker.error.connect(self._on_auto_crop_error)
        self._batch_worker.start()

    def _auto_crop_selected(self):
        paths = self._get_selected_paths()
        if not paths:
            self._show_error("Select at least one image from the workspace.")
            return

        self._set_busy(True, "Auto crop & straighten...")
        self._batch_worker = BatchImageWorker(
            self.merge_service.auto_crop_straighten_paths,
            paths,
        )
        self._batch_worker.finished.connect(self._on_auto_crop_finished)
        self._batch_worker.error.connect(self._on_auto_crop_error)
        self._batch_worker.start()

    def _on_auto_crop_finished(self, images):
        self._set_busy(False)
        saved = []
        try:
            for image in images:
                if image is not None:
                    saved.append(self.image_service.save_image(image))
        except Exception as exc:
            self._show_error(f"Auto crop save failed: {exc}")
            return

        if not saved:
            self._show_error("Auto crop did not produce any results.")
            return

        for file_path in saved:
            self._add_to_workspace(file_path)
        self.statusBar().showMessage(f"Auto crop applied to {len(saved)} image(s)")

    def _on_auto_crop_error(self, message: str):
        self._set_busy(False)
        self._show_error(f"Auto crop failed: {message}")

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_image(self):
        if not self.current_image_path:
            self._show_error("No image selected for export.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export Image",
            Path(self.current_image_path).stem,
            "JPEG (*.jpg);;PNG (*.png);;TIFF (*.tif)"
        )
        if not dest:
            return
        try:
            self.export_service.export_image(self.current_image_path, dest)
            self.statusBar().showMessage(f"Exported: {Path(dest).name}")
        except Exception as e:
            self._show_error(f"Export failed: {e}")

    def _export_pdf(self):
        paths = self._get_selected_paths()
        if not paths:
            # Fall back to current image
            if self.current_image_path:
                paths = [self.current_image_path]
            else:
                self._show_error("Select images to export as PDF.")
                return

        dest, _ = QFileDialog.getSaveFileName(
            self, "Export as PDF", "document", "PDF (*.pdf)"
        )
        if not dest:
            return
        try:
            self.export_service.export_pdf(paths, dest)
            self.statusBar().showMessage(
                f"PDF exported: {Path(dest).name} ({len(paths)} page(s))"
            )
        except Exception as e:
            self._show_error(f"PDF export failed: {e}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool, message: str = ""):
        self.scan_btn.setEnabled(not busy)
        self.stitch_btn.setEnabled(not busy)
        self.vertical_btn.setEnabled(not busy)
        self.horizontal_btn.setEnabled(not busy)
        self.grid_btn.setEnabled(not busy)
        self.smart_crop_btn.setEnabled(not busy)
        self.crop_btn.setEnabled(not busy)
        self.progress_bar.setVisible(busy)
        if message:
            self.statusBar().showMessage(message)

    def _show_error(self, message: str):
        self.statusBar().showMessage(message)
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event):
        try:
            self._stop_camera()
        except Exception:
            pass
        event.accept()
