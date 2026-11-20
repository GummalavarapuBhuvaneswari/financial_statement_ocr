"""Image cleanup before OCR."""

from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
def preprocess_for_ocr(image_path: Path, save_debug_to: Path | None = None) -> np.ndarray:
    bgr = cv2.imread(str(image_path))
    if bgr is None:
        raise FileNotFoundError(f"Could not read image: {image_path}")

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cleaned = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(cleaned)

    if save_debug_to is not None:
        save_debug_to.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(save_debug_to), enhanced)

    return enhanced
