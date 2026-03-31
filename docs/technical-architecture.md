# kindle2mp3 Technical Architecture

## Goal

このプロジェクトは、デスクトップ上の読書アプリから取得したスクリーンショットを OCR し、
日本語音声として読み上げ、最終的に 1 つの MP3 にまとめるためのローカル実行基盤を作る。

初期方針は以下の通り。

- ローカル完結を優先する
- 日本語特化で設計する
- 横書き、縦書きの両方に対応する
- macOS 上での実行を前提にする
- 音声生成の中間成果物は `wav` で保持し、最終段階だけ `mp3` 化する

## Selected Stack

### OCR

第一候補は `Tesseract OCR`。

- 横書き日本語: `jpn`
- 縦書き日本語: `jpn_vert`

理由:

- ローカルで完結する
- 日本語学習データがある
- `jpn_vert` により縦書き対応の逃げ道を持てる
- Python から扱いやすい

補助候補:

- `manga-ocr`
  - 日本語の縦書きやコミック系テキストに強い可能性がある
  - ただし初期構成では依存を増やしすぎないため、まずは追加候補に留める

### TTS

第一候補は `VOICEVOX`。

理由:

- ローカル HTTP エンジンとして動く
- Python から呼び出しやすい
- 日本語特化で相性が良い
- まず有料 API を前提にしなくてよい

補足:

- `Coefont` は有力候補だが、実運用は有料前提になりやすいため初期構成からは外す

### Audio Merge

音声結合は `ffmpeg` を使う。

理由:

- `wav` の連結と最終 `mp3` 化が安定している
- デバッグ時に中間音声を確認しやすい
- 再圧縮回数を減らせる

### Window Control and Screenshot

ブラウザ自動化ではなく、macOS のネイティブ操作を使う。

第一候補:

- `PyObjC + Accessibility API`
- `PyObjC + Quartz/CoreGraphics`

補助候補:

- `pywinctl`
- `pyautogui`

理由:

- `Playwright` はブラウザ自動化向けであり、ネイティブアプリ操作の主役には向かない
- 対象アプリの前面化、ウィンドウ座標取得、特定領域キャプチャには macOS ネイティブ API が適している

### Page Turn Strategy

ページ送りの本命は `AppleScript + System Events key code`。

初期採用方針:

- 前面化: `tell application id "com.amazon.Lassen" to activate`
- ページ送り: `tell application "System Events" to key code 124`
- 主なページ送りキー:
  - 右送り: `124`
  - 左送り: `123`

検証結果:

- `CGEvent` のキーボード入力は `Kindle` で安定しなかった
- `System Events key code` は実ページ遷移を観測できた
- 右側クリックも候補として残すが、メイン経路にはしない

前提権限:

- `Accessibility`
- `Screen Recording`
- `Automation` for `Ghostty -> System Events`

## Why Not Playwright

`Playwright` は `Chromium`, `WebKit`, `Firefox` などのブラウザ自動化ツールであり、
ネイティブデスクトップアプリの一般操作基盤ではない。

そのため、このプロジェクトでは以下のように位置づける。

- ブラウザ UI を操作する用途には使える
- デスクトップ版読書アプリの操作には主手段として採用しない

## System Architecture

想定する処理フロー:

1. `WindowController`
2. `ScreenCapture`
3. `PageAnalyzer`
4. `OcrEngine`
5. `TextNormalizer`
6. `TtsEngine`
7. `AudioAssembler`

### 1. WindowController

役割:

- 対象アプリの起動
- ウィンドウの列挙
- 対象ウィンドウの特定
- 前面化
- ページ送りやキー入力

想定実装:

- `PyObjC` 経由で `Accessibility API` を使う

### 2. ScreenCapture

役割:

- 対象ウィンドウの矩形取得
- 指定領域のスクリーンショット保存
- ページごとの画像ファイル管理

想定実装:

- `Quartz/CoreGraphics`

### 3. PageAnalyzer

役割:

- 横書きページか縦書きページかを判定する
- 混在ページを検出する
- OCR エンジンやモードを切り替える

初期方針:

- ページ単位で `horizontal / vertical / mixed` を持つ
- 将来的には領域単位判定に拡張する

### 4. OcrEngine

役割:

- 画像からテキスト抽出
- 方向ごとの OCR モデル切替
- ページ単位の OCR 結果保存

初期方針:

- 横書き: `jpn`
- 縦書き: `jpn_vert`

OCR の保存形式は、少なくとも以下を含める。

- `source_image`
- `text`
- `orientation`
- `provider`
- `confidence`

### 5. TextNormalizer

役割:

- 不自然な改行の除去
- ページ番号や柱の除去
- 重複行の除去
- TTS 向けの句読点正規化

重要点:

- 縦書き由来の行分割をここで吸収する
- OCR の生データは残し、正規化後テキストは別ファイルに分ける

### 6. TtsEngine

役割:

- 正規化済みテキストをチャンク化
- VOICEVOX に投入
- チャンクごとの `wav` を生成

初期方針:

- 文単位または短い段落単位でチャンク化する
- 生成失敗時の再試行を可能にする

### 7. AudioAssembler

役割:

- `wav` 一覧を順番に連結
- 最終成果物として `mp3` を生成

初期方針:

- 中間音声は `wav`
- 最後にだけ `ffmpeg` で `mp3` 化

## Local-First Design Principles

- クラウド API を必須にしない
- 各工程を CLI で個別実行できるようにする
- 中間成果物を残して、失敗地点から再開できるようにする
- OCR と TTS はプロバイダ差し替え可能な抽象で実装する

## Proposed Python Interfaces

```python
class OcrProvider:
    def extract(self, image_path: str, orientation: str) -> dict:
        ...


class TtsProvider:
    def synthesize(self, text: str, output_path: str, speaker: str | None = None) -> None:
        ...


class WindowController:
    def focus_target(self) -> None:
        ...

    def next_page(self) -> None:
        ...


class ScreenCapture:
    def capture_current_page(self, output_path: str) -> None:
        ...


class AudioMerger:
    def merge_wav_files(self, inputs: list[str], output_mp3: str) -> None:
        ...
```

## Initial Milestones

### Phase 1

`OCR -> TTS -> Merge` の最小パイプラインを作る。

- 画像入力
- `Tesseract` による OCR
- `VOICEVOX` による音声生成
- `ffmpeg` による結合

### Phase 2

画面取得とウィンドウ操作を追加する。

- 対象ウィンドウ列挙
- 前面化
- スクリーンショット保存
- ページ送り

### Phase 3

精度改善と再開性を強化する。

- 縦書き判定強化
- 正規化ルール追加
- リトライ制御
- ジョブ保存

## Tooling Notes

- Python パッケージ管理: `uv`
- 実行単位: CLI
- 中間データ:
  - `images/`
  - `ocr/`
  - `text/`
  - `audio/wav/`
  - `dist/`

## References

- CoeFont pricing: `https://coefont.cloud/selectPlan`
- VOICEVOX terms: `https://voicevox.hiroshiba.jp/term/`
- VOICEVOX Engine: `https://github.com/VOICEVOX/voicevox_engine`
- Playwright browsers: `https://playwright.dev/docs/browsers`
- Playwright top page: `https://playwright.dev/`
- Apple AXUIElement docs: `https://developer.apple.com/documentation/applicationservices/axuielement_h`
- PyObjC Quartz notes: `https://pyobjc.readthedocs.io/en/latest/apinotes/Quartz.html`
- PyWinCtl: `https://github.com/Kalmat/PyWinCtl`
- PyAutoGUI screenshots: `https://pyautogui.readthedocs.io/en/latest/screenshot.html`
- Tesseract: `https://github.com/tesseract-ocr/tesseract`
- Tesseract traineddata: `https://github.com/tesseract-ocr/tessdata_fast`
- manga-ocr: `https://github.com/kha-white/manga-ocr`
