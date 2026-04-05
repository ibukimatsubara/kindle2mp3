# kindle2mp3 Technical Architecture

## 概要

Kindle デスクトップアプリの書籍ページをスクリーンショットで取得し、レイアウト分析 → OCR → テキスト整形 → 音声合成 → MP3 化するパイプライン。

## 処理フロー

```
capture → layout → ocr → clean → llm-fix → tts → merge
```

## 採用技術

### ウィンドウ制御・スクリーンショット

- **PyObjC + Quartz/CoreGraphics** でウィンドウ列挙・スクリーンショット
- **AppleScript + System Events** でページ送り (`key code 124/123`)
- `screencapture` コマンドをプライマリ、Quartz API をフォールバックに

### レイアウト分析

- **DocLayout-YOLO** (YOLOv10 ベース)
- DocStructBench で学習済みモデル (`juliozhao/DocLayout-YOLO-DocStructBench`)
- 検出カテゴリ: plain text, title, abandon, figure, figure_caption, Page-header, Page-footer 等
- `plain text` と `title` を本文領域として採用

縦書き対応:
- ページ画像を90度回転してから検出し、bbox を逆変換

### OCR

- **PaddleOCR** (`paddleocr` パッケージ)
- layout で特定した本文領域以外を白塗りマスクしてから OCR
- ページ全体の文脈 (フォントサイズ、行間) が保たれるため精度が維持される

### テキスト整形

**clean ステージ** (正規表現ベース):
- カタカナ長音修正 (`一→ー`)
- 類似文字修正 (`ソ→ン`, `ツ→ッ`)
- OCR 行折り返しの文単位結合

**llm-fix ステージ** (Gemini API):
- ページ単位スライディングウィンドウ (4ページずつ)
- ワンショットプロンプトで読み上げ用テキストに整形
- ウィンドウ単位でキャッシュし途中再開可能

### 音声合成

- **VOICEVOX** (`http://127.0.0.1:50021`)
- チャンク単位で合成、WAV で保存
- デフォルトスピーカー: 58 (猫使ビィ / ノーマル)

### 音声結合

- **Python wave モジュール** で WAV 連結 (チャンク間 300ms 無音挿入)
- **ffmpeg** で MP3 変換 (フォールバック: macOS afconvert で M4A)

## ファイル構成

```
src/kindle2mp3/
  cli.py            CLIエントリポイント、argparse、.env読み込み
  pipeline.py       各ステージのオーケストレーション
  capture.py        ウィンドウキャプチャ、キー送信、自動方向判定
  layout.py         DocLayout-YOLO によるレイアウト検出
  ocr.py            PaddleOCR、マスク処理、行ソート
  clean.py          正規表現ベースのテキスト正規化
  llm_fix.py        Gemini API によるテキスト整形
  tts.py            VOICEVOX TTS、テキストチャンク分割
  merge.py          WAV 連結、MP3/M4A 変換
  sessions.py       セッション管理、ディレクトリ・メタデータ
  windowing.py      macOS ウィンドウ列挙・Kindle 検出
  defaults.py       既定値定数
  podcast.py        RSS フィード生成・HTTP 配信
  presenters.py     CLI出力のテキスト整形
```

## 設計原則

- **ローカル優先**: OCR と TTS はローカル実行。LLM のみ Gemini API を利用
- **中間成果物保存**: 各ステップの出力をファイルに残す。失敗時に途中から再開可能
- **セッション単位管理**: 1冊 = 1セッション。workspace/book_XXXX に全成果物を集約
- **横書き・縦書き対応**: 自動判定でページ送り方向と OCR 読み順を切り替え
