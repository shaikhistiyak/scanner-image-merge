from PyQt5.QtCore import QThread, pyqtSignal
from utils.logger import get_logger

logger = get_logger(__name__)


class ScanWorker(QThread):
    """
    Runs scanner acquisition in a background thread so the UI stays responsive.

    Signals
    -------
    finished(str) - emitted with saved file path on success
    error(str)    - emitted with error message on failure
    """

    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, scanner_service, scanner_name: str, dpi: int, color_mode: str):
        super().__init__()
        self.scanner_service = scanner_service
        self.scanner_name = scanner_name
        self.dpi = dpi
        self.color_mode = color_mode

    def run(self):
        try:
            logger.info(
                "ScanWorker: %s | %s DPI | %s",
                self.scanner_name,
                self.dpi,
                self.color_mode,
            )
            file_path = self.scanner_service.scan_image(
                self.scanner_name,
                dpi=self.dpi,
                color_mode=self.color_mode,
            )
            self.finished.emit(file_path)
        except Exception as exc:
            logger.exception("ScanWorker error")
            self.error.emit(str(exc))


class MergeWorker(QThread):
    """Runs merge/stitch operations in the background."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, merge_func, image_paths: list):
        super().__init__()
        self.merge_func = merge_func
        self.image_paths = image_paths

    def run(self):
        try:
            result = self.merge_func(self.image_paths)
            self.finished.emit(result)
        except Exception as exc:
            logger.exception("MergeWorker error")
            self.error.emit(str(exc))


class BatchImageWorker(QThread):
    """Runs batch image processing in the background."""

    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, process_func, image_paths: list):
        super().__init__()
        self.process_func = process_func
        self.image_paths = image_paths

    def run(self):
        try:
            results = self.process_func(self.image_paths)
            self.finished.emit(results)
        except Exception as exc:
            logger.exception("BatchImageWorker error")
            self.error.emit(str(exc))
