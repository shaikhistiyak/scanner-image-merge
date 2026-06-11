import shutil


class ExportService:

    def export_image(
        self,
        source_path,
        destination_path
    ):
        shutil.copy2(
            source_path,
            destination_path
        )