import shutil
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


class ExportService:

    def export_image(self, source_path: str, destination_path: str):
        """Copy image to destination."""
        shutil.copy2(source_path, destination_path)
        logger.info(f"Exported image: {destination_path}")

    def export_pdf(self, source_paths: list, destination_path: str):
        """
        Export one or more images as a single PDF.
        Each image becomes one page in the PDF.
        """
        try:
            import img2pdf
        except ImportError:
            raise RuntimeError(
                "img2pdf is not installed. Run: pip install img2pdf"
            )

        valid_paths = [p for p in source_paths if Path(p).exists()]
        if not valid_paths:
            raise ValueError("No valid image files found for PDF export.")

        # img2pdf requires JPEG or PNG — convert if needed
        processed = self._prepare_for_pdf(valid_paths)

        with open(destination_path, "wb") as f:
            f.write(img2pdf.convert(processed))

        logger.info(f"Exported PDF: {destination_path} ({len(processed)} page(s))")

    def _prepare_for_pdf(self, paths: list) -> list:
        """
        img2pdf works best with JPEG/PNG.
        Convert any unsupported formats to JPEG in temp dir.
        """
        import cv2
        from utils.config import TEMP_DIR
        from datetime import datetime

        result = []
        for p in paths:
            ext = Path(p).suffix.lower()
            if ext in (".jpg", ".jpeg", ".png"):
                result.append(p)
            else:
                # Convert to JPEG
                img = cv2.imread(str(p))
                if img is None:
                    continue
                out = str(TEMP_DIR / f"pdf_prep_{datetime.now().strftime('%H%M%S%f')}.jpg")
                cv2.imwrite(out, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                result.append(out)
        return result
