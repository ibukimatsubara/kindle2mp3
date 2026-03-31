# kindle2mp3 CLI Workflow

## Goal

このドキュメントは、利用者が CLI だけで `capture -> ocr -> tts -> merge` を順番に実行できる運用フローを定義する。

前提:

- 利用者は対象アプリを自分で開く
- 利用者は対象書籍の読み上げ開始位置まで自分で移動する
- 以降の処理は CLI で段階的に実行する
- 各処理はセッション単位で管理する

## User Flow

利用者の想定手順は以下。

1. 対象アプリを開く
2. 対象書籍を開く
3. 読み上げを開始したいページに移動する
4. `capture` を実行してページ画像を保存する
5. `ocr` を実行してテキスト化する
6. `tts` を実行して音声化する
7. `merge` を実行して最終 MP3 を作る

この設計では、各ステップを独立コマンドに分割する。

理由:

- 途中で失敗しても途中から再開しやすい
- OCR や TTS のパラメータを後から調整しやすい
- キャプチャ済みデータを何度でも再利用できる

## Session Model

1 冊ごと、または 1 回の作業単位ごとに `workspace` 下へセッションフォルダを作る。

命名規則の初期案:

- `book_0001`
- `book_0002`
- `book_0003`

将来的に人間が判別しやすい別名を持たせる場合は、メタデータに書名を保存する。
ディレクトリ名は CLI や自動処理に優しい固定フォーマットを維持する。

## Directory Layout

```text
workspace/
  book_0001/
    session.json
    capture/
      raw/
        page_000001.png
        page_000002.png
      debug/
    ocr/
      raw/
        page_000001.json
        page_000002.json
      normalized/
        page_000001.txt
        page_000002.txt
      combined.txt
    tts/
      chunks/
        chunk_000001.txt
        chunk_000002.txt
      wav/
        chunk_000001.wav
        chunk_000002.wav
      manifest.json
    output/
      audiobook.mp3
    logs/
      capture.log
      ocr.log
      tts.log
      merge.log
```

## Session Metadata

各セッションのルートには `session.json` を置く。

最低限、以下の情報を持たせる。

```json
{
  "session_id": "book_0001",
  "title": null,
  "created_at": "2026-03-31T12:00:00+09:00",
  "status": "capture_pending",
  "capture": {
    "direction": null,
    "page_count": 0,
    "image_format": "png"
  },
  "ocr": {
    "provider": "tesseract",
    "languages": ["jpn", "jpn_vert"]
  },
  "tts": {
    "provider": "voicevox",
    "speaker": null
  },
  "output": {
    "mp3_path": null
  }
}
```

## Workflow Design

### Step 1: Create Session

新しい作業開始時にセッションを作る。

コマンド案:

```bash
kindle2mp3 session create --title "Book Name"
```

期待動作:

- `workspace` がなければ作成する
- 次の連番を採番する
- `book_000X` ディレクトリを作る
- サブディレクトリを初期化する
- `session.json` を作る

出力例:

```text
Created session: book_0001
Path: workspace/book_0001
```

### Step 2: Capture Pages

利用者が対象書籍を開いた後で実行する。

コマンド案:

```bash
kindle2mp3 capture run --session book_0001
```

#### Page Turn Handling

初期版では、ページ送りはクリックではなくキーボード方式を使う。

採用方式:

- 前面化: `AppleScript`
- キー送信: `System Events key code`

コマンド案:

```bash
kindle2mp3 capture run --session book_0001 --key right --pages 120
```

またはセッション未統合の段階では:

```bash
kindle2mp3 capture run --output-dir workspace/book_0001/capture/raw --key right --pages 120
```

方向とキーの対応は次を基本とする。

- `right` -> `key code 124`
- `left` -> `key code 123`

ページ送り方向は次の 2 案がある。

案 A:

- 利用者が明示指定する

```bash
kindle2mp3 capture run --session book_0001 --direction right
kindle2mp3 capture run --session book_0001 --direction left
```

案 B:

- システムが自動推定する

ただし初期版では自動推定より、利用者指定の方が堅い。

理由:

- 読書アプリの表示モード差分が大きい
- 誤判定すると最初からキャプチャをやり直す可能性がある
- CLI では明示指定の方がデバッグしやすい

初期採用方針:

- `--key right|left` を利用者指定にする
- メインの入力経路は `system_events`
- `cgevent` はデバッグ用の補助とする

#### Stop Condition

ページ取得の終了条件も初期段階では利用者指定を基本にする。

コマンド案:

```bash
kindle2mp3 capture run --session book_0001 --key right --pages 120
```

または対話なしで実行しやすいように、次も候補にする。

```bash
kindle2mp3 capture run --session book_0001 --key right --until-duplicate 3
```

ただし初期版は `--pages` を優先採用する。

理由:

- 実装が簡単
- 終了判定が明確
- 同一ページ検出は後から追加しやすい

#### Capture Responsibilities

`capture` の責務:

- 対象ウィンドウの取得
- 前面化
- 現在ページを `png` で保存
- `System Events key code` によるページ送り
- これを指定回数だけ繰り返す

保存規則:

- `capture/raw/page_000001.png`
- `capture/raw/page_000002.png`

### Step 3: OCR

キャプチャ済み画像に対して OCR を実行する。

コマンド案:

```bash
kindle2mp3 ocr run --session book_0001
```

初期方針:

- 対象画像を順番に読む
- 各画像の向きを判定または指定する
- `jpn` / `jpn_vert` を使い分ける
- 生 OCR 結果を JSON で保存する
- 正規化後テキストを TXT で保存する
- 最後に全文連結版を `ocr/combined.txt` に保存する

オプション候補:

```bash
kindle2mp3 ocr run --session book_0001 --orientation auto
kindle2mp3 ocr run --session book_0001 --orientation vertical
kindle2mp3 ocr run --session book_0001 --orientation horizontal
```

初期採用方針:

- `--orientation auto` を既定
- 必要なら固定指定で再実行できるようにする

### Step 4: TTS

OCR 後のテキストから音声を作る。

コマンド案:

```bash
kindle2mp3 tts run --session book_0001 --speaker 3
```

責務:

- `combined.txt` もしくは正規化済みテキスト群を読む
- 文または段落単位でチャンク分割する
- `tts/chunks/*.txt` を作る
- `VOICEVOX` に投入して `tts/wav/*.wav` を作る
- チャンク対応表を `tts/manifest.json` に保存する

初期採用方針:

- 入力は `ocr/combined.txt`
- 文単位チャンクを基本にする
- 再実行時は既存 `wav` を再利用できる設計にする

### Step 5: Merge

生成済みの `wav` を結合して最終成果物を作る。

コマンド案:

```bash
kindle2mp3 merge run --session book_0001
```

責務:

- `tts/wav/*.wav` を順番に読む
- 一時ファイルまたは concat manifest を作る
- `ffmpeg` で結合する
- `output/audiobook.mp3` を生成する

## CLI Shape

コマンド体系はサブコマンド方式にする。

```bash
kindle2mp3 session create
kindle2mp3 session list
kindle2mp3 session show --session book_0001

kindle2mp3 capture run --session book_0001 --key right --pages 120
kindle2mp3 ocr run --session book_0001
kindle2mp3 tts run --session book_0001 --speaker 3
kindle2mp3 merge run --session book_0001
```

この構成の利点:

- ステップの責務が明確
- 自動化しやすい
- ログや再開制御を入れやすい

## Resume Strategy

再開性は CLI ツールとして重要。

初期方針:

- 既存成果物があればスキップできる
- `--force` 指定時だけ上書きする

例:

```bash
kindle2mp3 ocr run --session book_0001
kindle2mp3 ocr run --session book_0001 --force
```

## Logging

各ステップは個別ログを持つ。

- `logs/capture.log`
- `logs/ocr.log`
- `logs/tts.log`
- `logs/merge.log`

CLI 標準出力には進捗を簡潔に出し、詳細はログへ保存する。

## Recommended Initial Decisions

初期版で先に決めてよい内容:

- セッション ID は `book_0001` 形式
- `workspace` 配下に全成果物を集約
- `capture` は `--key` を利用者指定
- `capture` の終了条件は `--pages` 指定
- `ocr` は `--orientation auto` を既定
- `tts` は `combined.txt` を入力にする
- `merge` は `wav` から `mp3` を作る
- すべて CLI サブコマンドとして実装する

## Open Questions

後続で決めるべき論点:

- `capture` の対象ウィンドウはタイトル一致で取るか、前面ウィンドウ固定にするか
- OCR の向き判定をどこまで自動化するか
- TTS のチャンク長を文単位にするか、一定文字数にするか
- 最終 MP3 名を固定にするか、書名由来にするか
- セッション ID 採番を単純連番にするか、日付を含めるか
