from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def _load_dotenv() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()

from kindle2mp3.capture import (
    PageCaptureRunner,
    KeyPressProbe,
    WindowCapture,
)
from kindle2mp3.defaults import (
    DEFAULT_KEY,
    DEFAULT_SPEAKER,
    DEFAULT_STOP_AFTER_NO_CHANGE,
    DEFAULT_TRANSPORT,
    DEFAULT_VOICEVOX_BASE_URL,
)
from kindle2mp3.pipeline import (
    run_capture_stage,
    run_clean_stage,
    run_layout_stage,
    run_llm_fix_stage,
    run_merge_stage,
    run_ocr_stage,
    run_tts_stage,
)
from kindle2mp3.presenters import (
    render_capture_run_result,
    render_key_probe_result,
    render_kindle_summary,
    render_merge_run_result,
    render_ocr_run_result,
    render_tts_run_result,
    render_window_table,
)
from kindle2mp3.sessions import SessionManager
from kindle2mp3.windowing import MacOSWindowDetector, WindowingUnavailableError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kindle2mp3")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run capture, OCR, TTS, and merge in one command")
    run_parser.add_argument("--session", help="Existing session id, e.g. book_0001")
    run_parser.add_argument("--title", help="Session title when creating a new session")
    run_parser.add_argument("--window-id", type=int, help="Explicit macOS window id")
    run_parser.add_argument("--key", choices=("left", "right", "space"), default=DEFAULT_KEY)
    run_parser.add_argument(
        "--transport",
        choices=("system_events", "cgevent"),
        default=DEFAULT_TRANSPORT,
        help="Key injection backend",
    )
    run_parser.add_argument("--pages", type=int, help="Number of pages to capture")
    run_parser.add_argument(
        "--stop-after-no-change",
        type=int,
        default=DEFAULT_STOP_AFTER_NO_CHANGE,
        help="Stop after this many consecutive no-change turns when --pages is omitted",
    )
    run_parser.add_argument("--lang", default="japan", help="PaddleOCR language code")
    run_parser.add_argument("--speaker", type=int, default=DEFAULT_SPEAKER, help="VOICEVOX speaker style id")
    run_parser.add_argument("--base-url", default=DEFAULT_VOICEVOX_BASE_URL, help="VOICEVOX Engine base URL")
    run_parser.add_argument("--max-chars", type=int, default=180, help="Maximum characters per chunk")
    run_parser.add_argument("--settle-delay", type=float, default=1.0, help="Delay after each page turn")
    run_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

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

    layout_parser = subparsers.add_parser("layout", help="Detect page layout regions")
    layout_subparsers = layout_parser.add_subparsers(dest="layout_command", required=True)

    layout_run = layout_subparsers.add_parser("run", help="Run layout detection for a session")
    layout_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    layout_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    ocr_parser = subparsers.add_parser("ocr", help="Run OCR on captured session images")
    ocr_subparsers = ocr_parser.add_subparsers(dest="ocr_command", required=True)

    ocr_run = ocr_subparsers.add_parser("run", help="Run OCR for a session")
    ocr_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    ocr_run.add_argument("--lang", default="japan", help="PaddleOCR language code")
    ocr_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    clean_parser = subparsers.add_parser("clean", help="Clean and normalize OCR text")
    clean_subparsers = clean_parser.add_subparsers(dest="clean_command", required=True)

    clean_run = clean_subparsers.add_parser("run", help="Clean OCR text for a session")
    clean_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    clean_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    llm_fix_parser = subparsers.add_parser("llm-fix", help="Fix OCR text using Gemini API")
    llm_fix_subparsers = llm_fix_parser.add_subparsers(dest="llm_fix_command", required=True)

    llm_fix_run = llm_fix_subparsers.add_parser("run", help="Run LLM fix for a session")
    llm_fix_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    llm_fix_run.add_argument("--model", default="gemini-2.5-flash-lite", help="Gemini model name")
    llm_fix_run.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    tts_parser = subparsers.add_parser("tts", help="Run TTS for OCR text")
    tts_subparsers = tts_parser.add_subparsers(dest="tts_command", required=True)

    merge_parser = subparsers.add_parser("merge", help="Merge generated WAV files into a final MP3")
    merge_subparsers = merge_parser.add_subparsers(dest="merge_command", required=True)

    tts_run = tts_subparsers.add_parser("run", help="Run VOICEVOX TTS for a session")
    tts_run.add_argument("--session", required=True, help="Session id, e.g. book_0001")
    tts_run.add_argument("--speaker", type=int, default=DEFAULT_SPEAKER, help="VOICEVOX speaker style id")
    tts_run.add_argument("--base-url", default=DEFAULT_VOICEVOX_BASE_URL, help="VOICEVOX Engine base URL")
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
    run_parser.add_argument("--key", choices=("left", "right", "space"), default=DEFAULT_KEY)
    run_parser.add_argument(
        "--transport",
        choices=("system_events", "cgevent"),
        default=DEFAULT_TRANSPORT,
        help="Key injection backend",
    )
    run_parser.add_argument("--output-dir", help="Directory for captured PNG files")
    run_parser.add_argument("--pages", type=int, help="Number of pages to capture")
    run_parser.add_argument(
        "--stop-after-no-change",
        type=int,
        default=DEFAULT_STOP_AFTER_NO_CHANGE,
        help="Stop after this many consecutive no-change turns when --pages is omitted",
    )
    run_parser.add_argument("--settle-delay", type=float, default=1.0, help="Delay after each page turn")
    run_parser.add_argument("--json", action="store_true", help="Emit JSON instead of text")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "windows":
        return handle_windows(args)
    if args.command == "run":
        return handle_run(args)
    if args.command == "session":
        return handle_session(args)
    if args.command == "capture":
        return handle_capture(args)
    if args.command == "layout":
        return handle_layout(args)
    if args.command == "ocr":
        return handle_ocr(args)
    if args.command == "clean":
        return handle_clean(args)
    if args.command == "llm-fix":
        return handle_llm_fix(args)
    if args.command == "tts":
        return handle_tts(args)
    if args.command == "merge":
        return handle_merge(args)

    parser.error(f"Unknown command: {args.command}")
    return 2


def handle_run(args: argparse.Namespace) -> int:
    manager = SessionManager()
    if args.session:
        try:
            session = manager.load(args.session)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        session = manager.create(title=args.title)

    # 1. capture
    namespace_capture = argparse.Namespace(
        capture_command="run",
        window_id=args.window_id,
        session=session.session_id,
        key=args.key,
        transport=args.transport,
        output_dir=None,
        pages=args.pages,
        stop_after_no_change=args.stop_after_no_change,
        settle_delay=args.settle_delay,
        json=False,
    )
    capture_status = handle_capture(namespace_capture)
    if capture_status != 0:
        return capture_status

    # 2. layout
    namespace_layout = argparse.Namespace(
        layout_command="run",
        session=session.session_id,
        json=False,
    )
    layout_status = handle_layout(namespace_layout)
    if layout_status != 0:
        return layout_status

    # 3. ocr
    namespace_ocr = argparse.Namespace(
        ocr_command="run",
        session=session.session_id,
        lang=args.lang,
        json=False,
    )
    ocr_status = handle_ocr(namespace_ocr)
    if ocr_status != 0:
        return ocr_status

    # 4. clean
    namespace_clean = argparse.Namespace(
        clean_command="run",
        session=session.session_id,
        json=False,
    )
    clean_status = handle_clean(namespace_clean)
    if clean_status != 0:
        return clean_status

    # 5. llm-fix
    namespace_llm_fix = argparse.Namespace(
        llm_fix_command="run",
        session=session.session_id,
        model="gemini-2.5-flash-lite",
        json=False,
    )
    llm_fix_status = handle_llm_fix(namespace_llm_fix)
    if llm_fix_status != 0:
        return llm_fix_status

    # 6. tts
    namespace_tts = argparse.Namespace(
        tts_command="run",
        session=session.session_id,
        speaker=args.speaker,
        base_url=args.base_url,
        max_chars=args.max_chars,
        json=False,
    )
    tts_status = handle_tts(namespace_tts)
    if tts_status != 0:
        return tts_status

    # 6. merge
    namespace_merge = argparse.Namespace(
        merge_command="run",
        session=session.session_id,
        json=False,
    )
    merge_status = handle_merge(namespace_merge)
    if merge_status != 0:
        return merge_status

    session = manager.load(session.session_id)
    output_meta = session.metadata.get("output", {})
    if not isinstance(output_meta, dict):
        output_meta = {}

    payload = {
        "session_id": session.session_id,
        "status": session.metadata.get("status"),
        "audio_path": output_meta.get("audio_path"),
        "audio_format": output_meta.get("audio_format"),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Completed session: {session.session_id}")
        if payload["audio_path"]:
            print(f"Output: {payload['audio_path']}")
        if payload["audio_format"]:
            print(f"Format: {payload['audio_format']}")
    return 0


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


def handle_layout(args: argparse.Namespace) -> int:
    if args.layout_command != "run":
        print(f"error: unknown layout subcommand: {args.layout_command}", file=sys.stderr)
        return 2

    manager = SessionManager()
    try:
        session = manager.load(args.session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        result = run_layout_stage(manager=manager, session=session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Layout detected for {len(result.pages)} page(s).")
        total_body = sum(len(p.body_regions) for p in result.pages)
        print(f"Total body regions: {total_body}")
    return 0


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

    try:
        result = run_ocr_stage(manager=manager, session=session, lang=args.lang)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(render_ocr_run_result(result))
    return 0


def handle_clean(args: argparse.Namespace) -> int:
    if args.clean_command != "run":
        print(f"error: unknown clean subcommand: {args.clean_command}", file=sys.stderr)
        return 2

    manager = SessionManager()
    try:
        session = manager.load(args.session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        result = run_clean_stage(manager=manager, session=session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"Cleaned {len(result.pages)} page(s).")
        print(f"Combined text: {result.combined_path}")
    return 0


def handle_llm_fix(args: argparse.Namespace) -> int:
    if args.llm_fix_command != "run":
        print(f"error: unknown llm-fix subcommand: {args.llm_fix_command}", file=sys.stderr)
        return 2

    manager = SessionManager()
    try:
        session = manager.load(args.session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        result = run_llm_fix_stage(
            manager=manager,
            session=session,
            model=args.model,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"LLM fix: {result.sentence_count} sentence(s), {result.changed_count} changed.")
        print(f"Fixed text: {result.fixed_path}")
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

    try:
        result = run_tts_stage(
            manager=manager,
            session=session,
            speaker=args.speaker,
            base_url=args.base_url,
            max_chars=args.max_chars,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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

    try:
        result = run_merge_stage(manager=manager, session=session)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

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
        session = None
        if args.session:
            manager = SessionManager()
            try:
                session = manager.load(args.session)
            except RuntimeError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 1
        elif args.output_dir:
            output_dir = args.output_dir
        else:
            print("error: either --session or --output-dir is required", file=sys.stderr)
            return 1
        try:
            if session is not None:
                result = run_capture_stage(
                    manager=manager,
                    session=session,
                    window=window,
                    key_name=key_name,
                    key_code=key_code,
                    transport=args.transport,
                    settle_delay=args.settle_delay,
                    pages=args.pages,
                    stop_after_no_change=args.stop_after_no_change,
                )
            else:
                result = runner.run(
                    window,
                    key_name=key_name,
                    key_code=key_code,
                    output_dir=output_dir,
                    pages=args.pages,
                    stop_after_no_change=args.stop_after_no_change,
                )
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
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


if __name__ == "__main__":
    raise SystemExit(main())
