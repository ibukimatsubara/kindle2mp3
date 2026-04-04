from __future__ import annotations

from kindle2mp3.capture import PageCaptureRunner
from kindle2mp3.clean import TextCleaner
from kindle2mp3.layout import DocLayoutDetector
from kindle2mp3.merge import AudioMerger
from kindle2mp3.ocr import PaddleOcrRunner
from kindle2mp3.sessions import Session, SessionManager
from kindle2mp3.tts import VoicevoxTtsRunner


def run_capture_stage(
    *,
    manager: SessionManager,
    session: Session,
    window,
    key_name: str,
    key_code: int,
    transport: str,
    settle_delay: float,
    pages: int | None,
    stop_after_no_change: int,
):
    runner = PageCaptureRunner(settle_delay=settle_delay, transport=transport)
    result = runner.run(
        window,
        key_name=key_name,
        key_code=key_code,
        output_dir=manager.capture_raw_dir(session),
        pages=pages,
        stop_after_no_change=stop_after_no_change,
    )

    session.metadata["status"] = "capture_completed"
    capture_meta = session.metadata.setdefault("capture", {})
    if isinstance(capture_meta, dict):
        capture_meta["key"] = key_name
        capture_meta["transport"] = transport
        capture_meta["page_count"] = len(result.saved_paths)
    manager.save(session)
    return result


def run_layout_stage(*, manager: SessionManager, session: Session):
    image_paths = sorted(manager.capture_raw_dir(session).glob("page_*.png"))
    if not image_paths:
        raise RuntimeError("no captured PNG files found for session")

    detector = DocLayoutDetector()
    result = detector.run_for_session(
        session_id=session.session_id,
        image_paths=image_paths,
        layout_dir=manager.layout_dir(session),
    )

    session.metadata["status"] = "layout_completed"
    layout_meta = session.metadata.setdefault("layout", {})
    if isinstance(layout_meta, dict):
        layout_meta["provider"] = "doclayout-yolo"
        layout_meta["page_count"] = len(result.pages)
        layout_meta["total_body_regions"] = sum(
            len(p.body_regions) for p in result.pages
        )
    manager.save(session)
    return result


def run_ocr_stage(*, manager: SessionManager, session: Session, lang: str):
    image_paths = sorted(manager.capture_raw_dir(session).glob("page_*.png"))
    if not image_paths:
        raise RuntimeError("no captured PNG files found for session")

    runner = PaddleOcrRunner(lang=lang)
    result = runner.run_for_session(
        session_id=session.session_id,
        image_paths=image_paths,
        layout_dir=manager.layout_dir(session),
        raw_dir=manager.ocr_raw_dir(session),
        text_dir=manager.ocr_text_dir(session),
    )

    session.metadata["status"] = "ocr_completed"
    ocr_meta = session.metadata.setdefault("ocr", {})
    if isinstance(ocr_meta, dict):
        ocr_meta["provider"] = "paddleocr"
        ocr_meta["language"] = lang
        ocr_meta["page_count"] = len(result.pages)
    manager.save(session)
    return result


def run_clean_stage(*, manager: SessionManager, session: Session):
    cleaner = TextCleaner()
    result = cleaner.run_for_session(
        session_id=session.session_id,
        text_dir=manager.ocr_text_dir(session),
        clean_dir=manager.ocr_clean_dir(session),
        combined_path=manager.ocr_combined_path(session),
    )

    session.metadata["status"] = "clean_completed"
    clean_meta = session.metadata.setdefault("clean", {})
    if isinstance(clean_meta, dict):
        clean_meta["page_count"] = len(result.pages)
        clean_meta["combined_path"] = str(result.combined_path)
    manager.save(session)
    return result


def run_tts_stage(
    *,
    manager: SessionManager,
    session: Session,
    speaker: int,
    base_url: str,
    max_chars: int,
):
    input_text = manager.ocr_combined_path(session)
    if not input_text.exists():
        raise RuntimeError("OCR combined.txt not found for session")

    runner = VoicevoxTtsRunner(base_url=base_url, max_chars=max_chars)
    result = runner.run_for_session(
        session_id=session.session_id,
        input_text_path=input_text,
        chunks_dir=manager.tts_chunks_dir(session),
        wav_dir=manager.tts_wav_dir(session),
        manifest_path=manager.tts_manifest_path(session),
        speaker=speaker,
    )

    session.metadata["status"] = "tts_completed"
    tts_meta = session.metadata.setdefault("tts", {})
    if isinstance(tts_meta, dict):
        tts_meta["provider"] = "voicevox"
        tts_meta["speaker"] = speaker
        tts_meta["chunk_count"] = len(result.chunks)
    manager.save(session)
    return result


def run_merge_stage(*, manager: SessionManager, session: Session):
    wav_paths = sorted(manager.tts_wav_dir(session).glob("chunk_*.wav"))
    if not wav_paths:
        raise RuntimeError("no TTS WAV files found for session")

    merger = AudioMerger()
    result = merger.run(
        wav_paths=wav_paths,
        merged_wav_path=manager.output_merged_wav_path(session),
        output_mp3_path=manager.output_mp3_path(session),
        output_m4a_path=manager.output_m4a_path(session),
    )

    session.metadata["status"] = "merge_completed"
    output_meta = session.metadata.setdefault("output", {})
    if isinstance(output_meta, dict):
        output_meta["mp3_path"] = (
            str(result.output_audio_path) if result.output_format == "mp3" else None
        )
        output_meta["audio_path"] = str(result.output_audio_path)
        output_meta["audio_format"] = result.output_format
    manager.save(session)
    return result
