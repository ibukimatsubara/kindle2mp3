# kindle2mp3

Kindle の書籍をスクリーンショット → OCR → 音声合成して MP3 オーディオブックを生成する CLI ツール。

## パイプライン

```
capture → layout → ocr → clean → llm-fix → tts → merge
```

1. **capture** — Kindle ウィンドウのページを自動でスクリーンショット
2. **layout** — DocLayout-YOLO でページ構造を分析し、本文領域を特定
3. **ocr** — PaddleOCR で本文領域のみを OCR
4. **clean** — 正規表現で OCR 誤字を修正、行折り返しを文単位に結合
5. **llm-fix** — Gemini API で OCR テキストを読み上げ用に整形
6. **tts** — VOICEVOX で音声合成
7. **merge** — WAV を結合して MP3 を生成

## セットアップ

```bash
uv sync
```

### 必要なもの

- macOS (Quartz API を使用)
- VOICEVOX Engine を起動しておく
- ffmpeg (`brew install ffmpeg`)
- Gemini API キー

### API キー設定

プロジェクトルートに `.env` を作成:

```
GEMINI_API_KEY=your-api-key-here
```

API キーは https://aistudio.google.com/apikey で取得できる。

### macOS 権限

- Accessibility
- Screen Recording
- Automation (Terminal → System Events)

## 使い方

### 1コマンドで全パイプライン実行

Kindle で対象書籍の開始ページまで移動してから:

```bash
uv run kindle2mp3 run --title "本のタイトル"
```

出力: `workspace/book_XXXX/output/audiobook.mp3`

### オプション

```bash
# ページ送り方向を指定 (デフォルト: auto で自動判定)
uv run kindle2mp3 run --title "小説" --key left

# ページ数を指定 (デフォルト: 差分なし4回で自動停止)
uv run kindle2mp3 run --title "Book" --pages 100

# VOICEVOX スピーカーを指定 (デフォルト: 58)
uv run kindle2mp3 run --title "Book" --speaker 3
```

### 個別ステップ実行

```bash
uv run kindle2mp3 capture run --session book_0001
uv run kindle2mp3 layout run --session book_0001
uv run kindle2mp3 ocr run --session book_0001
uv run kindle2mp3 clean run --session book_0001
uv run kindle2mp3 llm-fix run --session book_0001
uv run kindle2mp3 tts run --session book_0001 --speaker 58
uv run kindle2mp3 merge run --session book_0001
```

### セッション管理

```bash
uv run kindle2mp3 session list
uv run kindle2mp3 session show --session book_0001 --json
```

## ディレクトリ構造

```
workspace/book_0001/
  session.json
  capture/raw/          page_000001.png ...
  layout/               page_000001.json (DocLayout-YOLO 結果)
  ocr/
    raw/                page_000001.json (OCR 生結果)
    text/               page_000001.txt (OCR テキスト)
    clean/              page_000001.txt (正規表現修正後)
    llm_windows/        window_0001.txt ... (LLM fix 中間結果)
    combined.txt        最終テキスト
    llm_fixed.txt       LLM fix 後テキスト
  tts/
    chunks/             chunk_000001.txt ...
    wav/                chunk_000001.wav ...
    manifest.json
  output/
    audiobook.mp3
    audiobook.wav
```

## 横書き・縦書き対応

- `--key auto` (デフォルト): →キーと←キーを試して自動判定
- 横書き: →キーでページ送り、OCR は上→下・左→右
- 縦書き: ←キーでページ送り、OCR は右→左・上→下、layout 検出時にページを90度回転

## 技術スタック

- **ウィンドウ制御**: PyObjC + Quartz/CoreGraphics
- **ページ送り**: AppleScript + System Events
- **レイアウト分析**: DocLayout-YOLO
- **OCR**: PaddleOCR
- **テキスト整形**: Gemini API (gemini-2.5-flash-lite)
- **音声合成**: VOICEVOX
- **音声結合**: ffmpeg (フォールバック: afconvert)
- **パッケージ管理**: uv

## Podcast 配信

生成した MP3 を RSS フィードとして Podcast アプリで聴ける。

### フィード生成のみ

```bash
uv run kindle2mp3 podcast generate
```

`podcast/feed.xml` と `podcast/media/` にフィードと音声ファイルが出力される。

### フィード生成 + HTTP サーバー起動

```bash
uv run kindle2mp3 podcast serve --port 8080
```

Podcast アプリに `http://<IPアドレス>:8080/feed.xml` を登録する。

### オプション

```bash
# ベース URL を指定 (Tailscale 等で外部公開する場合)
uv run kindle2mp3 podcast serve --base-url http://100.x.x.x:8080

# タイトル・説明をカスタマイズ
uv run kindle2mp3 podcast serve --title "My Audiobooks" --description "Kindle本の読み上げ"
```

完成済みセッション (`merge_completed`) のみがエピソードとして含まれる。エピソードが 0 件の場合はサーバーを起動しない。

## テスト

```bash
uv run python -m unittest discover -s tests -v
```
