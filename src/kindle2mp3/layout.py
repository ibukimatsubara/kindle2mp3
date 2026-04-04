"""Layout detection using DocLayout-YOLO.

Detects document regions (text, title, figure, etc.) and identifies
which regions contain body text for OCR.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


BODY_LABELS = {"plain text", "title"}
SKIP_LABELS = {"abandon", "figure", "figure_caption", "Page-header", "Page-footer"}


@dataclass(slots=True)
class LayoutRegion:
    label: str
    score: float
    bbox: tuple[int, int, int, int]  # (x1, y1, x2, y2)

    @property
    def is_body(self) -> bool:
        return self.label in BODY_LABELS

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "score": self.score,
            "bbox": list(self.bbox),
            "is_body": self.is_body,
        }


@dataclass(slots=True)
class PageLayoutResult:
    image_path: Path
    regions: list[LayoutRegion]
    layout_path: Path

    @property
    def body_regions(self) -> list[LayoutRegion]:
        return [r for r in self.regions if r.is_body]

    def to_dict(self) -> dict:
        return {
            "image_path": str(self.image_path),
            "regions": [r.to_dict() for r in self.regions],
            "body_region_count": len(self.body_regions),
        }


@dataclass(slots=True)
class LayoutRunResult:
    session_id: str
    pages: list[PageLayoutResult]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "page_count": len(self.pages),
            "total_body_regions": sum(len(p.body_regions) for p in self.pages),
        }


class DocLayoutDetector:
    def __init__(self, *, conf: float = 0.15) -> None:
        self.conf = conf
        self._model = None

    def _get_model(self):
        if self._model is None:
            from doclayout_yolo import YOLOv10
            from huggingface_hub import hf_hub_download

            filepath = hf_hub_download(
                repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
                filename="doclayout_yolo_docstructbench_imgsz1024.pt",
            )
            self._model = YOLOv10(filepath)
        return self._model

    def detect(self, image_path: str | Path) -> list[LayoutRegion]:
        model = self._get_model()
        results = model.predict(str(image_path), imgsz=1024, conf=self.conf)
        regions: list[LayoutRegion] = []
        for result in results:
            for bbox in result.boxes:
                xyxy = bbox.xyxy[0].tolist()
                cls_id = int(bbox.cls[0])
                score = float(bbox.conf[0])
                label = result.names[cls_id]
                regions.append(LayoutRegion(
                    label=label,
                    score=score,
                    bbox=(int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])),
                ))
        regions.sort(key=lambda r: (r.bbox[1], r.bbox[0]))
        return regions

    def run_for_session(
        self,
        *,
        session_id: str,
        image_paths: list[Path],
        layout_dir: str | Path,
    ) -> LayoutRunResult:
        layout_dir_path = Path(layout_dir)
        layout_dir_path.mkdir(parents=True, exist_ok=True)

        pages: list[PageLayoutResult] = []
        for image_path in sorted(image_paths):
            regions = self.detect(image_path)
            layout_path = layout_dir_path / f"{image_path.stem}.json"
            payload = {
                "image_path": str(image_path),
                "regions": [r.to_dict() for r in regions],
            }
            layout_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            pages.append(PageLayoutResult(
                image_path=image_path,
                regions=regions,
                layout_path=layout_path,
            ))

        return LayoutRunResult(session_id=session_id, pages=pages)


def load_layout(path: str | Path) -> list[LayoutRegion]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        LayoutRegion(
            label=r["label"],
            score=r["score"],
            bbox=tuple(r["bbox"]),
        )
        for r in data.get("regions", [])
    ]
