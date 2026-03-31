from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kindle2mp3.capture import (
    PageCaptureRunner,
    KeyPressProbe,
    WindowCapture,
)
from kindle2mp3.merge import AudioMerger
from kindle2mp3.ocr import PaddleOcrRunner
from kindle2mp3.sessions import SessionManager
from kindle2mp3.tts import VoicevoxTtsRunner
from kindle2mp3.windowing import MacOSWindowDetector, WindowingUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kindle2mp3")
    subparsers = parser.add_subparsers(dest="command", required=True)

    windows_parser = subparsers.add_parser("windows", help="Inspect macOS windows")
    windows_subparsers = windows_parser.add_subparsers(dest="windows_command", required=True)

    session_parser = subparsers.add_parser("session", help="Manage workspace sessions")
    session_subparsers = session_parser.add_subparsers(dest="session_command", required=True)

    session_create = session_subparsers.add_parser("create", help="Create a new workspace session")
    session_create.add_argument("--title", help="Optional title for the session")
    session_create.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    session_subparsers.add_parser("list", help="List existing workspace sessions")

    session_show = session_subparsers.add_parser("show", help="Show a workspace session")
    session_show.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    session_show.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    list_parser = windows_subparsers.add_parser("list", help="List visible application windows")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table")
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Include off-screen windows and background surfaces",
    )

    detect_parser = windows_subparsers.add_parser("detect", help="Detect Kindle windows")
    detect_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    capture_parser = subparsers.add_parser("capture", help="Capture or probe Kindle pages")
    capture_subparsers = capture_parser.add_subparsers(dest="capture_command", required=True)

    ocr_parser = subparsers.add_parser("ocr", help="Run OCR on captured session images")
    ocr_subparsers = ocr_parser.add_subparsers(dest="ocr_command", required=True)

    tts_parser = subparsers.add_parser("tts", help="Run TTS for OCR text")
    tts_subparsers = tts_parser.add_subparsers(dest="tts_command", required=True)

    merge_parser = subparsers.add_parser("merge", help="Merge generated WAV files into a final MP3")
    merge_subparsers = merge_parser.add_subparsers(dest="merge_command", required=True)

    ocr_run = ocr_subparsers.add_parser("run", help="Run OCR for a session")
    ocr_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    ocr_run.add_argument("--lang", default="japan", help="PaddleOCR language code")
    ocr_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    tts_run = tts_subparsers.add_parser("run", help="Run VOICEVOX TTS for a session")
    tts_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    tts_run.add_argument("--speaker", type=int, required=True, help="VOICEVOX speaker style id")
    tts_run.add_argument("--base-url", default="http://127.0.0.1:50021", help="VOICEVOX Engine base URL")
    tts_run.add_argument("--max-chars", type=int, default=180, help="Maximum characters per chunk")
    tts_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    merge_run = merge_subparsers.add_parser("run", help="Merge WAV chunks for a session")
    merge_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    merge_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    shot_parser = capture_subparsers.add_parser("shot", help="Save a screenshot of the Kindle window")
    shot_parser.add_argument("--window-id", type=int, help="Explicit macOS window id")
    shot_parser.add_argument("--output", required=True, help="PNG output path")

    key_parser = capture_subparsers.add_parser(
        "probe-key",
        help="Focus Kindle and send a single key press, saving before/after screenshots",
    )
    key_parser.add_argument("--window-id", type=int, help="Explicit macOS window id")
    key_parser.add_argument("--key", choices=("left", "right", "space"), required=True)
    key_parser.add_argument(
        "--transport",
        choices=("system_events", "cgevent"),
        default="system_events",
        help="Key injection backend",
    )
    key_parser.add_argument("--output-dir", required=True, help="Directory for probe screenshots")
    key_parser.add_argument("--settle-delay", type=float, default=1.0, help="Delay after the key press")
    key_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    run_parser = capture_subparsers.add_parser("run", help="Capture multiple pages with keyboard page turns")
    run_parser.add_argument("--window-id", type=int, help="Explicit macOS window id")
    run_parser.add_argument("--session", help="Session id. When set, output goes to workspace/<session>/capture/raw")
    run_parser.add_argument("--key", choices=("left", "right", "space"), required=True)
    run_parser.add_argument(
        "--transport",
        choices=("system_events", "cgevent"),
        default="system_events",
        help="Key injection backend",
    )
    run_parser.add_argument("--output-dir", help="Directory for captured PNG files")
    run_parser.add_argument("--pages", type=int, required=True, help="Number of pages to capture")
    run_parser.add_argument("--settle-delay", type=float, default=1.0, help="Delay after each page turn")
    run_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "windows":
        return handle_windows(args)
    if args.command == "session":
        return handle_session(args)
    if args.command == "capture":
        return handle_capture(args)
    if args.command == "ocr":
        return handle_ocr(args)
    if args.command == "tts":
        return handle_tts(args)
    if args.command == "merge":
        return handle_merge(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def handle_windows(args: argparse.Namespace) -> int:
    try:
        detector = MacOSWindowDetector()
    except WindowingUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.windows_command == "list":
        windows = detector.list_windows(on_screen_only=not args.all)
        if args.json:
            print(detector.dumps(windows))
        else:
            print(render_window_table(windows))
        return 0

    if args.windows_command == "detect":
        windows = detector.find_kindle_windows()
        if args.json:
            print(detector.dumps(windows))
        else:
            print(render_kindle_summary(windows))
        return 0

    print(f"error: unknown windows subcommand: {args.windows_command}", file=sys.stderr)
    return 2


def handle_session(args: argparse.Namespace) -> int:
    manager = SessionManager()

    if args.session_command == "create":
        session = manager.create(title=args.title)
        if args.json:
            print(json.dumps(session.metadata | {"root": str(session.root)}, ensure_ascii=False, indent=2))
        else:
            print(f"Created session: {session.session_id}")
            print(f"Path: {session.root}")
        return 0

    if args.session_command == "list":
        sessions = manager.list_sessions()
        if not sessions:
            print("No sessions found.")
            return 0
        for session in sessions:
            title = session.metadata.get("title") or "-"
            status = session.metadata.get("status") or "-"
            print(f"{session.session_id}  {status}  {title}")
        return 0

    if args.session_command == "show":
        try:
            session = manager.load(args.session)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        payload = session.metadata | {"root": str(session.root)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(f"error: unknown session subcommand: {args.session_command}", file=sys.stderr)
    return 2


def handle_ocr(args: argparse.Namespace) -> int:
    if args.ocr_command != "run":
        print(f"error: unknown ocr subcommand: {args.ocr_command}", file=sys.stderr)
        return 2

    manager = SessionManager()
    try:
        session = manager.load(args.session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    image_paths = sorted(manager.capture_raw_dir(session).glob("page_*.png"))
    if not image_paths:
        print("error: no captured PNG files found for session", file=sys.stderr)
        return 1

    runner = PaddleOcrRunner(lang=args.lang)
    try:
        result = runner.run_for_session(
            session_id=session.session_id,
            image_paths=image_paths,
            raw_dir=manager.ocr_raw_dir(session),
            normalized_dir=manager.ocr_normalized_dir(session),
            combined_path=manager.ocr_combined_path(session),
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    session.metadata["status"] = "ocr_completed"
    ocr_meta = session.metadata.setdefault("ocr", {})
    if isinstance(ocr_meta, dict):
        ocr_meta["provider"] = "paddleocr"
        ocr_meta["language"] = args.lang
        ocr_meta["page_count"] = len(result.pages)
    manager.save(session)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_ocr_run_result(result))
    return 0


def handle_tts(args: argparse.Namespace) -> int:
    if args.tts_command != "run":
        print(f"error: unknown tts subcommand: {args.tts_command}", file=sys.stderr)
        return 2

    manager = SessionManager()
    try:
        session = manager.load(args.session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    input_text = manager.ocr_combined_path(session)
    if not input_text.exists():
        print("error: OCR combined.txt not found for session", file=sys.stderr)
        return 1

    runner = VoicevoxTtsRunner(base_url=args.base_url, max_chars=args.max_chars)
    try:
        result = runner.run_for_session(
            session_id=session.session_id,
            input_text_path=input_text,
            chunks_dir=manager.tts_chunks_dir(session),
            wav_dir=manager.tts_wav_dir(session),
            manifest_path=manager.tts_manifest_path(session),
            speaker=args.speaker,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    session.metadata["status"] = "tts_completed"
    tts_meta = session.metadata.setdefault("tts", {})
    if isinstance(tts_meta, dict):
        tts_meta["provider"] = "voicevox"
        tts_meta["speaker"] = args.speaker
        tts_meta["chunk_count"] = len(result.chunks)
    manager.save(session)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_tts_run_result(result))
    return 0


def handle_merge(args: argparse.Namespace) -> int:
    if args.merge_command != "run":
        print(f"error: unknown merge subcommand: {args.merge_command}", file=sys.stderr)
        return 2

    manager = SessionManager()
    try:
        session = manager.load(args.session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    wav_paths = sorted(manager.tts_wav_dir(session).glob("chunk_*.wav"))
    if not wav_paths:
        print("error: no TTS WAV files found for session", file=sys.stderr)
        return 1

    merger = AudioMerger()
    try:
        result = merger.run(
            wav_paths=wav_paths,
            merged_wav_path=manager.output_merged_wav_path(session),
            output_mp3_path=manager.output_mp3_path(session),
            output_m4a_path=manager.output_m4a_path(session),
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    session.metadata["status"] = "merge_completed"
    output_meta = session.metadata.setdefault("output", {})
    if isinstance(output_meta, dict):
        output_meta["mp3_path"] = str(result.output_audio_path) if result.output_format == "mp3" else None
        output_meta["audio_path"] = str(result.output_audio_path)
        output_meta["audio_format"] = result.output_format
    manager.save(session)

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_merge_run_result(result))
    return 0


def handle_capture(args: argparse.Namespace) -> int:
    try:
        detector = MacOSWindowDetector()
    except WindowingUnavailableError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        window = resolve_target_window(detector, args.window_id)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.capture_command == "shot":
        capture = WindowCapture()
        try:
            path = capture.save_window_screenshot(window, args.output)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Saved screenshot: {path}")
        return 0

    if args.capture_command == "probe-key":
        key_name, key_code = resolve_key_spec(args.key)
        probe = KeyPressProbe(settle_delay=args.settle_delay, transport=args.transport)
        try:
            result = probe.probe(
                window,
                key_name=key_name,
                key_code=key_code,
                output_dir=args.output_dir,
            )
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_key_probe_result(result))
        return 0

    if args.capture_command == "run":
        key_name, key_code = resolve_key_spec(args.key)
        runner = PageCaptureRunner(settle_delay=args.settle_delay, transport=args.transport)
        output_dir: str | Path
        session = None
        if args.session:
            manager = SessionManager()
            try:
                session = manager.load(args.session)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            output_dir = manager.capture_raw_dir(session)
        elif args.output_dir:
            output_dir = args.output_dir
        else:
            print("error: either --session or --output-dir is required", file=sys.stderr)
            return 1
        try:
            result = runner.run(
                window,
                key_name=key_name,
                key_code=key_code,
                output_dir=output_dir,
                pages=args.pages,
            )
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if session is not None:
            manager = SessionManager()
            session.metadata["status"] = "capture_completed"
            capture_meta = session.metadata.setdefault("capture", {})
            if isinstance(capture_meta, dict):
                capture_meta["key"] = key_name
                capture_meta["transport"] = args.transport
                capture_meta["page_count"] = len(result.saved_paths)
            manager.save(session)
        if args.json:
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            print(render_capture_run_result(result))
        return 0

    print(f"error: unknown capture subcommand: {args.capture_command}", file=sys.stderr)
    return 2


def resolve_target_window(detector: MacOSWindowDetector, window_id: int | None):
    if window_id is None:
        window = detector.detect_primary_kindle_window()
        if window is None:
            raise RuntimeError("No Kindle window detected")
        return window

    for window in detector.list_windows(on_screen_only=False, min_width=0, min_height=0):
        if window.window_id == window_id:
            return window
    raise RuntimeError(f"Window id {window_id} not found")


def resolve_key_spec(key_name: str) -> tuple[str, int]:
    key_codes = {
        "left": 123,
        "right": 124,
        "space": 49,
    }
    return key_name, key_codes[key_name]


def render_window_table(windows: list) -> str:
    if not windows:
        return "No windows found."

    headers = ("window_id", "owner", "title", "width", "height", "x", "y")
    rows = [headers]
    for window in windows:
        rows.append(
            (
                str(window.window_id),
                window.owner_name,
                window.title or "<untitled>",
                str(window.width),
                str(window.height),
                str(window.bounds["X"]),
                str(window.bounds["Y"]),
            )
        )

    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )


def render_kindle_summary(windows: list) -> str:
    if not windows:
        return "No Kindle windows detected."

    primary = windows[0]
    lines = [
        f"Detected {len(windows)} Kindle window(s).",
        f"Primary window: id={primary.window_id} title={primary.title or '<untitled>'} size={primary.width}x{primary.height}",
    ]
    if len(windows) > 1:
        for window in windows[1:]:
            lines.append(
                f"Candidate: id={window.window_id} title={window.title or '<untitled>'} size={window.width}x{window.height}"
            )
    return "\n".join(lines)


def render_key_probe_result(result) -> str:
    lines = [
        f"Key: {result.key_name} ({result.key_code})",
        f"Transport: {result.transport}",
        f"Frontmost before: {result.frontmost_before or 'unknown'}",
        f"Frontmost after: {result.frontmost_after or 'unknown'}",
        f"Baseline: {Path(result.baseline_path)}",
        f"Candidate: {Path(result.candidate_path)}",
        f"Content diff: {result.diff_score:.4f}",
    ]
    return "\n".join(lines)


def render_capture_run_result(result) -> str:
    lines = [
        f"Captured {len(result.saved_paths)} page(s).",
        f"Key: {result.key_name} ({result.key_code})",
        f"Transport: {result.transport}",
        f"Output directory: {result.output_dir}",
    ]
    if result.saved_paths:
        lines.append(f"First file: {result.saved_paths[0].name}")
        lines.append(f"Last file: {result.saved_paths[-1].name}")
    return "\n".join(lines)


def render_ocr_run_result(result) -> str:
    lines = [
        f"OCR completed for {len(result.pages)} page(s).",
        f"Provider: {result.provider}",
        f"Language: {result.language}",
        f"Raw directory: {result.raw_dir}",
        f"Normalized directory: {result.normalized_dir}",
        f"Combined text: {result.combined_path}",
    ]
    return "\n".join(lines)


def render_tts_run_result(result) -> str:
    lines = [
        f"TTS completed for {len(result.chunks)} chunk(s).",
        f"Speaker: {result.speaker}",
        f"Base URL: {result.base_url}",
        f"Chunks directory: {result.chunks_dir}",
        f"WAV directory: {result.wav_dir}",
        f"Manifest: {result.manifest_path}",
    ]
    return "\n".join(lines)


def render_merge_run_result(result) -> str:
    lines = [
        f"Merged {result.input_count} WAV file(s).",
        f"Merged WAV: {result.merged_wav_path}",
        f"Output audio: {result.output_audio_path}",
        f"Format: {result.output_format}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
