from pathlib import Path
from PIL import Image, ImageOps
from utils.logger import get_logger

logger = get_logger(__name__)


class ExportService:
    def export_image(self, source_path: str, destination_path: str):
        """Export an image and encode it to match the destination extension."""
        source = Path(source_path)
        destination = Path(destination_path)

        if not source.exists():
            raise FileNotFoundError(f"Source image not found: {source_path}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        suffix = destination.suffix.lower()
        if not suffix:
            destination = destination.with_suffix(source.suffix or ".jpg")
            suffix = destination.suffix.lower()

        image_format = self._format_from_suffix(suffix)
        with Image.open(source) as image:
            image = ImageOps.exif_transpose(image)
            if image_format in ("JPEG", "PDF") and image.mode in ("RGBA", "LA", "P"):
                image = image.convert("RGB")
            save_options = {"quality": 95} if image_format == "JPEG" else {}
            image.save(destination, format=image_format, **save_options)

        logger.info("Exported image: %s", destination)

    def export_pdf(self, source_paths: list, destination_path: str):
        """
        Export one or more images as a single PDF.
        Each image becomes one page in the PDF.
        """
        destination = Path(destination_path)
        if destination.suffix.lower() != ".pdf":
            destination = destination.with_suffix(".pdf")
        destination.parent.mkdir(parents=True, exist_ok=True)

        valid_paths = [Path(path) for path in source_paths if Path(path).exists()]
        if not valid_paths:
            raise ValueError("No valid image files found for PDF export.")

        pages = []
        try:
            for path in valid_paths:
                image = Image.open(path)
                image = ImageOps.exif_transpose(image)
                if image.mode != "RGB":
                    image = image.convert("RGB")
                pages.append(image)

            first_page = pages[0]
            first_page.save(
                destination,
                "PDF",
                resolution=300.0,
                save_all=True,
                append_images=pages[1:],
            )
        finally:
            for page in pages:
                page.close()

        logger.info("Exported PDF: %s (%s page(s))", destination, len(valid_paths))

    def _format_from_suffix(self, suffix: str) -> str:
        formats = {
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".tif": "TIFF",
            ".tiff": "TIFF",
            ".bmp": "BMP",
        }
        try:
            return formats[suffix]
        except KeyError:
            raise ValueError(f"Unsupported export format: {suffix}")
