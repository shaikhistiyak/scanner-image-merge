"""
StitchingEngine  v2
===================
Professional document-stitching pipeline.

Pipeline:
  1. NCC overlap search   — find how much the images overlap
  2. Phase correlation    — sub-pixel precise vertical alignment
  3. Exposure compensation
  4. Optimal seam (DP)   — seam avoids text and edges
  5. Multi-band Laplacian pyramid blending — invisible seam

Why not SIFT/ORB for documents?
  Newspaper/document text looks the same everywhere.
  Feature matchers get confused and produce wrong rotations.
  NCC + phase correlation is the correct approach for flat printed documents.
  This is the same approach used in professional scanner software.
"""

import cv2
import numpy as np
from utils.logger import get_logger

logger = get_logger(__name__)


class StitchingEngine:

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def stitch(self, images: list) -> np.ndarray:
        """
        Stitch a list of numpy BGR images into one seamless document.
        Pass images in reading order (left→right or top→bottom).
        """
        if len(images) == 0:
            raise ValueError("No images provided")
        if len(images) == 1:
            return images[0]

        result = images[0]
        for i in range(1, len(images)):
            logger.info(f"--- Stitching pair {i}/{len(images)-1} ---")
            result = self._stitch_pair(result, images[i])

        return result

    # ──────────────────────────────────────────────────────────────────
    # Step 1  —  NCC overlap search
    # ──────────────────────────────────────────────────────────────────

    def _find_overlap(self, img1: np.ndarray, img2: np.ndarray,
                       axis: str = "horizontal"):
        """
        Brute-force NCC overlap search.
        axis='horizontal' → images placed left/right, search for overlap width.
        axis='vertical'   → images placed top/bottom, search for overlap height.

        Returns best overlap in pixels and its NCC score.
        """
        g1 = self._gray_norm(img1)
        g2 = self._gray_norm(img2)
        h1, w1 = g1.shape
        h2, w2 = g2.shape

        if axis == "horizontal":
            # Compare right strip of img1 with left strip of img2
            # Use middle 50% rows to avoid edge noise
            r0, r1 = min(h1, h2) // 4, 3 * min(h1, h2) // 4
            min_ov = 10
            max_ov = int(min(w1, w2) * 0.65)
            step   = max(1, (max_ov - min_ov) // 200)

            scores = []
            for ov in range(min_ov, max_ov, step):
                s1 = g1[r0:r1, w1 - ov:w1]
                s2 = g2[r0:r1, :ov]
                scores.append((self._ncc(s1, s2), ov))

        else:  # vertical
            c0, c1 = min(w1, w2) // 4, 3 * min(w1, w2) // 4
            min_ov = 10
            max_ov = int(min(h1, h2) * 0.65)
            step   = max(1, (max_ov - min_ov) // 200)

            scores = []
            for ov in range(min_ov, max_ov, step):
                s1 = g1[h1 - ov:h1, c0:c1]
                s2 = g2[:ov, c0:c1]
                scores.append((self._ncc(s1, s2), ov))

        if not scores:
            return 0, -1.0

        best_score, best_ov = max(scores, key=lambda x: x[0])
        logger.info(f"  Overlap ({axis}): {best_ov}px  NCC={best_score:.4f}")
        return best_ov, best_score

    # ──────────────────────────────────────────────────────────────────
    # Step 2  —  Phase correlation for precise dy (vertical offset)
    # ──────────────────────────────────────────────────────────────────

    def _refine_alignment(self, img1: np.ndarray, img2: np.ndarray,
                           overlap: int, axis: str = "horizontal"):
        """
        Use phase correlation on the overlap zone to find the exact
        vertical (or horizontal) misalignment between scans.
        Scanners sometimes feed paper slightly crooked.

        Returns (dy) for horizontal stitch, (dx) for vertical stitch.
        """
        g1 = self._gray_norm(img1)
        g2 = self._gray_norm(img2)

        if axis == "horizontal":
            h  = min(g1.shape[0], g2.shape[0])
            p1 = g1[:h, g1.shape[1] - overlap:g1.shape[1]]
            p2 = g2[:h, :overlap]
        else:
            w  = min(g1.shape[1], g2.shape[1])
            p1 = g1[g1.shape[0] - overlap:g1.shape[0], :w]
            p2 = g2[:overlap, :w]

        if p1.shape != p2.shape:
            min_h = min(p1.shape[0], p2.shape[0])
            min_w = min(p1.shape[1], p2.shape[1])
            p1, p2 = p1[:min_h, :min_w], p2[:min_h, :min_w]

        try:
            shift, _ = cv2.phaseCorrelate(p1.astype(np.float64),
                                           p2.astype(np.float64))
            offset = int(round(shift[1] if axis == "horizontal" else shift[0]))
            # Clamp: scanner misalignment should never be more than 2% of image
            max_offset = int(min(img1.shape[0], img1.shape[1]) * 0.02)
            offset = int(np.clip(offset, -max_offset, max_offset))
            logger.info(f"  Phase correlation offset: {offset}px")
            return offset
        except Exception as e:
            logger.warning(f"  Phase correlation failed: {e}")
            return 0

    # ──────────────────────────────────────────────────────────────────
    # Step 3  —  Direction detection
    # ──────────────────────────────────────────────────────────────────

    def _detect_direction(self, img1: np.ndarray, img2: np.ndarray) -> str:
        """
        Decide if img2 is to the RIGHT of img1 (horizontal)
        or BELOW img1 (vertical).
        """
        ov_h, sc_h = self._find_overlap(img1, img2, axis="horizontal")
        ov_v, sc_v = self._find_overlap(img1, img2, axis="vertical")

        direction = "vertical" if sc_v > sc_h * 1.1 else "horizontal"
        logger.info(f"  Direction: {direction}  "
                    f"(H NCC={sc_h:.3f}, V NCC={sc_v:.3f})")
        return direction

    # ──────────────────────────────────────────────────────────────────
    # Step 4  —  Exposure compensation
    # ──────────────────────────────────────────────────────────────────

    def _match_exposure(self, ref: np.ndarray, tgt: np.ndarray,
                         ref_patch_slice, tgt_patch_slice) -> np.ndarray:
        """
        Adjust brightness/colour of tgt so its overlap zone matches ref.
        Removes visible brightness seam caused by different scan passes.
        """
        p_ref = ref[ref_patch_slice].astype(np.float32)
        p_tgt = tgt[tgt_patch_slice].astype(np.float32)

        result = tgt.astype(np.float32)
        for c in range(3):
            mu_r = p_ref[:, :, c].mean()
            mu_t = p_tgt[:, :, c].mean()
            sd_r = p_ref[:, :, c].std() + 1e-6
            sd_t = p_tgt[:, :, c].std() + 1e-6

            gain   = np.clip(sd_r / sd_t, 0.7, 1.4)
            offset = np.clip(mu_r - gain * mu_t, -40, 40)
            result[:, :, c] = result[:, :, c] * gain + offset

        logger.info("  Exposure compensation applied")
        return np.clip(result, 0, 255).astype(np.uint8)

    # ──────────────────────────────────────────────────────────────────
    # Step 5  —  Optimal seam (dynamic programming)
    # ──────────────────────────────────────────────────────────────────

    def _find_seam(self, patch1: np.ndarray, patch2: np.ndarray,
                    seam_dir: str = "vertical") -> np.ndarray:
        """
        Find the minimum-energy seam through the overlap zone.

        seam_dir='vertical'   → seam column changes per row  (horizontal stitch)
        seam_dir='horizontal' → seam row changes per column  (vertical stitch)

        Energy = difference between the two images + gradient magnitude.
        The seam naturally avoids cutting through text strokes.
        """
        diff   = np.abs(patch1.astype(np.float32) - patch2.astype(np.float32))
        energy = diff.mean(axis=2)

        # Add gradient energy so seam avoids sharp edges (text strokes)
        g1_gray = cv2.cvtColor(patch1, cv2.COLOR_BGR2GRAY).astype(np.float32)
        grad    = cv2.Sobel(g1_gray, cv2.CV_32F, 1, 0, ksize=3) ** 2
        grad    = grad / (grad.max() + 1e-6) * energy.mean()
        energy += grad * 0.3

        if seam_dir == "horizontal":
            energy = energy.T   # transpose → DP always runs top→bottom

        h, w = energy.shape
        dp   = energy.copy()
        back = np.zeros_like(dp, dtype=np.int32)

        for i in range(1, h):
            for j in range(w):
                lo  = max(0, j - 1)
                hi  = min(w - 1, j + 1)
                idx = lo + int(np.argmin(dp[i - 1, lo:hi + 1]))
                back[i, j] = idx
                dp[i, j]  += dp[i - 1, idx]

        # Backtrack
        seam     = np.zeros(h, dtype=np.int32)
        seam[-1] = int(np.argmin(dp[-1]))
        for i in range(h - 2, -1, -1):
            seam[i] = back[i + 1, seam[i + 1]]

        if seam_dir == "horizontal":
            seam = seam   # caller transposes back

        return seam

    def _seam_to_mask(self, seam: np.ndarray, h: int, w: int,
                       feather: int = 25) -> np.ndarray:
        """
        Seam → float32 blend mask.
        0 = take from img1, 1 = take from img2.
        Feathered transition prevents any visible seam line.
        """
        mask = np.zeros((h, w), dtype=np.float32)
        for row in range(h):
            col = int(np.clip(seam[row], 0, w - 1))
            hi  = min(w,     col + feather)
            lo  = max(0,     col - feather)
            mask[row, hi:] = 1.0
            if hi > lo:
                mask[row, lo:hi] = np.linspace(0.0, 1.0, hi - lo)
        return mask

    # ──────────────────────────────────────────────────────────────────
    # Step 6  —  Multi-band Laplacian pyramid blending
    # ──────────────────────────────────────────────────────────────────

    def _laplacian_blend(self, img1: np.ndarray, img2: np.ndarray,
                          mask: np.ndarray, levels: int = 6) -> np.ndarray:
        """
        Laplacian pyramid multi-band blending.

        Each pyramid level uses a different blend width:
          - Low-frequency bands  → wide blend (smooth colour/brightness)
          - High-frequency bands → narrow blend (sharp edges at seam)

        Result: no visible seam, no colour fringing, no ghosting.
        This is the same algorithm used in professional panorama software.
        """
        f1 = img1.astype(np.float32)
        f2 = img2.astype(np.float32)
        m  = np.stack([mask, mask, mask], axis=2)

        gp1 = self._gpyr(f1, levels)
        gp2 = self._gpyr(f2, levels)
        gpm = self._gpyr(m,  levels)

        lp1 = self._lpyr(gp1)
        lp2 = self._lpyr(gp2)

        merged = []
        for la, lb, gm in zip(lp1, lp2, gpm):
            h_, w_ = la.shape[:2]
            gm_r   = cv2.resize(gm, (w_, h_))
            if gm_r.ndim == 2:
                gm_r = np.stack([gm_r] * 3, axis=2)
            merged.append(la * (1.0 - gm_r) + lb * gm_r)

        result = merged[-1]
        for lev in reversed(merged[:-1]):
            h_, w_ = lev.shape[:2]
            result  = cv2.resize(cv2.pyrUp(result), (w_, h_))
            result += lev

        return np.clip(result, 0, 255).astype(np.uint8)

    def _gpyr(self, img, levels):
        g = [img]
        for _ in range(levels - 1):
            g.append(cv2.pyrDown(g[-1]))
        return g

    def _lpyr(self, gp):
        lp = []
        for i in range(len(gp) - 1):
            up = cv2.resize(cv2.pyrUp(gp[i + 1]),
                             (gp[i].shape[1], gp[i].shape[0]))
            lp.append(gp[i].astype(np.float32) - up.astype(np.float32))
        lp.append(gp[-1].astype(np.float32))
        return lp

    # ──────────────────────────────────────────────────────────────────
    # Main pair stitch
    # ──────────────────────────────────────────────────────────────────

    def _stitch_pair(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        # Detect direction
        direction = self._detect_direction(img1, img2)

        if direction == "horizontal":
            return self._stitch_h(img1, img2)
        else:
            return self._stitch_v(img1, img2)

    def _stitch_h(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """Full pipeline for horizontal (left/right) stitch."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        # 1. Overlap
        ov_w, _ = self._find_overlap(img1, img2, axis="horizontal")

        # 2. Phase correlation → vertical offset correction
        dy = self._refine_alignment(img1, img2, ov_w, axis="horizontal")

        # 3. Canvas geometry
        x1, y1 = 0, max(0, dy)
        x2, y2 = w1 - ov_w, max(0, -dy)

        out_w = x2 + w2
        out_h = max(y1 + h1, y2 + h2)

        # Overlap region in canvas coordinates
        ov_x  = x2
        ov_y  = max(y1, y2)
        ov_h  = min(y1 + h1, y2 + h2) - ov_y

        # 4. Exposure compensation on overlap zone
        if ov_h > 0 and ov_w > 0:
            img1_ov_y = ov_y - y1
            img2_ov_y = ov_y - y2
            ref_sl = (slice(img1_ov_y, img1_ov_y + ov_h), slice(w1 - ov_w, w1))
            tgt_sl = (slice(img2_ov_y, img2_ov_y + ov_h), slice(0, ov_w))
            img2   = self._match_exposure(img1, img2, ref_sl, tgt_sl)

        # 5. Build canvas
        canvas = np.full((out_h, out_w, 3), 255, dtype=np.uint8)
        canvas[y1:y1 + h1, x1:x1 + w1] = img1
        canvas[y2:y2 + h2, x2:x2 + w2] = img2   # will be blended below

        if ov_h < 10 or ov_w < 10:
            logger.info("  Minimal overlap — simple placement")
            return canvas

        # 6. Optimal seam
        img1_ov_y = ov_y - y1
        img2_ov_y = ov_y - y2
        p1 = img1[img1_ov_y:img1_ov_y + ov_h, w1 - ov_w:w1]
        p2 = img2[img2_ov_y:img2_ov_y + ov_h,        0:ov_w]
        seam = self._find_seam(p1, p2, seam_dir="vertical")
        mask = self._seam_to_mask(seam, ov_h, ov_w, feather=30)

        # 7. Multi-band blend
        blended = self._laplacian_blend(p1, p2, mask, levels=6)
        canvas[ov_y:ov_y + ov_h, ov_x:ov_x + ov_w] = blended

        logger.info(
            f"  Horizontal stitch: {w1}x{h1} + {w2}x{h2} → {out_w}x{out_h}  "
            f"overlap={ov_w}x{ov_h}  dy={dy}"
        )
        return canvas

    def _stitch_v(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """Full pipeline for vertical (top/bottom) stitch."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        ov_h, _ = self._find_overlap(img1, img2, axis="vertical")
        dx      = self._refine_alignment(img1, img2, ov_h, axis="vertical")

        x1, y1 = max(0, dx), 0
        x2, y2 = max(0, -dx), h1 - ov_h

        out_h = y2 + h2
        out_w = max(x1 + w1, x2 + w2)

        ov_y  = y2
        ov_x  = max(x1, x2)
        ov_w  = min(x1 + w1, x2 + w2) - ov_x

        if ov_w > 0 and ov_h > 0:
            img1_ov_x = ov_x - x1
            img2_ov_x = ov_x - x2
            ref_sl = (slice(h1 - ov_h, h1), slice(img1_ov_x, img1_ov_x + ov_w))
            tgt_sl = (slice(0, ov_h),        slice(img2_ov_x, img2_ov_x + ov_w))
            img2   = self._match_exposure(img1, img2, ref_sl, tgt_sl)

        canvas = np.full((out_h, out_w, 3), 255, dtype=np.uint8)
        canvas[y1:y1 + h1, x1:x1 + w1] = img1
        canvas[y2:y2 + h2, x2:x2 + w2] = img2

        if ov_w < 10 or ov_h < 10:
            return canvas

        img1_ov_x = ov_x - x1
        img2_ov_x = ov_x - x2
        p1 = img1[h1 - ov_h:h1, img1_ov_x:img1_ov_x + ov_w]
        p2 = img2[        0:ov_h, img2_ov_x:img2_ov_x + ov_w]

        seam = self._find_seam(p1.T, p2.T, seam_dir="vertical")
        mask = self._seam_to_mask(seam, ov_w, ov_h, feather=30).T

        blended = self._laplacian_blend(p1, p2, mask, levels=6)
        canvas[ov_y:ov_y + ov_h, ov_x:ov_x + ov_w] = blended

        logger.info(
            f"  Vertical stitch: {w1}x{h1} + {w2}x{h2} → {out_w}x{out_h}  "
            f"overlap={ov_w}x{ov_h}  dx={dx}"
        )
        return canvas

    # ──────────────────────────────────────────────────────────────────
    # Utilities
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _gray_norm(img: np.ndarray) -> np.ndarray:
        """Convert to grayscale and normalise per-pixel contrast."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return (gray - gray.mean()) / (gray.std() + 1e-6)

    @staticmethod
    def _ncc(a: np.ndarray, b: np.ndarray) -> float:
        if a.size == 0 or b.size == 0:
            return -1.0
        an = (a - a.mean()) / (a.std() + 1e-6)
        bn = (b - b.mean()) / (b.std() + 1e-6)
        return float((an * bn).mean())
