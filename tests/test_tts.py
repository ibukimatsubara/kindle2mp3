import unittest

from kindle2mp3.tts import TextChunker


class TextChunkerTest(unittest.TestCase):
    def test_split_breaks_on_sentence_boundaries(self) -> None:
        chunker = TextChunker(max_chars=12)
        chunks = chunker.split("これは一文目です。これは二文目です。")

        self.assertEqual(chunks, ["これは一文目です。", "これは二文目です。"])

    def test_split_groups_short_sentences(self) -> None:
        chunker = TextChunker(max_chars=30)
        chunks = chunker.split("短いです。これも短いです。")

        self.assertEqual(chunks, ["短いです。\nこれも短いです。"])


if __name__ == "__main__":
    unittest.main()
