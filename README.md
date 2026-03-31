# kindle2mp3

CLI pipeline for capture, OCR, TTS, and audiobook assembly.

Current scope:

- session-oriented workspace layout
- macOS window recognition for Kindle
- one-command `capture -> ocr -> tts -> merge`

## Quick Start

利用前提:

- Kindle を開いて対象書籍の開始ページまで移動する
- VOICEVOX Engine を起動しておく

最短実行:

```bash
uv sync
uv run kindle2mp3 run --title "Book Title"
```

既定値:

- page turn: `right`
- transport: `system_events`
- stop condition: 差分なしが 4 回連続したら停止
- speaker: `58` (`猫使ビィ / ノーマル`)

## Development

```bash
uv sync
uv run kindle2mp3 windows list
```
