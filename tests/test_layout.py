import unittest

from kindle2mp3.ndlocr import _BODY_TYPES


class BodyTypesTest(unittest.TestCase):
    def test_body_types_include_expected(self) -> None:
        self.assertIn("本文", _BODY_TYPES)
        self.assertIn("タイトル本文", _BODY_TYPES)

    def test_body_types_exclude_headers(self) -> None:
        self.assertNotIn("柱", _BODY_TYPES)
        self.assertNotIn("ノンブル", _BODY_TYPES)
        self.assertNotIn("図版", _BODY_TYPES)


if __name__ == "__main__":
    unittest.main()
