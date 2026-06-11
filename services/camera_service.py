import cv2
from utils.logger import get_logger

logger = get_logger(__name__)


class CameraService:

    def __init__(self):
        self.cap = None

    def get_cameras(self):
        cameras = []
        for index in range(10):
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            try:
                if cap.isOpened():
                    cameras.append(f"Camera {index}")
            finally:
                cap.release()
        return cameras

    def start_camera(self, index=0):
        self.stop_camera()
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap.release()
            self.cap = None
            raise RuntimeError(f"Unable to open camera {index}")
        logger.info("Camera %s started", index)

    def read_frame(self):
        if self.cap is None:
            return None
        success, frame = self.cap.read()
        return frame if success else None

    def stop_camera(self):
        if self.cap:
            self.cap.release()
            self.cap = None
            logger.info("Camera stopped")
