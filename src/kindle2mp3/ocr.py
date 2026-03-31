from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(slots=True)
class OcrPageResult:
    image_path: Path
    raw_path: Path
    normalized_path: Path
    text: str


@dataclass(slots=True)
class OcrRunResult:
    session_id: str
    provider: str
    language: str
    raw_dir: Path
    normalized_dir: Path
    combined_path: Path
    pages: list[OcrPageResult]

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "language": self.language,
            "raw_dir": str(self.raw_dir),
            "normalized_dir": str(self.normalized_dir),
            "combined_path": str(self.combined_path),
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
        raw_dir: str | Path,
        normalized_dir: str | Path,
        combined_path: str | Path,
    ) -> OcrRunResult:
        raw_dir_path = Path(raw_dir)
        normalized_dir_path = Path(normalized_dir)
        combined_path_obj = Path(combined_path)
        raw_dir_path.mkdir(parents=True, exist_ok=True)
        normalized_dir_path.mkdir(parents=True, exist_ok=True)
        combined_path_obj.parent.mkdir(parents=True, exist_ok=True)

        pages: list[OcrPageResult] = []
        combined_texts: list[str] = []

        for image_path in sorted(image_paths):
            result = self._run_single_image(image_path, raw_dir_path, normalized_dir_path)
            pages.append(result)
            combined_texts.append(result.text)

        combined_text = "\n\n".join(text for text in combined_texts if text)
        combined_path_obj.write_text(combined_text + ("\n" if combined_text else ""), encoding="utf-8")

        return OcrRunResult(
            session_id=session_id,
            provider="paddleocr",
            language=self.lang,
            raw_dir=raw_dir_path,
            normalized_dir=normalized_dir_path,
            combined_path=combined_path_obj,
            pages=pages,
        )

    def _run_single_image(
        self,
        image_path: Path,
        raw_dir: Path,
        normalized_dir: Path,
    ) -> OcrPageResult:
        raw_result = self._get_engine().predict(
            str(image_path),
            use_textline_orientation=self.use_angle_cls,
        )
        lines = self._extract_lines(raw_result)
        text = "\n".join(line["text"] for line in lines).strip()

        stem = image_path.stem
        raw_path = raw_dir / f"{stem}.json"
        normalized_path = normalized_dir / f"{stem}.txt"

        raw_payload = {
            "image_path": str(image_path),
            "provider": "paddleocr",
            "language": self.lang,
            "use_textline_orientation": self.use_angle_cls,
            "lines": lines,
        }
        raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        normalized_path.write_text(text + ("\n" if text else ""), encoding="utf-8")

        return OcrPageResult(
            image_path=image_path,
            raw_path=raw_path,
            normalized_path=normalized_path,
            text=text,
        )

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
    def _extract_lines(raw_result) -> list[dict[str, object]]:
        payload = raw_result[0] if raw_result and isinstance(raw_result, list) else raw_result
        if payload is None:
            return []
        if hasattr(payload, "keys"):
            texts = list(payload.get("rec_texts", []))
            scores = list(payload.get("rec_scores", []))
            polys = list(payload.get("rec_polys", payload.get("dt_polys", [])))
            lines: list[dict[str, object]] = []
            for index, text in enumerate(texts):
                text = str(text).strip()
                if not text:
                    continue
                score = float(scores[index]) if index < len(scores) else 0.0
                box = polys[index].tolist() if index < len(polys) and hasattr(polys[index], "tolist") else polys[index] if index < len(polys) else None
                lines.append({"box": box, "text": text, "score": score})
            return lines

        lines: list[dict[str, object]] = []
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
