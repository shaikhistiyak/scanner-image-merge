import cv2
import numpy as np


class MergeService:

    def _ensure_bgr(self, image):
        if image is None:
            return None

        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)

        if image.ndim == 3 and image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)

        if image.ndim == 3 and image.shape[2] == 3:
            return image

        raise ValueError("Unsupported image format")

    def _load_images(self, image_paths):
        images = []
        errors = []

        for path in image_paths:
            image = cv2.imread(str(path))

            if image is None:
                errors.append(str(path))
                continue

            image = self._ensure_bgr(image)
            images.append(image)

        if errors:
            raise ValueError(
                f"Failed to load the following image(s): {', '.join(errors)}"
            )

        if len(images) < 2:
            raise ValueError("At least two valid images are required for merge")

        return images

    def merge_vertical(self, image_paths):
        images = self._load_images(image_paths)

        max_width = max(image.shape[1] for image in images)

        resized = []
        for image in images:
            h, w = image.shape[:2]
            ratio = max_width / float(w)
            new_height = max(1, int(h * ratio))
            resized.append(cv2.resize(image, (max_width, new_height)))

        return np.vstack(resized)

    def merge_horizontal(self, image_paths):
        images = self._load_images(image_paths)

        max_height = max(image.shape[0] for image in images)

        resized = []
        for image in images:
            h, w = image.shape[:2]
            ratio = max_height / float(h)
            new_width = max(1, int(w * ratio))
            resized.append(cv2.resize(image, (new_width, max_height)))

        return np.hstack(resized)

    def merge_grid(self, image_paths, columns=2):
        images = self._load_images(image_paths)

        rows = []
        for i in range(0, len(images), columns):
            row_images = images[i:i + columns]
            max_height = max(img.shape[0] for img in row_images)

            resized_row = []
            for img in row_images:
                h, w = img.shape[:2]
                ratio = max_height / float(h)
                resized_row.append(cv2.resize(img, (max(1, int(w * ratio)), max_height)))

            rows.append(np.hstack(resized_row))

        max_width = max(row.shape[1] for row in rows)

        padded_rows = []
        for row in rows:
            if row.shape[1] < max_width:
                diff = max_width - row.shape[1]
                row = cv2.copyMakeBorder(
                    row,
                    0,
                    0,
                    0,
                    diff,
                    cv2.BORDER_CONSTANT,
                    value=(255, 255, 255),
                )
            padded_rows.append(row)

        return np.vstack(padded_rows)
