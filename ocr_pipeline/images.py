"""PDF -> page images."""

from __future__ import annotations

from pathlib import Path

import pymupdf
from PIL import Image


def pdf_to_page_images(pdf_path: Path, out_dir: Path, dpi: int = 300) -> list[Path]:
    """Render each PDF page to a PNG. Returns the list of image paths in order."""
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(pdf_path))
    scale = dpi / 72.0
    matrix = pymupdf.Matrix(scale, scale)

    paths: list[Path] = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        path = out_dir / f"page_{i + 1}.png"
        pix.save(str(path))
        paths.append(path)
        print(f"  rendered page {i + 1}/{doc.page_count} -> {path.name} ({pix.width}x{pix.height})")

    doc.close()
    return paths


def load_pil(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")
