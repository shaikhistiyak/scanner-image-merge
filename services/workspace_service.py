from models.workspace_image import WorkspaceImage
from pathlib import Path


class WorkspaceService:

    def __init__(self):
        self.images = []

    def add_image(self, file_path):
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"Image not found: {file_path}")

        file_path = str(path.resolve())
        file_name = path.name

        for image in self.images:
            if image.file_path == file_path:
                return image

        image = WorkspaceImage(
            file_path=file_path,
            file_name=file_name
        )

        self.images.append(image)

        return image

    def get_images(self):
        return self.images

    def clear(self):
        self.images.clear()