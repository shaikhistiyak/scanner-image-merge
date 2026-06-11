from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ScanJob:
    scanner_name: str
    dpi: int
    color_mode: str
    created_at: datetime = field(default_factory=datetime.now)
    file_path: str = ""
    success: bool = False
    error_message: str = ""
