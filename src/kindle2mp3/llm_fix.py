"""LLM-based OCR text correction using Gemini API."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen


DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_WINDOW_PAGES = 4
DEFAULT_STRIDE_PAGES = 2

SYSTEM_PROMPT = """\
あなたは書籍OCRテキストの校正・整形の専門家です。
OCRで読み取った書籍テキストを、音声読み上げに適した形に整形します。
原文の意味は絶対に変えないでください。"""

FIX_PROMPT = """\
以下は書籍のOCRテキストです。読み上げ用に整形してください。

ルール:
1. OCR誤字を修正する。文脈から判断して自然な日本語にする
2. 行折り返しを結合して自然な文にする
3. 見出しの前には空行を入れる
4. 括弧は除去して自然な表現にする
5. 文と文の間は改行で区切る
6. 読み上げに不要な記号は除去する
7. 原文の意味は絶対に変えない

入力の例:
第3章　基本的な考え方
●本章では、プロジエクトにおけるチ一ム
ワークの重要性について解説します。「効率
的なコミユニケーション」が成功の鍵であ
ると言われています。
メンバ一同士が信頼関係を築くためには、
率直で効率的なやり取りが必要です。

出力の例:
第3章 基本的な考え方

本章では、プロジェクトにおけるチームワークの重要性について解説します。
効率的なコミュニケーションが成功の鍵であると言われています。
メンバー同士が信頼関係を築くためには、率直で効率的なやり取りが必要です。

ここから実際の処理です。
「処理対象」の整形結果だけを出力してください。
文脈は参照用です。出力しないでください。

{context_before}
--- 処理対象 ---
{target}
---
{context_after}"""


@dataclass(slots=True)
class LlmFixResult:
    session_id: str
    fixed_path: Path
    original_text: str
    fixed_text: str
    window_count: int
    changed: bool

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "fixed_path": str(self.fixed_path),
            "window_count": self.window_count,
            "changed": self.changed,
        }


class GeminiClient:
    def __init__(self, *, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
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
                "maxOutputTokens": 4096,
            },
        }
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return parts[0].get("text", "").strip() if parts else ""


def split_pages(text: str) -> list[str]:
    """Split combined text into pages (separated by double newline)."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def build_prompt(
    pages: list[str],
    target_start: int,
    target_end: int,
    context_before: str,
) -> str:
    before_pages = pages[max(0, target_start - 1):target_start]
    after_pages = pages[target_end:min(len(pages), target_end + 1)]

    ctx_before = ""
    if context_before:
        # Use last few lines from previous window's output for continuity
        lines = context_before.strip().split("\n")
        ctx_before = "\n".join(lines[-5:]) if len(lines) > 5 else context_before.strip()
        ctx_before = f"--- 前の文脈 ---\n{ctx_before}\n\n"
    elif before_pages:
        ctx_before = f"--- 前の文脈 ---\n{before_pages[0]}\n\n"

    ctx_after = ""
    if after_pages:
        ctx_after = f"\n--- 後の文脈 ---\n{after_pages[0]}"

    target = "\n\n".join(pages[target_start:target_end])

    return FIX_PROMPT.format(
        context_before=ctx_before,
        target=target,
        context_after=ctx_after,
    )


class LlmFixer:
    def __init__(
        self,
        *,
        client: GeminiClient,
        window_pages: int = DEFAULT_WINDOW_PAGES,
        stride_pages: int = DEFAULT_STRIDE_PAGES,
    ) -> None:
        self.client = client
        self.window_pages = window_pages
        self.stride_pages = stride_pages

    def fix_text(self, text: str) -> tuple[str, int]:
        """Fix OCR text. Returns (fixed_text, window_count)."""
        pages = split_pages(text)
        if not pages:
            return text, 0

        total_pages = len(pages)

        # If all pages fit in one window, process in a single call
        if total_pages <= self.window_pages:
            print(f"  llm-fix: processing {total_pages} page(s) in 1 window", flush=True)
            prompt = build_prompt(pages, 0, total_pages, "")
            result = self.client.generate(prompt)
            if result.strip():
                return result.strip(), 1
            return text, 1

        total_windows = (total_pages + self.stride_pages - 1) // self.stride_pages
        results: list[str] = []
        window_count = 0
        prev_output = ""
        processed_up_to = 0

        while processed_up_to < total_pages:
            start = processed_up_to
            end = min(start + self.window_pages, total_pages)
            window_count += 1
            print(f"  llm-fix: window {window_count}/{total_windows} (pages {start + 1}-{end})", flush=True)
            prompt = build_prompt(pages, start, end, prev_output)
            result = self.client.generate(prompt)

            if result.strip():
                results.append(result.strip())
                prev_output = result.strip()
            else:
                results.append("\n\n".join(pages[start:end]))
                prev_output = ""

            processed_up_to = end

        return "\n\n".join(results), window_count

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
        fixed_text, window_count = self.fix_text(original_text)

        output.write_text(fixed_text + "\n", encoding="utf-8")
        combined.write_text(fixed_text + "\n", encoding="utf-8")

        return LlmFixResult(
            session_id=session_id,
            fixed_path=output,
            original_text=original_text,
            fixed_text=fixed_text,
            window_count=window_count,
            changed=original_text != fixed_text,
        )
