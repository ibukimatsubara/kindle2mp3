from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？!?])")


@dataclass(slots=True)
class TtsChunk:
    index: int
    text: str
    text_path: Path
    wav_path: Path


@dataclass(slots=True)
class TtsRunResult:
    session_id: str
    speaker: int
    base_url: str
    chunks_dir: Path
    wav_dir: Path
    manifest_path: Path
    chunks: list[TtsChunk]

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "speaker": self.speaker,
            "base_url": self.base_url,
            "chunks_dir": str(self.chunks_dir),
            "wav_dir": str(self.wav_dir),
            "manifest_path": str(self.manifest_path),
            "chunk_count": len(self.chunks),
        }


class TextChunker:
    def __init__(self, *, max_chars: int = 180) -> None:
        self.max_chars = max_chars

    def split(self, text: str) -> list[str]:
        sentences = [sentence.strip() for sentence in self._split_sentences(text) if sentence.strip()]
        chunks: list[str] = []
        current = ""

        for sentence in sentences:
            if len(sentence) > self.max_chars:
                for piece in self._split_long_sentence(sentence):
                    current = self._append_piece(current, piece, chunks)
                continue
            current = self._append_piece(current, sentence, chunks)

        if current:
            chunks.append(current)
        return chunks

    def _append_piece(self, current: str, piece: str, chunks: list[str]) -> str:
        if not current:
            return piece
        candidate = f"{current}\n{piece}"
        if len(candidate) <= self.max_chars:
            return candidate
        chunks.append(current)
        return piece

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n")
        parts: list[str] = []
        for paragraph in normalized.split("\n"):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            parts.extend(part for part in SENTENCE_BOUNDARY_RE.split(paragraph) if part)
        return parts

    def _split_long_sentence(self, sentence: str) -> list[str]:
        pieces: list[str] = []
        current = ""
        for fragment in re.split(r"(?<=、)", sentence):
            fragment = fragment.strip()
            if not fragment:
                continue
            if not current:
                current = fragment
                continue
            candidate = current + fragment
            if len(candidate) <= self.max_chars:
                current = candidate
            else:
                pieces.append(current)
                current = fragment
        if current:
            pieces.append(current)
        return pieces


class VoicevoxTtsRunner:
    def __init__(self, *, base_url: str = "http://127.0.0.1:50021", max_chars: int = 180) -> None:
        self.base_url = base_url.rstrip("/")
        self.chunker = TextChunker(max_chars=max_chars)

    def run_for_session(
        self,
        *,
        session_id: str,
        input_text_path: str | Path,
        chunks_dir: str | Path,
        wav_dir: str | Path,
        manifest_path: str | Path,
        speaker: int,
    ) -> TtsRunResult:
        input_path = Path(input_text_path)
        source_text = input_path.read_text(encoding="utf-8")
        chunk_texts = self.chunker.split(source_text)

        chunks_dir_path = Path(chunks_dir)
        wav_dir_path = Path(wav_dir)
        manifest_path_obj = Path(manifest_path)
        chunks_dir_path.mkdir(parents=True, exist_ok=True)
        wav_dir_path.mkdir(parents=True, exist_ok=True)
        manifest_path_obj.parent.mkdir(parents=True, exist_ok=True)

        chunks: list[TtsChunk] = []
        manifest_items: list[dict[str, object]] = []

        total_chunks = len(chunk_texts)
        for index, chunk_text in enumerate(chunk_texts, start=1):
            print(f"  tts chunk {index}/{total_chunks}", flush=True)
            text_path = chunks_dir_path / f"chunk_{index:06d}.txt"
            wav_path = wav_dir_path / f"chunk_{index:06d}.wav"
            text_path.write_text(chunk_text + "\n", encoding="utf-8")
            wav_bytes = self._synthesize(chunk_text, speaker=speaker)
            wav_path.write_bytes(wav_bytes)

            chunk = TtsChunk(index=index, text=chunk_text, text_path=text_path, wav_path=wav_path)
            chunks.append(chunk)
            manifest_items.append(
                {
                    "index": index,
                    "text_path": str(text_path),
                    "wav_path": str(wav_path),
                    "char_count": len(chunk_text),
                }
            )

        manifest = {
            "session_id": session_id,
            "speaker": speaker,
            "base_url": self.base_url,
            "chunk_count": len(chunks),
            "chunks": manifest_items,
        }
        manifest_path_obj.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        return TtsRunResult(
            session_id=session_id,
            speaker=speaker,
            base_url=self.base_url,
            chunks_dir=chunks_dir_path,
            wav_dir=wav_dir_path,
            manifest_path=manifest_path_obj,
            chunks=chunks,
        )

    def _synthesize(self, text: str, *, speaker: int) -> bytes:
        query_req = Request(
            self.base_url + "/audio_query?" + urlencode({"text": text, "speaker": speaker}),
            method="POST",
        )
        with urlopen(query_req, timeout=15) as resp:
            query = json.loads(resp.read().decode("utf-8"))

        synthesis_req = Request(
            self.base_url + "/synthesis?" + urlencode({"speaker": speaker}),
            data=json.dumps(query).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(synthesis_req, timeout=60) as resp:
            return resp.read()
