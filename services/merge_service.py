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
            raise ValueError(f"Failed to load: {', '.join(errors)}")
        if len(images) < 2:
            raise ValueError("At least two valid images are required")
        return images

    # ------------------------------------------------------------------
    # Basic merges (kept from v1)
    # ------------------------------------------------------------------

    def merge_vertical(self, image_paths):
        images = self._load_images(image_paths)
        max_width = max(img.shape[1] for img in images)
        resized = []
        for img in images:
            h, w = img.shape[:2]
            new_h = max(1, int(h * max_width / w))
            resized.append(cv2.resize(img, (max_width, new_h)))
        return np.vstack(resized)

    def merge_horizontal(self, image_paths):
        images = self._load_images(image_paths)
        max_height = max(img.shape[0] for img in images)
        resized = []
        for img in images:
            h, w = img.shape[:2]
            new_w = max(1, int(w * max_height / h))
            resized.append(cv2.resize(img, (new_w, max_height)))
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
                diff = max_w - r.shape[1]
                r = cv2.copyMakeBorder(r, 0, 0, 0, diff,
                                       cv2.BORDER_CONSTANT, value=(255, 255, 255))
            padded.append(r)
        return np.vstack(padded)

    # ------------------------------------------------------------------
    # ✨ SMART STITCH — seamless, works for ANY document type
    # ------------------------------------------------------------------

    def merge_stitch(self, image_paths):
        """
        Seamlessly stitch multiple scans of the same document.
        Uses OpenCV Stitcher_SCANS mode (optimised for flat documents).
        Falls back to feature-based overlap blending if stitcher fails.
        """
        images = self._load_images(image_paths)
        logger.info(f"Smart stitch: {len(images)} images")

        # --- Try OpenCV Stitcher (best quality) ---
        try:
            stitcher = cv2.Stitcher.create(cv2.Stitcher_SCANS)
            status, result = stitcher.stitch(images)
            if status == cv2.Stitcher_OK:
                logger.info("OpenCV Stitcher succeeded")
                return self._trim_black_border(result)
        except Exception as e:
            logger.warning(f"OpenCV Stitcher error: {e}")

        # --- Fallback: feature-based pairwise blending ---
        logger.info("Falling back to feature-based blend")
        result = images[0]
        for i in range(1, len(images)):
            result = self._blend_pair(result, images[i])
        return self._trim_black_border(result)

    def _blend_pair(self, img1, img2):
        """
        Blend two images using ORB feature matching + homography.
        Falls back to simple horizontal stack if features can't be matched.
        """
        orb = cv2.ORB_create(5000)
        kp1, des1 = orb.detectAndCompute(img1, None)
        kp2, des2 = orb.detectAndCompute(img2, None)

        if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
            logger.warning("Not enough features - using simple hstack fallback")
            return self._simple_hstack(img1, img2)

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)

        if len(matches) < 4:
            logger.warning("Not enough matches - using simple hstack fallback")
            return self._simple_hstack(img1, img2)

        good = matches[:min(100, len(matches))]
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(dst_pts, src_pts, cv2.RANSAC, 5.0)

        if H is None:
            return self._simple_hstack(img1, img2)

        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        corners_img1 = np.float32([[0, 0], [w1, 0], [w1, h1], [0, h1]]).reshape(-1, 1, 2)
        corners_img2 = np.float32([[0, 0], [w2, 0], [w2, h2], [0, h2]]).reshape(-1, 1, 2)
        warped_corners_img2 = cv2.perspectiveTransform(corners_img2, H)
        all_corners = np.concatenate((corners_img1, warped_corners_img2), axis=0)

        x_min, y_min = np.int32(all_corners.min(axis=0).ravel() - 0.5)
        x_max, y_max = np.int32(all_corners.max(axis=0).ravel() + 0.5)

        translate_x = -x_min if x_min < 0 else 0
        translate_y = -y_min if y_min < 0 else 0
        translation = np.array(
            [[1, 0, translate_x], [0, 1, translate_y], [0, 0, 1]],
            dtype=np.float64,
        )

        output_width = int(x_max - x_min)
        output_height = int(y_max - y_min)
        if output_width <= 0 or output_height <= 0:
            return self._simple_hstack(img1, img2)

        warped = cv2.warpPerspective(img2, translation @ H, (output_width, output_height))
        result = warped.copy()

        x1 = translate_x
        y1 = translate_y
        roi = result[y1:y1 + h1, x1:x1 + w1]
        existing_mask = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) > 0
        overlap = existing_mask

        roi[~existing_mask] = img1[~existing_mask]
        if np.any(overlap):
            roi[overlap] = cv2.addWeighted(roi[overlap], 0.5, img1[overlap], 0.5, 0)

        result[y1:y1 + h1, x1:x1 + w1] = roi
        return result

    def _simple_hstack(self, img1, img2):
        max_h = max(img1.shape[0], img2.shape[0])
        def pad_height(img):
            h, w = img.shape[:2]
            if h < max_h:
                img = cv2.copyMakeBorder(img, 0, max_h - h, 0, 0,
                                         cv2.BORDER_CONSTANT, value=(255, 255, 255))
            return img
        return np.hstack([pad_height(img1), pad_height(img2)])

    def _trim_black_border(self, image):
        """Remove black borders that appear after stitching/warping."""
        if image is None:
            return image
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return image
        x, y, w, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
        return image[y:y + h, x:x + w]

    # ------------------------------------------------------------------
    # ✨ AUTO CROP & STRAIGHTEN — works for any document on any background
    # ------------------------------------------------------------------

    def auto_crop_straighten(self, image):
        """
        Detect document boundary in the image and apply perspective correction.
        Works for A4 papers, certificates, books, newspapers on any background.
        Returns the corrected image, or the original if no document is detected.
        """
        orig = image.copy()
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Try multiple edge thresholds for robustness
        for thresh_low, thresh_high in [(50, 150), (30, 100), (75, 200)]:
            edged = cv2.Canny(blurred, thresh_low, thresh_high)
            edged = cv2.dilate(edged, None, iterations=1)

            contours, _ = cv2.findContours(
                edged, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
            )
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:10]

            for c in contours:
                peri = cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, 0.02 * peri, True)
                if len(approx) == 4:
                    logger.info("Document boundary found - applying perspective fix")
                    return self._four_point_transform(orig, approx.reshape(4, 2))

        logger.warning("No document boundary found - returning original")
        return orig

    def auto_crop_straighten_paths(self, image_paths):
        """
        Apply auto crop & straighten to each image path.
        Returns a list of corrected numpy images.
        """
        images = self._load_images(image_paths)
        return [self.auto_crop_straighten(img) for img in images]

    def _four_point_transform(self, image, pts):
        rect = self._order_points(pts)
        tl, tr, br, bl = rect

        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = max(int(width_a), int(width_b))

        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = max(int(height_a), int(height_b))

        if max_width <= 0 or max_height <= 0:
            return image

        dst = np.array([
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ], dtype="float32")

        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpPerspective(image, M, (max_width, max_height))

    def _order_points(self, pts):
        """Order: top-left, top-right, bottom-right, bottom-left."""
        pts = pts.astype("float32")
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left
        rect[2] = pts[np.argmax(s)]   # bottom-right
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right
        rect[3] = pts[np.argmax(diff)]  # bottom-left
        return rect
