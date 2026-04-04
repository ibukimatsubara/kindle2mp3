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


# ── Katakana long vowel fix ──────────────────────────
# PaddleOCR often recognizes ー (katakana prolonged sound mark)
# as 一 (kanji "one"). Fix this when 一 appears between katakana.
#
# Pattern: カタカナ + 一 + カタカナ or end-of-chunk
_KATAKANA = r"\u30A0-\u30FF"
_KANA_LONG_VOWEL_RE = re.compile(
    rf"([{_KATAKANA}])一([{_KATAKANA}]|[^一-龥\d]|$)"
)


def _fix_katakana_long_vowel(text: str) -> str:
    # Need to apply repeatedly because matches can overlap
    # e.g. "チ一ム" → first pass catches チ一ム
    prev = ""
    while prev != text:
        prev = text
        text = _KANA_LONG_VOWEL_RE.sub(r"\1ー\2", text)
    return text


# ── Similar character fixes ──────────────────────────
# Context-aware replacements for commonly confused characters.
# Each entry: (compiled_regex, replacement)
_CHAR_FIXES = [
    # ソ → ン after katakana (バージョソ → バージョン)
    (re.compile(rf"([{_KATAKANA}])ソ($|[^{_KATAKANA}])"), r"\1ン\2"),
    # ツ → ッ before ト (プラツト → プラット, コミツト → コミット)
    (re.compile(rf"([{_KATAKANA}])ツ(ト)"), r"\1ッ\2"),
    # ヅ → ジ before エ (プロヅエクト → プロジェクト)
    (re.compile(r"ヅエ"), "ジェ"),
    # ヅ → ジ in プロヅクト → プロジェクト
    (re.compile(r"プロヅクト"), "プロジェクト"),
]


# ── Noise patterns ──────────────────────────────────
_NOISE_PATTERNS = [
    re.compile(r"^[\s　]*$"),  # blank lines
]


_SENTENCE_END_RE = re.compile(r"[。！？!?]")
SHORT_LINE_THRESHOLD = 40


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
        # A line that doesn't end with sentence-ending punctuation
        # is a continuation of the previous line (OCR line-wrap).
        sentences: list[str] = []
        current = ""
        for line in normalized:
            if current:
                current += line
            else:
                current = line

            # Split on sentence boundaries within the joined text
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
        # katakana long vowel
        text = _fix_katakana_long_vowel(text)

        # similar character fixes
        for pattern, replacement in _CHAR_FIXES:
            text = pattern.sub(replacement, text)

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
