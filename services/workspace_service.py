from models.workspace_image import WorkspaceImage
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


class WorkspaceService:

    def __init__(self):
        self.images: list[WorkspaceImage] = []

    def add_image(self, file_path: str) -> WorkspaceImage:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {file_path}")
        resolved = str(path.resolve())
        for img in self.images:
            if img.file_path == resolved:
                return img
        image = WorkspaceImage(file_path=resolved, file_name=path.name)
        self.images.append(image)
        logger.info(f"Added to workspace: {path.name}")
        return image

    def remove_image(self, file_path: str):
        self.images = [i for i in self.images if i.file_path != file_path]

    def get_images(self) -> list:
        return self.images

    def clear(self):
        self.images.clear()
        logger.info("Workspace cleared")
