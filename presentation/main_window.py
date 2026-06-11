from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QFileDialog,
    QAbstractItemView,
    QMessageBox,
)
from PyQt6.QtGui import (
    QAction,
    QImage,
    QPixmap,
)

from pathlib import Path

from presentation.widgets.image_viewer import ImageViewer

from services.device_service import DeviceService
from services.camera_service import CameraService
from services.image_service import ImageService
from services.workspace_service import WorkspaceService
from services.merge_service import MergeService
from services.export_service import ExportService

import cv2


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
        
        self.setWindowTitle("Scanner Image Merge Pro")
        self.resize(1400, 900)

        self.setup_ui()

        self.refresh_devices()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_camera_frame)
        
        
        self.statusBar().showMessage("Ready")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # =========================
        # LEFT PANEL
        # =========================

        left_panel = QFrame()
        left_panel.setFixedWidth(250)

        left_layout = QVBoxLayout(left_panel)

        # =========================
        # DEVICE
        # =========================

        left_layout.addWidget(QLabel("Device"))

        self.device_combo = QComboBox()
        self.device_combo.addItems([
            "No Device Connected"
        ])

        left_layout.addWidget(self.device_combo)

        self.refresh_btn = QPushButton("Refresh Devices")
        
        self.refresh_btn.clicked.connect(
            self.refresh_devices
        )
        
        left_layout.addWidget(self.refresh_btn)

        # =========================
        # SCAN SETTINGS
        # =========================

        left_layout.addSpacing(15)

        left_layout.addWidget(QLabel("Resolution"))

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems([
            "75 DPI",
            "150 DPI",
            "300 DPI",
            "600 DPI"
        ])

        left_layout.addWidget(self.resolution_combo)

        left_layout.addWidget(QLabel("Color Mode"))

        self.color_combo = QComboBox()
        self.color_combo.addItems([
            "Color",
            "Grayscale",
            "Black & White"
        ])

        left_layout.addWidget(self.color_combo)

        # =========================
        # ACTIONS
        # =========================

        left_layout.addSpacing(15)

        self.scan_btn = QPushButton("Scan")
        self.scan_btn.clicked.connect(
            self.scan_document
        )
        left_layout.addWidget(self.scan_btn)

        self.capture_btn = QPushButton("Capture")
        self.capture_btn.clicked.connect(
            self.capture_image
        )
        left_layout.addWidget(self.capture_btn)

        self.start_camera_btn = QPushButton("Start Camera")
        self.stop_camera_btn = QPushButton("Stop Camera")

        self.start_camera_btn.clicked.connect(
            self.start_camera
        )

        self.stop_camera_btn.clicked.connect(
            self.stop_camera
        )
        left_layout.addWidget(self.start_camera_btn)
        left_layout.addWidget(self.stop_camera_btn)
        
        
        left_layout.addStretch()

        # =========================
        # CENTER PANEL
        # =========================

        center_panel = QFrame()

        center_layout = QVBoxLayout(center_panel)

        self.image_viewer = ImageViewer()

        center_layout.addWidget(self.image_viewer)

        # =========================
        # RIGHT PANEL
        # =========================

        right_panel = QFrame()
        right_panel.setFixedWidth(300)

        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Workspace Images"))

        self.workspace_list= QListWidget()
        self.workspace_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.workspace_list.itemClicked.connect(
            self.load_workspace_image
        )
        right_layout.addWidget(self.workspace_list)

        right_layout.addWidget(QLabel("Merge Options"))

        self.vertical_btn = QPushButton("Vertical Merge")
        self.horizontal_btn = QPushButton("Horizontal Merge")
        self.grid_btn = QPushButton("Grid Merge")

        self.vertical_btn.clicked.connect(
            self.merge_vertical
        )

        self.horizontal_btn.clicked.connect(
            self.merge_horizontal
        )

        self.grid_btn.clicked.connect(
            self.merge_grid
        )
        
        right_layout.addWidget(self.vertical_btn)
        right_layout.addWidget(self.horizontal_btn)
        right_layout.addWidget(self.grid_btn)

        # =========================
        # MAIN LAYOUT
        # =========================

        main_layout.addWidget(left_panel)
        main_layout.addWidget(center_panel, 1)
        main_layout.addWidget(right_panel)

        # =========================
        # TOOLBAR
        # =========================

        toolbar = self.addToolBar("Tools")

        self.import_action = QAction("Import", self)
        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_out_action = QAction("Zoom Out", self)
        self.rotate_left_action = QAction("Rotate Left", self)
        self.rotate_right_action = QAction("Rotate Right", self)
        self.fit_action = QAction("Fit Screen", self)
        self.export_action = QAction(
            "Export",
            self
        )
        
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.zoom_in_action)
        toolbar.addAction(self.zoom_out_action)
        toolbar.addAction(self.rotate_left_action)
        toolbar.addAction(self.rotate_right_action)
        toolbar.addAction(self.fit_action)
        toolbar.addAction(
            self.export_action
        )

        # =========================
        # SIGNALS
        # =========================

        self.import_action.triggered.connect(self.import_image)

        self.zoom_in_action.triggered.connect(
            self.image_viewer.zoom_in
        )

        self.zoom_out_action.triggered.connect(
            self.image_viewer.zoom_out
        )

        self.rotate_left_action.triggered.connect(
            self.image_viewer.rotate_left
        )

        self.rotate_right_action.triggered.connect(
            self.image_viewer.rotate_right
        )

        self.fit_action.triggered.connect(
            self.image_viewer.fit_image
        )
        self.export_action.triggered.connect(
            self.export_image
        )

    def import_image(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open Images",
            "",
            "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)"
        )

        if not file_paths:
            return

        imported = 0

        first_path = None

        for file_path in file_paths:
            try:
                image = self.workspace_service.add_image(file_path)
            except Exception as exc:
                self.show_error_message(
                    f"Failed to import {Path(file_path).name}: {exc}"
                )
                continue

            if image is None:
                continue

            already_added = any(
                self.workspace_list.item(i).data(Qt.ItemDataRole.UserRole) == image.file_path
                for i in range(self.workspace_list.count())
            )

            if already_added:
                continue

            self.add_workspace_item(image.file_path, image.file_name)
            imported += 1

            if first_path is None:
                first_path = image.file_path

        if imported == 0:
            return

        if first_path is None or not self.image_viewer.load_image(first_path):
            self.show_error_message(
                f"Imported image could not be displayed: {Path(file_paths[0]).name}"
            )
            return
        
        self.image_viewer.load_image(first_path)
        
        self.statusBar().showMessage(
            f"{imported} image(s) imported"
        )
    
    def refresh_devices(self):

        self.device_combo.clear()

        devices = self.device_service.get_devices()

        if not devices:
            self.device_combo.addItem(
                "No Device Found"
            )

            self.statusBar().showMessage(
                "No devices detected"
            )

            return

        self.device_combo.addItems(devices)

        self.statusBar().showMessage(
            f"{len(devices)} device(s) detected"
        )
        
    def start_camera(self):
        selected = self.device_combo.currentText()

        if not selected.startswith("Camera"):
            self.statusBar().showMessage(
                "No camera selected"
            )
            return

        camera_index = int(selected.split()[-1])

        self.camera_service.start_camera(camera_index)

        self.timer.start(30)

        self.statusBar().showMessage(
            f"Camera {camera_index} started"
        )
    
    def stop_camera(self):

        self.timer.stop()

        self.camera_service.stop_camera()

        self.statusBar().showMessage(
            "Camera stopped"
        )
        
    def update_camera_frame(self):

        frame = self.camera_service.read_frame()

        if frame is None:
            return

        frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        h, w, ch = frame.shape

        image = QImage(
            frame.data,
            w,
            h,
            ch * w,
            QImage.Format.Format_RGB888
        )

        pixmap = QPixmap.fromImage(image)

        self.image_viewer.pixmap_item.setPixmap(
            pixmap
        )

        self.image_viewer.scene.setSceneRect(
            self.image_viewer.pixmap_item.boundingRect()
        )
    def closeEvent(self, event):

        try:
            self.stop_camera()
        except:
            pass

        event.accept()
        
    def capture_image(self):

        frame = self.camera_service.read_frame()

        if frame is None:
            self.statusBar().showMessage(
                "No camera frame available"
            )
            return

        file_path = self.image_service.save_frame(frame)

        try:
            image = self.workspace_service.add_image(file_path)
        except Exception as exc:
            self.show_error_message(
                f"Failed to add captured image: {exc}"
            )
            return

        if image:
            self.add_workspace_item(image.file_path, image.file_name)

        if not self.image_viewer.load_image(file_path):
            self.show_error_message(
                f"Captured image could not be displayed: {Path(file_path).name}"
            )
            return

        self.current_image_path = file_path
        
        self.statusBar().showMessage(
            f"Captured: {Path(file_path).name}"
        )
        
    def scan_document(self):

        selected_device = (
            self.device_combo.currentText()
        )

        if (
            not selected_device
            or selected_device == "No Device Found"
            or selected_device.startswith("Camera")
        ):
            self.show_error_message(
                "Please select a scanner"
            )
            return

        try:

            file_path = (
                self.device_service
                .scanner_service
                .scan_image(selected_device)
            )

            image = (
                self.workspace_service
                .add_image(file_path)
            )

            if image:
                self.add_workspace_item(
                    image.file_path,
                    image.file_name
                )

            if not self.image_viewer.load_image(
                file_path
            ):
                raise ValueError(
                    "Failed to display scanned image"
                )

            self.current_image_path = file_path

            self.statusBar().showMessage(
                "Scan completed"
            )

        except Exception as e:

            self.show_error_message(
                f"Scan failed: {e}"
            )
    def load_workspace_image(self, item):
        file_path = item.data(Qt.ItemDataRole.UserRole)

        if not file_path:
            self.show_error_message("Selected image has no path assigned")
            return

        if not self.image_viewer.load_image(file_path):
            self.show_error_message(
                f"Unable to display image: {Path(file_path).name}"
            )
            return

        self.current_image_path = file_path
        
    def get_selected_image_paths(self):

        selected_items = self.workspace_list.selectedItems()

        paths = []

        for item in selected_items:
            file_path = item.data(Qt.ItemDataRole.UserRole)

            if file_path:
                paths.append(file_path)

        return paths
    
    def merge_vertical(self):
        self.process_merge(
            self.merge_service.merge_vertical,
            "Vertical merge completed"
        )

    def merge_horizontal(self):
        self.process_merge(
            self.merge_service.merge_horizontal,
            "Horizontal merge completed"
        )

    def merge_grid(self):
        self.process_merge(
            self.merge_service.merge_grid,
            "Grid merge completed"
        )

    def process_merge(self, merge_func, success_message):
        image_paths = self.get_selected_image_paths()

        if len(image_paths) < 2:
            self.show_error_message("Select at least 2 images")
            return

        try:
            merged = merge_func(image_paths)

            if merged is None or not hasattr(merged, 'size') or merged.size == 0:
                raise ValueError("Merged image is invalid")

            file_path = self.image_service.save_image(merged)

            if not self.image_viewer.load_image(file_path):
                raise ValueError("Failed to load merged image")
            
            self.current_image_path = file_path
            
            self.statusBar().showMessage(success_message)
        except Exception as exc:
            self.show_error_message(f"{success_message} failed: {exc}")

    def add_workspace_item(self, file_path, file_name):
        item = QListWidgetItem(file_name)
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        self.workspace_list.addItem(item)

    def export_image(self):

        if not self.current_image_path:
            self.show_error_message(
                "No image available for export"
            )
            return

        destination_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Image",
            Path(self.current_image_path).stem,
            "JPEG (*.jpg);;PNG (*.png)"
        )

        if not destination_path:
            return

        try:
            self.export_service.export_image(
                self.current_image_path,
                destination_path
            )

            self.statusBar().showMessage(
                "Image exported successfully"
            )

        except Exception as exc:
            self.show_error_message(
                f"Export failed: {exc}"
            )
            
    def show_error_message(self, message):
        self.statusBar().showMessage(message)
        QMessageBox.critical(self, "Error", message)