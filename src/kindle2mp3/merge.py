from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
import wave


@dataclass(slots=True)
class MergeRunResult:
    input_count: int
    merged_wav_path: Path
    output_audio_path: Path
    output_format: str

    def to_dict(self) -> dict[str, object]:
        return {
            "input_count": self.input_count,
            "merged_wav_path": str(self.merged_wav_path),
            "output_audio_path": str(self.output_audio_path),
            "output_format": self.output_format,
        }


class AudioMerger:
    def run(
        self,
        *,
        wav_paths: list[Path],
        merged_wav_path: str | Path,
        output_mp3_path: str | Path,
        output_m4a_path: str | Path,
    ) -> MergeRunResult:
        if not wav_paths:
            raise RuntimeError("No WAV files to merge")

        merged_wav = Path(merged_wav_path)
        output_mp3 = Path(output_mp3_path)
        output_m4a = Path(output_m4a_path)
        merged_wav.parent.mkdir(parents=True, exist_ok=True)
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        output_m4a.parent.mkdir(parents=True, exist_ok=True)

        self._merge_wavs(wav_paths, merged_wav)
        try:
            self._convert_to_mp3(merged_wav, output_mp3)
            output_audio_path = output_mp3
            output_format = "mp3"
        except RuntimeError:
            self._convert_to_m4a(merged_wav, output_m4a)
            output_audio_path = output_m4a
            output_format = "m4a"

        return MergeRunResult(
            input_count=len(wav_paths),
            merged_wav_path=merged_wav,
            output_audio_path=output_audio_path,
            output_format=output_format,
        )

    def _merge_wavs(self, wav_paths: list[Path], output_path: Path) -> None:
        with wave.open(str(wav_paths[0]), "rb") as first:
            params = first.getparams()
            frames = [first.readframes(first.getnframes())]

        for path in wav_paths[1:]:
            with wave.open(str(path), "rb") as current:
                current_params = current.getparams()
                if (
                    current_params.nchannels != params.nchannels
                    or current_params.sampwidth != params.sampwidth
                    or current_params.framerate != params.framerate
                    or current_params.comptype != params.comptype
                ):
                    raise RuntimeError(f"Incompatible WAV parameters: {path}")
                frames.append(current.readframes(current.getnframes()))

        with wave.open(str(output_path), "wb") as merged:
            merged.setparams(params)
            for chunk in frames:
                merged.writeframes(chunk)

    def _convert_to_mp3(self, wav_path: Path, output_path: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            completed = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(wav_path),
                    "-codec:a",
                    "libmp3lame",
                    "-q:a",
                    "2",
                    str(output_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode == 0:
                return

        completed = subprocess.run(
            [
                "afconvert",
                str(wav_path),
                "-o",
                str(output_path),
                "-f",
                "MPG3",
                "-d",
                ".mp3",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"mp3 conversion failed: {completed.stderr.strip()}")

    def _convert_to_m4a(self, wav_path: Path, output_path: Path) -> None:
        completed = subprocess.run(
            [
                "afconvert",
                str(wav_path),
                "-o",
                str(output_path),
                "-f",
                "m4af",
                "-d",
                "aac",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"afconvert failed: {completed.stderr.strip()}")
