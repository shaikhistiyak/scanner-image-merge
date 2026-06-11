import cv2
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)


class MergeService:

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
        Seamlessly stitch scanned document sections.

        Strategy
        --------
        1. Smart-crop each scan to remove scanner borders.
        2. Detect whether sections are arranged horizontally or vertically
           (compare aspect ratios and edge content).
        3. Find the overlap zone using normalized cross-correlation.
        4. Blend images at the seam with a gradient.

        This is a TRANSLATION-ONLY stitch — no rotation, no perspective warp.
        That is exactly correct for flat document scanning.
        """
        images = self._load_images(image_paths)
        logger.info(f"merge_stitch: {len(images)} images")

        # Step 1: smart crop each image
        cropped = [self.smart_crop(img) for img in images]

        # Step 2: detect direction (horizontal vs vertical)
        direction = self._detect_direction(cropped)
        logger.info(f"Detected stitch direction: {direction}")

        # Step 3: stitch pairs in detected direction
        result = cropped[0]
        for i in range(1, len(cropped)):
            if direction == "horizontal":
                result = self._stitch_pair_h(result, cropped[i])
            else:
                result = self._stitch_pair_v(result, cropped[i])

        return result

    def _detect_direction(self, images):
        """
        Decide if images are arranged left→right (horizontal) or top→bottom (vertical).
        Compares similarity of image RIGHT edge vs BOTTOM edge with next image's LEFT/TOP.
        """
        if len(images) < 2:
            return "horizontal"

        img1, img2 = images[0], images[1]
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY).astype(np.float32)

        strip_size = 100
        mid_y = slice(h1 // 4, 3 * h1 // 4)
        mid_x = slice(w1 // 4, 3 * w1 // 4)

        # Compare right edge of img1 vs left edge of img2
        r1 = g1[mid_y, -strip_size:]
        l2 = g2[mid_y, :strip_size]
        h_score = self._ncc(r1, l2) if r1.shape == l2.shape else 0.0

        # Compare bottom edge of img1 vs top edge of img2
        b1 = g1[-strip_size:, mid_x]
        t2 = g2[:strip_size, mid_x]
        v_score = self._ncc(b1, t2) if b1.shape == t2.shape else 0.0

        logger.info(f"Direction NCC — horizontal: {h_score:.3f}, vertical: {v_score:.3f}")
        return "vertical" if v_score > h_score else "horizontal"

    def _ncc(self, a, b):
        """Normalized cross-correlation between two arrays."""
        an = (a - a.mean()) / (a.std() + 1e-6)
        bn = (b - b.mean()) / (b.std() + 1e-6)
        return float((an * bn).mean())

    def _find_overlap_h(self, img1, img2, min_pct=0.02, max_pct=0.6, step=4):
        """Find best horizontal overlap in pixels using NCC on vertical strips."""
        g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        y_start = min(h1, h2) // 4
        y_end   = 3 * min(h1, h2) // 4
        min_ov  = max(5, int(min(w1, w2) * min_pct))
        max_ov  = int(min(w1, w2) * max_pct)

        best_score, best_ov = -999, 0
        for ov in range(min_ov, max_ov, step):
            s1 = g1[y_start:y_end, w1-ov:w1]
            s2 = g2[y_start:y_end, :ov]
            sc = self._ncc(s1, s2)
            if sc > best_score:
                best_score, best_ov = sc, ov

        logger.info(f"Horizontal overlap: {best_ov}px (NCC={best_score:.4f})")
        return best_ov

    def _find_overlap_v(self, img1, img2, min_pct=0.02, max_pct=0.6, step=4):
        """Find best vertical overlap in pixels using NCC on horizontal strips."""
        g1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        x_start = min(w1, w2) // 4
        x_end   = 3 * min(w1, w2) // 4
        min_ov  = max(5, int(min(h1, h2) * min_pct))
        max_ov  = int(min(h1, h2) * max_pct)

        best_score, best_ov = -999, 0
        for ov in range(min_ov, max_ov, step):
            s1 = g1[h1-ov:h1, x_start:x_end]
            s2 = g2[:ov, x_start:x_end]
            sc = self._ncc(s1, s2)
            if sc > best_score:
                best_score, best_ov = sc, ov

        logger.info(f"Vertical overlap: {best_ov}px (NCC={best_score:.4f})")
        return best_ov

    def _stitch_pair_h(self, img1, img2):
        """Stitch two images horizontally with gradient blend at seam."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        overlap = self._find_overlap_h(img1, img2)

        out_h = max(h1, h2)
        out_w = w1 + w2 - overlap
        result = np.full((out_h, out_w, 3), 255, dtype=np.uint8)

        # Place img1
        result[:h1, :w1] = img1

        # Gradient blend at overlap zone
        if overlap > 0:
            blend_h = min(h1, h2)
            alpha = np.linspace(1.0, 0.0, overlap, dtype=np.float32)[np.newaxis, :, np.newaxis]
            z1 = img1[:blend_h, w1-overlap:w1].astype(np.float32)
            z2 = img2[:blend_h, :overlap].astype(np.float32)
            result[:blend_h, w1-overlap:w1] = (z1 * alpha + z2 * (1.0 - alpha)).astype(np.uint8)

        # Place non-overlapping part of img2
        result[:h2, w1:] = img2[:h2, overlap:]
        return result

    def _stitch_pair_v(self, img1, img2):
        """Stitch two images vertically with gradient blend at seam."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        overlap = self._find_overlap_v(img1, img2)

        out_w = max(w1, w2)
        out_h = h1 + h2 - overlap
        result = np.full((out_h, out_w, 3), 255, dtype=np.uint8)

        result[:h1, :w1] = img1

        if overlap > 0:
            blend_w = min(w1, w2)
            alpha = np.linspace(1.0, 0.0, overlap, dtype=np.float32)[:, np.newaxis, np.newaxis]
            z1 = img1[h1-overlap:h1, :blend_w].astype(np.float32)
            z2 = img2[:overlap, :blend_w].astype(np.float32)
            result[h1-overlap:h1, :blend_w] = (z1 * alpha + z2 * (1.0 - alpha)).astype(np.uint8)

        result[h1:, :w2] = img2[overlap:, :]
        return result

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
