
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytesseract


def locate_tesseract() -> str:
    """Find tesseract.exe in PATH or the usual Windows install folders."""
    env = os.environ.get("TESSERACT_CMD")
    if env and Path(env).exists():
        return env

    which = shutil.which("tesseract")
    if which:
        return which

    candidates = [
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    raise FileNotFoundError(
        "Tesseract OCR was not found. Install it locally and/or set TESSERACT_CMD "
        "to the full path of tesseract.exe."
    )


def configure_tesseract() -> str:
    cmd = locate_tesseract()
    pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


@dataclass
class OcrWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    @property
    def cx(self) -> int:
        return self.left + self.width // 2


@dataclass
class OcrLine:
    page: int
    top: int
    words: list[OcrWord]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def left(self) -> int:
        return min(w.left for w in self.words) if self.words else 0

    @property
    def avg_conf(self) -> float:
        if not self.words:
            return 0.0
        return sum(w.conf for w in self.words) / len(self.words)

    def bbox(self) -> dict:
        if not self.words:
            return {"left": 0, "top": 0, "right": 0, "bottom": 0}
        return {
            "left": min(w.left for w in self.words),
            "top": min(w.top for w in self.words),
            "right": max(w.right for w in self.words),
            "bottom": max(w.bottom for w in self.words),
        }


def run_ocr(image, page_number: int, psm: int = 6) -> tuple[str, list[OcrLine]]:
    """OCR one preprocessed page. Returns (full_text, structured lines with boxes)."""
    configure_tesseract()
    config = f"--oem 3 --psm {psm}"

    full_text = pytesseract.image_to_string(image, config=config, lang="eng")
    data = pytesseract.image_to_data(
        image, config=config, lang="eng", output_type=pytesseract.Output.DICT
    )

    buckets: dict[tuple[int, int, int], list[OcrWord]] = {}
    n = len(data["text"])
    for i in range(n):
        txt = str(data["text"][i]).strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        # tesseract uses -1 for "no confidence" on some structural tokens
        if conf < 0:
            conf = 0.0

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        buckets.setdefault(key, []).append(
            OcrWord(
                text=txt,
                left=int(data["left"][i]),
                top=int(data["top"][i]),
                width=int(data["width"][i]),
                height=int(data["height"][i]),
                conf=conf,
            )
        )

    lines: list[OcrLine] = []
    for words in buckets.values():
        words = sorted(words, key=lambda w: w.left)
        top = min(w.top for w in words)
        lines.append(OcrLine(page=page_number, top=top, words=words))

    lines.sort(key=lambda ln: ln.top)
    return full_text, lines
