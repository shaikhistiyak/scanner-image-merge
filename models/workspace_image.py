from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkspaceImage:
    file_path: str
    file_name: str

    @property
    def extension(self) -> str:
        return Path(self.file_path).suffix.lower()

    @property
    def exists(self) -> bool:
        return Path(self.file_path).exists()
