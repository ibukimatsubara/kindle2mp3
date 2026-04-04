"""LLM-based OCR text correction using Ollama."""
from __future__ import annotations

import json
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SENTENCE_END_RE = re.compile(r"[。！？!?」）\)]$")
# Lines shorter than this are treated as complete units (headings, list items)
SHORT_LINE_THRESHOLD = 40

DEFAULT_MODEL = "gemma3:4b"
DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_CONTEXT_LINES = 3

SYSTEM_PROMPT = """\
あなたはOCR誤認識の修正専門家です。
ルール:
- 明らかなOCR誤字のみ修正する
- 原文の意味・構造・句読点の位置は変えない
- 文を追加・削除・要約しない
- 修正後のテキストだけを出力する（説明不要）"""

FIX_PROMPT_TEMPLATE = """\
以下はOCR結果の一部です。[修正対象]の行のOCR誤字だけを修正してください。
[文脈]の行は参照用です。出力しないでください。

{context}

[修正対象]の行の修正結果だけを1行で出力してください。説明や番号は不要です。"""


@dataclass(slots=True)
class LlmFixResult:
    session_id: str
    fixed_path: Path
    original_text: str
    fixed_text: str
    sentence_count: int
    changed_count: int

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "fixed_path": str(self.fixed_path),
            "sentence_count": self.sentence_count,
            "changed_count": self.changed_count,
        }


class OllamaManager:
    """Start/stop ollama serve as a subprocess."""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    def ensure_running(self, base_url: str = DEFAULT_BASE_URL) -> None:
        if self._is_reachable(base_url):
            return
        if base_url != DEFAULT_BASE_URL:
            raise RuntimeError(
                f"Remote Ollama at {base_url} is not reachable"
            )
        self._process = subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # wait for it to be ready
        for _ in range(30):
            time.sleep(1)
            if self._is_reachable(base_url):
                return
        raise RuntimeError("ollama serve did not start within 30 seconds")

    def stop(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    @staticmethod
    def _is_reachable(base_url: str) -> bool:
        try:
            with urlopen(base_url, timeout=2):
                return True
        except (URLError, OSError):
            return False


class OllamaClient:
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 512,
            },
        }
        req = Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result.get("response", "").strip()


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, respecting paragraph breaks and short lines."""
    # Split on paragraph breaks (double newline) first
    paragraphs = text.split("\n\n")
    sentences: list[str] = []

    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        current = ""

        for line in lines:
            # Short lines are likely headings or list items — keep them separate
            if len(line) <= SHORT_LINE_THRESHOLD and not current:
                sentences.append(line)
                continue

            if current:
                current += line
            else:
                current = line

            if SENTENCE_END_RE.search(current):
                sentences.append(current)
                current = ""

        if current:
            sentences.append(current)

    return sentences


def build_fix_prompt(
    sentences: list[str],
    target_idx: int,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> str:
    start = max(0, target_idx - context_lines)
    end = min(len(sentences), target_idx + context_lines + 1)

    lines: list[str] = []
    for i in range(start, end):
        if i == target_idx:
            lines.append(f"[修正対象] {sentences[i]}")
        else:
            lines.append(f"[文脈] {sentences[i]}")

    context = "\n".join(lines)
    return FIX_PROMPT_TEMPLATE.format(context=context)


class LlmFixer:
    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        context_lines: int = DEFAULT_CONTEXT_LINES,
    ) -> None:
        self.client = OllamaClient(model=model, base_url=base_url)
        self.context_lines = context_lines

    def fix_text(self, text: str) -> tuple[str, int, int]:
        """Fix OCR text. Returns (fixed_text, sentence_count, changed_count)."""
        sentences = split_sentences(text)
        if not sentences:
            return text, 0, 0

        fixed: list[str] = []
        changed = 0

        for i, sentence in enumerate(sentences):
            prompt = build_fix_prompt(sentences, i, self.context_lines)
            result = self.client.generate(prompt)

            # Sanity check: if result is wildly different length, keep original
            result_clean = result.strip()
            # Strip any prompt artifacts the LLM might echo back
            for prefix in ("[修正対象]", "[修正対象] ", "[文脈]", "[文脈] "):
                if result_clean.startswith(prefix):
                    result_clean = result_clean[len(prefix):]
            result_clean = result_clean.strip()
            if not result_clean:
                fixed.append(sentence)
                continue

            ratio = len(result_clean) / len(sentence) if sentence else 1
            if ratio < 0.5 or ratio > 2.0:
                # LLM likely hallucinated or summarized
                fixed.append(sentence)
                continue

            if result_clean != sentence:
                changed += 1
            fixed.append(result_clean)

        return "\n".join(fixed), len(sentences), changed

    def run_for_session(
        self,
        *,
        session_id: str,
        combined_path: str | Path,
        fixed_path: str | Path,
    ) -> LlmFixResult:
        combined = Path(combined_path)
        output = Path(fixed_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        original_text = combined.read_text(encoding="utf-8").strip()
        fixed_text, sentence_count, changed_count = self.fix_text(original_text)

        output.write_text(fixed_text + "\n", encoding="utf-8")
        # Also overwrite combined.txt so TTS picks up the fixed version
        combined.write_text(fixed_text + "\n", encoding="utf-8")

        return LlmFixResult(
            session_id=session_id,
            fixed_path=output,
            original_text=original_text,
            fixed_text=fixed_text,
            sentence_count=sentence_count,
            changed_count=changed_count,
        )
