import cv2


class CameraService:

    def __init__(self):
        self.cap = None

    def get_cameras(self):
        cameras = []

        for index in range(10):
            cap = cv2.VideoCapture(index)

            if cap.isOpened():
                cameras.append(f"Camera {index}")
                cap.release()

        return cameras

    def start_camera(self, index=0):
        self.cap = cv2.VideoCapture(index)

    def read_frame(self):
        if self.cap is None:
            return None

        success, frame = self.cap.read()

        if not success:
            return None

        return frame

    def stop_camera(self):
        if self.cap:
            self.cap.release()
            self.cap = None