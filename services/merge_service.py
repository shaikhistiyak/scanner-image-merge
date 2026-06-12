import cv2
import numpy as np
from utils.logger import get_logger
from services.stitching_engine import StitchingEngine

logger = get_logger(__name__)


class MergeService:

    def __init__(self):
        self._engine = StitchingEngine()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
        images, errors = [], []
        for path in image_paths:
            img = cv2.imread(str(path))
            if img is None:
                errors.append(str(path))
                continue
            images.append(self._ensure_bgr(img))
        if errors:
            raise ValueError(f"Failed to load: {', '.join(errors)}")
        if len(images) < 2:
            raise ValueError("At least two valid images are required")
        return images

    # ------------------------------------------------------------------
    # ✨ SMART CROP — removes scanner border shadows and dead zones
    # ------------------------------------------------------------------

    def smart_crop(self, image):
        """
        Remove dark scanner borders and black dead zones.
        Uses 30th-percentile brightness per row/column.
        Works for all document types on any scanner.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        row_p30 = np.percentile(gray, 30, axis=1)
        col_p30 = np.percentile(gray, 30, axis=0)

        threshold = 100
        bright_rows = np.where(row_p30 > threshold)[0]
        bright_cols = np.where(col_p30 > threshold)[0]

        if len(bright_rows) == 0 or len(bright_cols) == 0:
            logger.warning("smart_crop: no bright area found, returning original")
            return image

        pad = 8
        t = max(0,  bright_rows[0]  - pad)
        b = min(h,  bright_rows[-1] + pad)
        l = max(0,  bright_cols[0]  - pad)
        r = min(w,  bright_cols[-1] + pad)

        cropped = image[t:b, l:r]
        logger.info(f"smart_crop: {w}x{h} → {r-l}x{b-t}")
        return cropped

    def smart_crop_paths(self, image_paths):
        """Apply smart_crop to each path. Returns list of numpy images."""
        images = []
        for path in image_paths:
            img = cv2.imread(str(path))
            if img is None:
                logger.warning(f"Could not load: {path}")
                continue
            images.append(self.smart_crop(self._ensure_bgr(img)))
        return images

    # ------------------------------------------------------------------
    # ✨ SMART STITCH — translation-only, correct for flat documents
    # ------------------------------------------------------------------

    def merge_stitch(self, image_paths):
        """
        Professional seamless stitch using the full pipeline:
          SIFT features → FLANN matching → RANSAC translation →
          Exposure compensation → Optimal seam (DP) → Laplacian pyramid blend

        Same approach as Adobe Photoshop Photomerge (Reposition Only mode).
        Works for any document type: newspapers, A4, books, certificates, maps.
        """
        images = self._load_images(image_paths)
        logger.info(f"merge_stitch: {len(images)} images — professional pipeline")

        # Smart-crop scanner borders first
        cropped = [self.smart_crop(img) for img in images]

        # Stitch with the professional engine
        return self._engine.stitch(cropped)

    # ------------------------------------------------------------------
    # Basic merges (kept for manual use)
    # ------------------------------------------------------------------

    def merge_vertical(self, image_paths):
        images = self._load_images(image_paths)
        max_width = max(img.shape[1] for img in images)
        resized = []
        for img in images:
            h, w = img.shape[:2]
            resized.append(cv2.resize(img, (max_width, max(1, int(h * max_width / w)))))
        return np.vstack(resized)

    def merge_horizontal(self, image_paths):
        images = self._load_images(image_paths)
        max_height = max(img.shape[0] for img in images)
        resized = []
        for img in images:
            h, w = img.shape[:2]
            resized.append(cv2.resize(img, (max(1, int(w * max_height / h)), max_height)))
        return np.hstack(resized)

    def merge_grid(self, image_paths, columns=2):
        images = self._load_images(image_paths)
        rows = []
        for i in range(0, len(images), columns):
            row_imgs = images[i:i + columns]
            max_h = max(img.shape[0] for img in row_imgs)
            row = []
            for img in row_imgs:
                h, w = img.shape[:2]
                row.append(cv2.resize(img, (max(1, int(w * max_h / h)), max_h)))
            rows.append(np.hstack(row))
        max_w = max(r.shape[1] for r in rows)
        padded = []
        for r in rows:
            if r.shape[1] < max_w:
                r = cv2.copyMakeBorder(r, 0, 0, 0, max_w - r.shape[1],
                                       cv2.BORDER_CONSTANT, value=(255, 255, 255))
            padded.append(r)
        return np.vstack(padded)

    # ------------------------------------------------------------------
    # AUTO CROP & STRAIGHTEN (perspective correction)
    # ------------------------------------------------------------------

    def auto_crop_straighten(self, image):
        """
        Smart crop + optional perspective correction.
        Step 1: Remove scanner borders (smart_crop).
        Step 2: Detect 4-corner document boundary and warp flat.
        """
        # Always start with smart_crop
        cropped = self.smart_crop(image)
        orig = cropped.copy()

        gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        for t_lo, t_hi in [(30, 100), (50, 150), (75, 200)]:
            edged = cv2.Canny(blurred, t_lo, t_hi)
            edged = cv2.dilate(edged, None, iterations=1)
            contours, _ = cv2.findContours(edged, cv2.RETR_LIST,
                                            cv2.CHAIN_APPROX_SIMPLE)
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

            for c in contours:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                area = cv2.contourArea(approx)
                img_area = cropped.shape[0] * cropped.shape[1]
                if len(approx) == 4 and area > img_area * 0.25:
                    logger.info("Perspective boundary found — applying warp")
                    return self._four_point_transform(orig, approx.reshape(4, 2))

        logger.info("No perspective boundary — returning smart-cropped image")
        return orig

    def auto_crop_straighten_paths(self, image_paths):
        results = []
        for path in image_paths:
            img = cv2.imread(str(path))
            if img is None:
                logger.warning(f"Could not load: {path}")
                continue
            results.append(self.auto_crop_straighten(self._ensure_bgr(img)))
        return results

    def _four_point_transform(self, image, pts):
        rect = self._order_points(pts.astype("float32"))
        tl, tr, br, bl = rect
        w = int(max(np.linalg.norm(br-bl), np.linalg.norm(tr-tl)))
        h = int(max(np.linalg.norm(tr-br), np.linalg.norm(tl-bl)))
        if w <= 0 or h <= 0:
            return image
        dst = np.array([[0,0],[w-1,0],[w-1,h-1],[0,h-1]], dtype="float32")
        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(image, M, (w, h))

    def _order_points(self, pts):
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        return rect
