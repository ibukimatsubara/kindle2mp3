"""OCR using PaddleOCR, scoped to layout-detected body regions."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path

from PIL import Image

from kindle2mp3.layout import LayoutRegion, load_layout


@dataclass(slots=True)
class OcrRegionResult:
    region_index: int
    label: str
    bbox: tuple[int, int, int, int]
    lines: list[dict]
    text: str


@dataclass(slots=True)
class OcrPageResult:
    image_path: Path
    raw_path: Path
    text_path: Path
    text: str
    regions: list[OcrRegionResult]


@dataclass(slots=True)
class OcrRunResult:
    session_id: str
    provider: str
    language: str
    raw_dir: Path
    text_dir: Path
    pages: list[OcrPageResult]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "language": self.language,
            "raw_dir": str(self.raw_dir),
            "text_dir": str(self.text_dir),
            "page_count": len(self.pages),
        }


class PaddleOcrRunner:
    def __init__(self, *, lang: str = "japan", use_angle_cls: bool = True) -> None:
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self._ocr = None

    def run_for_session(
        self,
        *,
        session_id: str,
        image_paths: list[Path],
        layout_dir: str | Path,
        raw_dir: str | Path,
        text_dir: str | Path,
        orientation: str = "horizontal",
    ) -> OcrRunResult:
        raw_dir_path = Path(raw_dir)
        text_dir_path = Path(text_dir)
        layout_dir_path = Path(layout_dir)
        raw_dir_path.mkdir(parents=True, exist_ok=True)
        text_dir_path.mkdir(parents=True, exist_ok=True)

        sorted_paths = sorted(image_paths)
        total = len(sorted_paths)

        # Prepare per-page inputs
        page_inputs: list[tuple[Path, list[LayoutRegion]]] = []
        for image_path in sorted_paths:
            layout_path = layout_dir_path / f"{image_path.stem}.json"
            if layout_path.exists():
                body_regions = [r for r in load_layout(layout_path) if r.is_body]
            else:
                body_regions = []
            page_inputs.append((image_path, body_regions))

        # Process pages in parallel
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _process(args: tuple[Path, list[LayoutRegion]]) -> tuple[Path, OcrPageResult]:
            img_path, regions = args
            result = self._run_single_page(
                img_path, regions, raw_dir_path, text_dir_path,
                orientation=orientation,
            )
            return img_path, result

        max_workers = min(4, total)
        results_map: dict[str, OcrPageResult] = {}
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_process, inp): inp[0] for inp in page_inputs}
            for future in as_completed(futures):
                img_path, result = future.result()
                results_map[img_path.name] = result
                completed += 1
                print(f"  ocr page {completed}/{total}", flush=True)

        # Collect in order
        pages: list[OcrPageResult] = [results_map[p.name] for p in sorted_paths]

        return OcrRunResult(
            session_id=session_id,
            provider="paddleocr",
            language=self.lang,
            raw_dir=raw_dir_path,
            text_dir=text_dir_path,
            pages=pages,
        )

    def _run_single_page(
        self,
        image_path: Path,
        body_regions: list[LayoutRegion],
        raw_dir: Path,
        text_dir: Path,
        orientation: str = "horizontal",
    ) -> OcrPageResult:
        region_results: list[OcrRegionResult] = []
        sort_key = _line_sort_key(orientation)

        if not body_regions:
            lines = self._ocr_image(image_path)
            lines.sort(key=sort_key)
            text = "\n".join(line["text"] for line in lines).strip()
            region_results.append(OcrRegionResult(
                region_index=0, label="full_page", bbox=(0, 0, 0, 0),
                lines=lines, text=text,
            ))
        else:
            masked = _mask_non_body(image_path, body_regions)
            all_lines = self._ocr_pil_image(masked)

            assigned = _assign_lines_to_regions(all_lines, body_regions)
            for i, region in enumerate(body_regions):
                region_lines = assigned.get(i, [])
                region_lines.sort(key=sort_key)
                text = "\n".join(line["text"] for line in region_lines).strip()
                region_results.append(OcrRegionResult(
                    region_index=i, label=region.label,
                    bbox=region.bbox, lines=region_lines, text=text,
                ))

        # Sort regions in reading order
        if orientation == "vertical":
            region_results.sort(key=lambda r: (-r.bbox[2], r.bbox[1]))  # right-to-left, top-to-bottom
        else:
            region_results.sort(key=lambda r: (r.bbox[1], r.bbox[0]))  # top-to-bottom, left-to-right

        page_text = "\n".join(r.text for r in region_results if r.text).strip()

        stem = image_path.stem
        raw_path = raw_dir / f"{stem}.json"
        text_path = text_dir / f"{stem}.txt"

        raw_payload = {
            "image_path": str(image_path),
            "provider": "paddleocr",
            "language": self.lang,
            "regions": [
                {
                    "region_index": r.region_index,
                    "label": r.label,
                    "bbox": list(r.bbox),
                    "lines": r.lines,
                }
                for r in region_results
            ],
        }
        raw_path.write_text(
            json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        text_path.write_text(page_text + ("\n" if page_text else ""), encoding="utf-8")

        return OcrPageResult(
            image_path=image_path,
            raw_path=raw_path,
            text_path=text_path,
            text=page_text,
            regions=region_results,
        )

    def _ocr_image(self, image_path: Path) -> list[dict]:
        raw_result = self._get_engine().predict(
            str(image_path),
            use_textline_orientation=self.use_angle_cls,
        )
        return self._extract_lines(raw_result)

    def _ocr_pil_image(self, pil_image: Image.Image) -> list[dict]:
        import numpy as np
        rgb_image = pil_image.convert("RGB") if pil_image.mode != "RGB" else pil_image
        img_array = np.array(rgb_image)
        raw_result = self._get_engine().predict(
            img_array,
            use_textline_orientation=self.use_angle_cls,
        )
        return self._extract_lines(raw_result)

    def _get_engine(self):
        if self._ocr is None:
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                lang=self.lang,
                use_textline_orientation=self.use_angle_cls,
            )
        return self._ocr

    @staticmethod
    def _extract_lines(raw_result) -> list[dict]:
        payload = raw_result[0] if raw_result and isinstance(raw_result, list) else raw_result
        if payload is None:
            return []
        if hasattr(payload, "keys"):
            texts = list(payload.get("rec_texts", []))
            scores = list(payload.get("rec_scores", []))
            polys = list(payload.get("rec_polys", payload.get("dt_polys", [])))
            lines: list[dict] = []
            for index, text in enumerate(texts):
                text = str(text).strip()
                if not text:
                    continue
                score = float(scores[index]) if index < len(scores) else 0.0
                box = (
                    polys[index].tolist()
                    if index < len(polys) and hasattr(polys[index], "tolist")
                    else polys[index] if index < len(polys) else None
                )
                lines.append({"box": box, "text": text, "score": score})
            return lines

        lines: list[dict] = []
        for item in payload:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            box = item[0]
            text_info = item[1]
            if not isinstance(text_info, (list, tuple)) or len(text_info) < 2:
                continue
            text = str(text_info[0]).strip()
            score = float(text_info[1])
            if not text:
                continue
            lines.append({"box": box, "text": text, "score": score})
        return lines


MASK_PADDING = 20


def _mask_non_body(
    image_path: Path, body_regions: list[LayoutRegion],
) -> Image.Image:
    """White-out everything outside body regions (with padding)."""
    from PIL import ImageDraw as _ImageDraw

    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    mask = Image.new("L", img.size, 0)
    draw = _ImageDraw.Draw(mask)
    for region in body_regions:
        padded = (
            max(0, region.bbox[0] - MASK_PADDING),
            max(0, region.bbox[1] - MASK_PADDING),
            min(w, region.bbox[2] + MASK_PADDING),
            min(h, region.bbox[3] + MASK_PADDING),
        )
        draw.rectangle(padded, fill=255)
    white = Image.new("RGB", img.size, (255, 255, 255))
    return Image.composite(img, white, mask)


def _assign_lines_to_regions(
    lines: list[dict], regions: list[LayoutRegion],
) -> dict[int, list[dict]]:
    """Assign each OCR line to exactly one region (closest center distance)."""
    assigned: dict[int, list[dict]] = {i: [] for i in range(len(regions))}
    for line in lines:
        box = line.get("box")
        if not box or not isinstance(box[0], (list, tuple)):
            continue
        cx = sum(p[0] for p in box) / len(box)
        cy = sum(p[1] for p in box) / len(box)

        best_idx = -1
        best_dist = float("inf")
        for i, region in enumerate(regions):
            x1, y1, x2, y2 = region.bbox
            # distance from center to bbox (0 if inside)
            dx = max(x1 - cx, 0, cx - x2)
            dy = max(y1 - cy, 0, cy - y2)
            dist = dx * dx + dy * dy
            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0 and best_dist <= MASK_PADDING * MASK_PADDING * 2:
            assigned[best_idx].append(line)

    return assigned


def _line_sort_key(orientation: str):
    """Return a sort key function for OCR lines based on text orientation."""
    def _box_center(line: dict) -> tuple[float, float]:
        box = line.get("box")
        if not box or not isinstance(box[0], (list, tuple)):
            return (0.0, 0.0)
        cx = sum(p[0] for p in box) / len(box)
        cy = sum(p[1] for p in box) / len(box)
        return (cx, cy)

    if orientation == "vertical":
        # Right-to-left, top-to-bottom
        return lambda line: (-_box_center(line)[0], _box_center(line)[1])
    else:
        # Top-to-bottom, left-to-right
        return lambda line: (_box_center(line)[1], _box_center(line)[0])


def _line_center_in_bbox(line: dict, bbox: tuple[int, int, int, int]) -> bool:
    """Check if an OCR line's center falls inside a bbox (with padding)."""
    box = line.get("box")
    if not box:
        return False
    if isinstance(box[0], (list, tuple)):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
    else:
        return False
    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)
    return (
        bbox[0] - MASK_PADDING <= cx <= bbox[2] + MASK_PADDING
        and bbox[1] - MASK_PADDING <= cy <= bbox[3] + MASK_PADDING
    )
