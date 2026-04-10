from __future__ import annotations

from pathlib import Path


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
    if result.stop_reason:
        lines.append(f"Stop reason: {result.stop_reason}")
    if result.saved_paths:
        lines.append(f"First file: {result.saved_paths[0].name}")
        lines.append(f"Last file: {result.saved_paths[-1].name}")
    return "\n".join(lines)


def render_ocr_run_result(result) -> str:
    lines = [
        f"OCR completed for {len(result.pages)} page(s).",
        f"Provider: {result.provider}",
        f"Raw directory: {result.raw_dir}",
        f"Text directory: {result.text_dir}",
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
