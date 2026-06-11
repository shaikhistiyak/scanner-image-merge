try:
    import win32com.client
except ImportError:
    win32com = None
from pathlib import Path
from datetime import datetime

class ScannerService:

    def __init__(self):
        self.scanners = []

    def get_scanners(self):

        self.scanners = []

        if win32com is None:
            return self.scanners

        try:
            device_manager = win32com.client.Dispatch(
                "WIA.DeviceManager"
            )

            for device in device_manager.DeviceInfos:

                try:
                    # WIA Scanner Type = 1
                    if device.Type == 1:

                        scanner = {
                            "name": device.Properties("Name").Value,
                            "device_id": device.DeviceID,
                        }

                        self.scanners.append(scanner)

                except Exception:
                    pass

        except Exception as e:
            print(
                f"Scanner detection error: {e}"
            )

        return self.scanners

    def get_scanner_names(self):

        scanners = self.get_scanners()

        return [
            scanner["name"]
            for scanner in scanners
        ]

    def find_scanner(self, scanner_name):

        scanners = self.get_scanners()

        for scanner in scanners:

            if scanner["name"] == scanner_name:
                return scanner

        return None

    def scan_image(self, scanner_name):

        scanner = self.find_scanner(
            scanner_name
        )

        if scanner is None:
            raise ValueError(
                f"Scanner not found: {scanner_name}"
            )

        if win32com is None:
            raise RuntimeError(
                "pywin32 is not installed."
            )

        try:

            device_manager = win32com.client.Dispatch(
                "WIA.DeviceManager"
            )

            device = None

            for info in device_manager.DeviceInfos:

                if info.DeviceID == scanner["device_id"]:
                    device = info.Connect()
                    break

            if device is None:
                raise RuntimeError(
                    "Unable to connect to scanner."
                )

            item = device.Items[1]

            image = item.Transfer()

            temp_dir = Path("temp")
            temp_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            file_name = (
                f"scan_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                f".jpg"
            )

            output_path = temp_dir / file_name

            image.SaveFile(
                str(output_path)
            )

            return str(output_path)

        except Exception as e:
            raise RuntimeError(
                f"Scan failed: {e}"
            )