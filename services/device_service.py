from services.camera_service import CameraService
from services.scanner_service import ScannerService
from utils.logger import get_logger

logger = get_logger(__name__)


class DeviceService:

    def __init__(self):
        self.camera_service = CameraService()
        self.scanner_service = ScannerService()

    def get_devices(self):
        devices = []
        devices.extend(self.camera_service.get_cameras())
        try:
            devices.extend(self.scanner_service.get_scanner_names())
        except Exception as e:
            logger.error(f"Scanner detection error: {e}")
        return devices
