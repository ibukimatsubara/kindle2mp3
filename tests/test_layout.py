import unittest

from kindle2mp3.layout import LayoutRegion, BODY_LABELS, SKIP_LABELS


class LayoutRegionTest(unittest.TestCase):
    def test_body_label_is_body(self) -> None:
        for label in BODY_LABELS:
            region = LayoutRegion(label=label, score=0.9, bbox=(0, 0, 100, 100))
            self.assertTrue(region.is_body, f"{label} should be body")

    def test_skip_label_is_not_body(self) -> None:
        for label in SKIP_LABELS:
            region = LayoutRegion(label=label, score=0.9, bbox=(0, 0, 100, 100))
            self.assertFalse(region.is_body, f"{label} should not be body")

    def test_to_dict(self) -> None:
        region = LayoutRegion(label="plain text", score=0.95, bbox=(10, 20, 300, 400))
        d = region.to_dict()
        self.assertEqual(d["label"], "plain text")
        self.assertEqual(d["bbox"], [10, 20, 300, 400])
        self.assertTrue(d["is_body"])


if __name__ == "__main__":
    unittest.main()
