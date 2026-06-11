from pathlib import Path

APP_NAME = "ScanMerge Pro"
APP_VERSION = "2.0.0"

BASE_DIR = Path(__file__).resolve().parents[1]
TEMP_DIR = BASE_DIR / "temp"
EXPORT_DIR = BASE_DIR / "exports"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "database" / "app.db"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

SUPPORTED_IMAGE_FORMATS = "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff)"

RESOLUTIONS = [75, 150, 300, 600]
DEFAULT_RESOLUTION = 300

COLOR_MODES = ["Color", "Grayscale", "Black & White"]
DEFAULT_COLOR_MODE = "Color"

WIA_COLOR_MAP = {
    "Color": 1,
    "Grayscale": 2,
    "Black & White": 4,
}

THUMBNAIL_SIZE = (90, 90)
