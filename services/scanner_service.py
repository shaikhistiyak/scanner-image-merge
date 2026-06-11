try:
    import win32com.client
    import pythoncom
except ImportError:
    win32com = None
    pythoncom = None

from datetime import datetime
from utils.config import TEMP_DIR, WIA_COLOR_MAP
from utils.logger import get_logger

logger = get_logger(__name__)


class ScannerService:
    def __init__(self):
        self.scanners = []

    def get_scanners(self):
        self.scanners = []
        if win32com is None:
            logger.warning("pywin32 not installed - scanner detection disabled")
            return self.scanners

        try:
            device_manager = win32com.client.Dispatch("WIA.DeviceManager")
            for device in device_manager.DeviceInfos:
                try:
                    if device.Type == 1:
                        self.scanners.append({
                            "name": device.Properties("Name").Value,
                            "device_id": device.DeviceID,
                        })
                except Exception as exc:
                    logger.debug("Skipping WIA device during detection: %s", exc)
        except Exception:
            logger.exception("Scanner detection error")

        return self.scanners

    def get_scanner_names(self):
        return [scanner["name"] for scanner in self.get_scanners()]

    def find_scanner(self, scanner_name):
        for scanner in self.get_scanners():
            if scanner["name"] == scanner_name:
                return scanner
        return None

    def scan_image(self, scanner_name, dpi: int = 300, color_mode: str = "Color") -> str:
        """
        Scan a document through WIA and return the saved file path.

        Parameters
        ----------
        scanner_name : str
            Name of the scanner as shown in the device list.
        dpi : int
            Scan resolution.
        color_mode : str
            "Color", "Grayscale", or "Black & White".
        """
        if win32com is None:
            raise RuntimeError("pywin32 is not installed.")

        scanner = self.find_scanner(scanner_name)
        if scanner is None:
            raise ValueError(f"Scanner not found: {scanner_name}")

        com_initialized = False
        try:
            if pythoncom is not None:
                pythoncom.CoInitialize()
                com_initialized = True

            device_manager = win32com.client.Dispatch("WIA.DeviceManager")
            device = None
            for info in device_manager.DeviceInfos:
                if info.DeviceID == scanner["device_id"]:
                    device = info.Connect()
                    break

            if device is None:
                raise RuntimeError("Unable to connect to scanner.")

            item = device.Items[1]

            try:
                item.Properties("Horizontal Resolution").Value = dpi
                item.Properties("Vertical Resolution").Value = dpi
                logger.info("DPI set to %s", dpi)
            except Exception as exc:
                logger.warning("Could not set DPI: %s", exc)

            try:
                wia_intent = WIA_COLOR_MAP.get(color_mode, 1)
                item.Properties("Current Intent").Value = wia_intent
                logger.info("Color mode set to %s (WIA intent %s)", color_mode, wia_intent)
            except Exception as exc:
                logger.warning("Could not set color mode: %s", exc)

            image = item.Transfer()

            TEMP_DIR.mkdir(parents=True, exist_ok=True)
            file_name = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
            output_path = TEMP_DIR / file_name
            image.SaveFile(str(output_path))

            logger.info("Scan saved: %s", output_path)
            return str(output_path)

        except Exception as exc:
            logger.exception("Scan failed")
            raise RuntimeError(f"Scan failed: {exc}")
        finally:
            if com_initialized:
                pythoncom.CoUninitialize()
