"""LLM-based OCR text correction using Gemini API or Ollama."""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


SENTENCE_END_RE = re.compile(r"[。！？!?」）\)]$")
SHORT_LINE_THRESHOLD = 40

DEFAULT_CONTEXT_LINES = 3

SYSTEM_PROMPT = """\
あなたはOCR誤認識の校正者です。

絶対に守るルール:
1. 誤字の修正だけを行う。1〜3文字の置換のみ許可する
2. 文の追加・削除・並べ替え・言い換えは禁止
3. 意味や構造が正しい箇所は絶対に変えない
4. 修正が不要なら入力をそのまま返す
5. 修正後のテキストだけを出力する。説明・注釈・番号は一切不要

よくあるOCR誤字の例:
- 一→ー（カタカナの長音）: チ一ム→チーム
- ユ→ュ（小書き）: レビユー→レビュー
- ソ→ン: バージョソ→バージョン
- ツ→ッ: プラツト→プラット"""

FIX_PROMPT_TEMPLATE = """\
以下の「>>>」行のOCR誤字を修正してください。
前後の行は文脈です。出力しないでください。
修正がなければ「>>>」行をそのまま返してください。

{context}

「>>>」行の修正結果だけを出力:"""


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


# ── LLM Clients ─────────────────────────────────────

class GeminiClient:
    def __init__(self, *, model: str = "gemini-2.5-flash-lite", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is required. "
                "Get one at https://aistudio.google.com/apikey"
            )

    def generate(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 256,
            },
        }
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "").strip() if parts else ""


class OllamaClient:
    def __init__(self, *, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "system": SYSTEM_PROMPT,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 256},
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


class OllamaManager:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    def ensure_running(self, base_url: str) -> None:
        if self._is_reachable(base_url):
            return
        if base_url != "http://localhost:11434":
            raise RuntimeError(f"Remote Ollama at {base_url} is not reachable")
        self._process = subprocess.Popen(
            ["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
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


# ── Sentence splitting ───────────────────────────────

def split_sentences(text: str) -> list[str]:
    paragraphs = text.split("\n\n")
    sentences: list[str] = []

    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        current = ""

        for line in lines:
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
    sentences: list[str], target_idx: int, context_lines: int = DEFAULT_CONTEXT_LINES,
) -> str:
    start = max(0, target_idx - context_lines)
    end = min(len(sentences), target_idx + context_lines + 1)

    lines: list[str] = []
    for i in range(start, end):
        if i == target_idx:
            lines.append(f">>> {sentences[i]}")
        else:
            lines.append(f"    {sentences[i]}")

    context = "\n".join(lines)
    return FIX_PROMPT_TEMPLATE.format(context=context)


# ── Fixer ────────────────────────────────────────────

class LlmFixer:
    def __init__(self, *, client, context_lines: int = DEFAULT_CONTEXT_LINES) -> None:
        self.client = client
        self.context_lines = context_lines

    def fix_text(self, text: str) -> tuple[str, int, int]:
        sentences = split_sentences(text)
        if not sentences:
            return text, 0, 0

        fixed: list[str] = []
        changed = 0

        for i, sentence in enumerate(sentences):
            prompt = build_fix_prompt(sentences, i, self.context_lines)
            result = self.client.generate(prompt)

            result_clean = result.strip()
            for prefix in (">>>", ">>> ", "「>>>」"):
                if result_clean.startswith(prefix):
                    result_clean = result_clean[len(prefix):]
            result_clean = result_clean.strip().strip("「」")

            if not result_clean:
                fixed.append(sentence)
                continue

            ratio = len(result_clean) / len(sentence) if sentence else 1
            if ratio < 0.5 or ratio > 2.0:
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
        combined.write_text(fixed_text + "\n", encoding="utf-8")

        return LlmFixResult(
            session_id=session_id,
            fixed_path=output,
            original_text=original_text,
            fixed_text=fixed_text,
            sentence_count=sentence_count,
            changed_count=changed_count,
        )
