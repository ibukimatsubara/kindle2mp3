"""OCR using ndlocr-lite (layout detection + text recognition in one pass)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

# LINE TYPEs to include in output text
_BODY_TYPES = {"本文", "タイトル本文"}


@dataclass(slots=True)
class NdlocrPageResult:
    image_path: Path
    xml_path: Path
    text_path: Path
    text: str
    line_count: int


@dataclass(slots=True)
class NdlocrRunResult:
    session_id: str
    provider: str
    raw_dir: Path
    text_dir: Path
    pages: list[NdlocrPageResult]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "raw_dir": str(self.raw_dir),
            "text_dir": str(self.text_dir),
            "page_count": len(self.pages),
        }


def _build_args(*, source_dir: Path, output_dir: Path, device: str = "cpu") -> Namespace:
    """Build an argparse.Namespace matching ndlocr-lite's expected arguments."""
    import ocr as _ndlocr_module

    base_dir = Path(_ndlocr_module.__file__).resolve().parent
    model_dir = base_dir / "model"
    config_dir = base_dir / "config"

    return Namespace(
        sourcedir=str(source_dir),
        sourceimg=None,
        output=str(output_dir),
        viz=False,
        det_weights=str(model_dir / "deim-s-1024x1024.onnx"),
        det_classes=str(config_dir / "ndl.yaml"),
        det_score_threshold=0.2,
        det_conf_threshold=0.25,
        det_iou_threshold=0.2,
        simple_mode=False,
        rec_weights30=str(model_dir / "parseq-ndl-16x256-30-tiny-192epoch-tegaki3.onnx"),
        rec_weights50=str(model_dir / "parseq-ndl-16x384-50-tiny-146epoch-tegaki2.onnx"),
        rec_weights=str(model_dir / "parseq-ndl-16x768-100-tiny-165epoch-tegaki2.onnx"),
        rec_classes=str(config_dir / "NDLmoji.yaml"),
        device=device,
    )


def parse_xml_body_text(xml_path: Path) -> tuple[str, int]:
    """Parse ndlocr-lite XML output, returning body text and line count.

    Filters to LINE elements with TYPE in _BODY_TYPES, sorted by ORDER.
    Excludes lines that overlap with 柱 (pillar/header) BLOCK regions.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Collect 柱 (pillar) block regions to exclude header text like "Kindle"
    pillar_boxes: list[tuple[int, int, int, int]] = []
    for block in root.iter("BLOCK"):
        if block.get("TYPE") == "柱":
            x = int(block.get("X", 0))
            y = int(block.get("Y", 0))
            w = int(block.get("WIDTH", 0))
            h = int(block.get("HEIGHT", 0))
            pillar_boxes.append((x, y, x + w, y + h))

    lines: list[tuple[int, str]] = []
    for line_elem in root.iter("LINE"):
        line_type = line_elem.get("TYPE", "")
        if line_type not in _BODY_TYPES:
            continue

        # Check if this line overlaps with a pillar region
        lx = int(line_elem.get("X", 0))
        ly = int(line_elem.get("Y", 0))
        lw = int(line_elem.get("WIDTH", 0))
        lh = int(line_elem.get("HEIGHT", 0))
        if _overlaps_any(lx, ly, lx + lw, ly + lh, pillar_boxes):
            continue

        order = int(line_elem.get("ORDER", 0))
        text = line_elem.get("STRING", "").strip()
        if text:
            lines.append((order, text))

    lines.sort(key=lambda x: x[0])
    body_text = "\n".join(text for _, text in lines)
    return body_text, len(lines)


def _overlaps_any(
    x1: int, y1: int, x2: int, y2: int,
    boxes: list[tuple[int, int, int, int]],
) -> bool:
    """Check if a rectangle overlaps with any of the given boxes."""
    for bx1, by1, bx2, by2 in boxes:
        if x1 < bx2 and x2 > bx1 and y1 < by2 and y2 > by1:
            return True
    return False


class NdlocrRunner:
    def __init__(self, *, device: str = "cpu") -> None:
        self.device = device

    def run_for_session(
        self,
        *,
        session_id: str,
        image_paths: list[Path],
        raw_dir: str | Path,
        text_dir: str | Path,
    ) -> NdlocrRunResult:
        raw_dir_path = Path(raw_dir)
        text_dir_path = Path(text_dir)
        raw_dir_path.mkdir(parents=True, exist_ok=True)
        text_dir_path.mkdir(parents=True, exist_ok=True)

        if not image_paths:
            return NdlocrRunResult(
                session_id=session_id,
                provider="ndlocr-lite",
                raw_dir=raw_dir_path,
                text_dir=text_dir_path,
                pages=[],
            )

        # Determine source directory from image paths
        source_dir = image_paths[0].parent
        args = _build_args(
            source_dir=source_dir,
            output_dir=raw_dir_path,
            device=self.device,
        )

        # Run ndlocr-lite
        from ocr import process
        print(f"  ndlocr-lite: processing {len(image_paths)} page(s)...", flush=True)
        process(args)

        # Parse XML outputs and write filtered text
        sorted_paths = sorted(image_paths)
        pages: list[NdlocrPageResult] = []

        for image_path in sorted_paths:
            stem = image_path.stem
            xml_path = raw_dir_path / f"{stem}.xml"
            text_path = text_dir_path / f"{stem}.txt"

            if xml_path.exists():
                body_text, line_count = parse_xml_body_text(xml_path)
            else:
                body_text, line_count = "", 0

            text_path.write_text(
                body_text + ("\n" if body_text else ""),
                encoding="utf-8",
            )

            pages.append(NdlocrPageResult(
                image_path=image_path,
                xml_path=xml_path,
                text_path=text_path,
                text=body_text,
                line_count=line_count,
            ))

        return NdlocrRunResult(
            session_id=session_id,
            provider="ndlocr-lite",
            raw_dir=raw_dir_path,
            text_dir=text_dir_path,
            pages=pages,
        )
