"""Text cleaning and normalization after OCR."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CleanPageResult:
    source_path: Path
    clean_path: Path
    original_text: str
    clean_text: str


@dataclass(slots=True)
class CleanRunResult:
    session_id: str
    combined_path: Path
    pages: list[CleanPageResult]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "combined_path": str(self.combined_path),
            "page_count": len(self.pages),
        }


# ── Noise patterns ──────────────────────────────────
_NOISE_PATTERNS = [
    re.compile(r"^[\s　]*$"),  # blank lines
]


_SENTENCE_END_RE = re.compile(r"[。！？!?]")


class TextCleaner:
    def clean_page(self, text: str) -> str:
        lines = text.split("\n")
        normalized: list[str] = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(p.match(line) for p in _NOISE_PATTERNS):
                continue
            line = self._normalize(line)
            normalized.append(line)

        # Join OCR line-wraps into proper sentences.
        sentences: list[str] = []
        current = ""
        for line in normalized:
            if current:
                current += line
            else:
                current = line

            while True:
                match = _SENTENCE_END_RE.search(current)
                if not match:
                    break
                end_pos = match.end()
                sentences.append(current[:end_pos])
                current = current[end_pos:].strip()

        if current:
            sentences.append(current)

        return "\n".join(sentences)

    def _normalize(self, text: str) -> str:
        # full-width tilde normalization
        text = text.replace("～", "〜")

        # collapse multiple spaces
        text = re.sub(r"[ 　]{2,}", " ", text)

        return text

    def run_for_session(
        self,
        *,
        session_id: str,
        text_dir: str | Path,
        clean_dir: str | Path,
        combined_path: str | Path,
    ) -> CleanRunResult:
        text_dir_path = Path(text_dir)
        clean_dir_path = Path(clean_dir)
        combined_path_obj = Path(combined_path)
        clean_dir_path.mkdir(parents=True, exist_ok=True)
        combined_path_obj.parent.mkdir(parents=True, exist_ok=True)

        pages: list[CleanPageResult] = []
        combined_texts: list[str] = []

        for text_path in sorted(text_dir_path.glob("page_*.txt")):
            original_text = text_path.read_text(encoding="utf-8").strip()
            clean_text = self.clean_page(original_text)

            clean_path = clean_dir_path / text_path.name
            clean_path.write_text(
                clean_text + ("\n" if clean_text else ""),
                encoding="utf-8",
            )

            pages.append(CleanPageResult(
                source_path=text_path,
                clean_path=clean_path,
                original_text=original_text,
                clean_text=clean_text,
            ))
            if clean_text:
                combined_texts.append(clean_text)

        combined_text = "\n\n".join(combined_texts)
        combined_path_obj.write_text(
            combined_text + ("\n" if combined_text else ""),
            encoding="utf-8",
        )

        return CleanRunResult(
            session_id=session_id,
            combined_path=combined_path_obj,
            pages=pages,
        )
