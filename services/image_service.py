import cv2
import numpy as np
from datetime import datetime
from utils.config import TEMP_DIR
from utils.logger import get_logger

logger = get_logger(__name__)


class ImageService:

    def save_frame(self, frame: np.ndarray) -> str:
        if frame is None:
            raise ValueError("No frame data to save")
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        file_path = TEMP_DIR / datetime.now().strftime("capture_%Y%m%d_%H%M%S.jpg")
        if not cv2.imwrite(str(file_path), frame):
            raise IOError(f"Failed to save frame: {file_path}")
        logger.info(f"Frame saved: {file_path}")
        return str(file_path)

    def save_image(self, image: np.ndarray) -> str:
        if image is None or image.size == 0:
            raise ValueError("Invalid image data")
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        file_path = TEMP_DIR / datetime.now().strftime("merged_%Y%m%d_%H%M%S.jpg")
        if not cv2.imwrite(str(file_path), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise IOError(f"Failed to save image: {file_path}")
        logger.info(f"Image saved: {file_path}")
        return str(file_path)
