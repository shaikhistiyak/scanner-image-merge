from pathlib import Path
from datetime import datetime
import cv2


class ImageService:

    TEMP_DIR = Path(__file__).resolve().parents[1] / "temp"

    def save_frame(self, frame):
        if frame is None:
            raise ValueError("No frame data to save")

        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)

        filename = datetime.now().strftime(
            "capture_%Y%m%d_%H%M%S.jpg"
        )

        file_path = self.TEMP_DIR / filename

        success = cv2.imwrite(str(file_path), frame)
        if not success:
            raise IOError(f"Failed to save captured image to {file_path}")

        return str(file_path)

    def save_image(self, image):
        if image is None or not hasattr(image, 'size') or image.size == 0:
            raise ValueError("Invalid image data to save")

        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)

        file_path = self.TEMP_DIR / datetime.now().strftime(
            "merged_%Y%m%d_%H%M%S.jpg"
        )

        success = cv2.imwrite(str(file_path), image)
        if not success:
            raise IOError(f"Failed to save merged image to {file_path}")

        return str(file_path)
