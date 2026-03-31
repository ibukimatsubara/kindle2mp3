from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re


SESSION_ID_RE = re.compile(r"^book_(\d{4})$")


@dataclass(slots=True)
class Session:
    session_id: str
    root: Path
    metadata: dict[str, object]


class SessionManager:
    def __init__(self, workspace_root: str | Path = "workspace") -> None:
        self.workspace_root = Path(workspace_root)

    def create(self, *, title: str | None = None) -> Session:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        session_id = self._next_session_id()
        root = self.workspace_root / session_id
        self._initialize_session_dirs(root)

        metadata = {
            "session_id": session_id,
            "title": title,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "status": "capture_pending",
            "capture": {
                "key": None,
                "transport": "system_events",
                "page_count": 0,
                "image_format": "png",
            },
            "ocr": {
                "provider": "tesseract",
                "languages": ["jpn", "jpn_vert"],
            },
            "tts": {
                "provider": "voicevox",
                "speaker": None,
            },
            "output": {
                "mp3_path": None,
            },
        }
        self._write_metadata(root / "session.json", metadata)
        return Session(session_id=session_id, root=root, metadata=metadata)

    def list_sessions(self) -> list[Session]:
        if not self.workspace_root.exists():
            return []

        sessions: list[Session] = []
        for path in sorted(self.workspace_root.iterdir()):
            if not path.is_dir():
                continue
            if not SESSION_ID_RE.match(path.name):
                continue
            metadata_path = path / "session.json"
            if not metadata_path.exists():
                continue
            metadata = json.loads(metadata_path.read_text())
            sessions.append(Session(session_id=path.name, root=path, metadata=metadata))
        return sessions

    def load(self, session_id: str) -> Session:
        root = self.workspace_root / session_id
        metadata_path = root / "session.json"
        if not metadata_path.exists():
            raise RuntimeError(f"Session not found: {session_id}")
        metadata = json.loads(metadata_path.read_text())
        return Session(session_id=session_id, root=root, metadata=metadata)

    def save(self, session: Session) -> None:
        self._write_metadata(session.root / "session.json", session.metadata)

    def capture_raw_dir(self, session: Session) -> Path:
        return session.root / "capture" / "raw"

    def ocr_raw_dir(self, session: Session) -> Path:
        return session.root / "ocr" / "raw"

    def ocr_normalized_dir(self, session: Session) -> Path:
        return session.root / "ocr" / "normalized"

    def ocr_combined_path(self, session: Session) -> Path:
        return session.root / "ocr" / "combined.txt"

    def tts_chunks_dir(self, session: Session) -> Path:
        return session.root / "tts" / "chunks"

    def tts_wav_dir(self, session: Session) -> Path:
        return session.root / "tts" / "wav"

    def tts_manifest_path(self, session: Session) -> Path:
        return session.root / "tts" / "manifest.json"

    def output_mp3_path(self, session: Session) -> Path:
        return session.root / "output" / "audiobook.mp3"

    def output_merged_wav_path(self, session: Session) -> Path:
        return session.root / "output" / "audiobook.wav"

    def output_m4a_path(self, session: Session) -> Path:
        return session.root / "output" / "audiobook.m4a"

    def _next_session_id(self) -> str:
        max_index = 0
        for session in self.list_sessions():
            match = SESSION_ID_RE.match(session.session_id)
            if match is None:
                continue
            max_index = max(max_index, int(match.group(1)))
        return f"book_{max_index + 1:04d}"

    def _initialize_session_dirs(self, root: Path) -> None:
        for relative in (
            "capture/raw",
            "capture/debug",
            "ocr/raw",
            "ocr/normalized",
            "tts/chunks",
            "tts/wav",
            "output",
            "logs",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _write_metadata(path: Path, metadata: dict[str, object]) -> None:
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
