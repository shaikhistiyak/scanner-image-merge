from services.camera_service import CameraService
from services.scanner_service import ScannerService


class DeviceService:

    def __init__(self):
        self.camera_service = CameraService()
        self.scanner_service = ScannerService()

    def get_devices(self):

        devices = []

        # Cameras
        devices.extend(
            self.camera_service.get_cameras()
        )

        # Scanners
        try:
            devices.extend(
                self.scanner_service.get_scanner_names()
            )
        except Exception as e:
            print(
                f"Scanner detection error: {e}"
            )

        return devices