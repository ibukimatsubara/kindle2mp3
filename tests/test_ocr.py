import unittest

from kindle2mp3.ocr import PaddleOcrRunner


class PaddleOcrRunnerTest(unittest.TestCase):
    def test_extract_lines_handles_standard_payload(self) -> None:
        payload = [
            [
                [
                    [[0, 0], [10, 0], [10, 10], [0, 10]],
                    ("hello", 0.99),
                ],
                [
                    [[0, 20], [10, 20], [10, 30], [0, 30]],
                    ("world", 0.95),
                ],
            ]
        ]

        lines = PaddleOcrRunner._extract_lines(payload)

        self.assertEqual([line["text"] for line in lines], ["hello", "world"])
        self.assertAlmostEqual(lines[0]["score"], 0.99)


if __name__ == "__main__":
    unittest.main()
