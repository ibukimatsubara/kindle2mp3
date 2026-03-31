import tempfile
import unittest
import wave
from pathlib import Path

from kindle2mp3.merge import AudioMerger


class AudioMergerTest(unittest.TestCase):
    def test_merge_wavs_concatenates_frames(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            wav1 = base / "a.wav"
            wav2 = base / "b.wav"
            merged = base / "merged.wav"

            self._write_silent_wav(wav1, frame_count=800)
            self._write_silent_wav(wav2, frame_count=1200)

            merger = AudioMerger()
            merger._merge_wavs([wav1, wav2], merged)

            with wave.open(str(merged), "rb") as handle:
                self.assertEqual(handle.getnframes(), 2000)

    @staticmethod
    def _write_silent_wav(path: Path, *, frame_count: int) -> None:
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(b"\x00\x00" * frame_count)


if __name__ == "__main__":
    unittest.main()
