import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from kindle2mp3.capture import compute_content_difference, compute_image_difference


class CaptureTest(unittest.TestCase):
    def test_compute_image_difference_detects_changed_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            left_path = Path(tmp_dir) / "left.png"
            right_path = Path(tmp_dir) / "right.png"

            left = Image.new("RGB", (120, 120), "white")
            left.save(left_path)

            right = Image.new("RGB", (120, 120), "white")
            draw = ImageDraw.Draw(right)
            draw.rectangle((20, 20, 100, 100), fill="black")
            right.save(right_path)

            diff = compute_image_difference(left_path, right_path)

            self.assertGreater(diff, 0.1)

    def test_compute_content_difference_detects_center_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            left_path = Path(tmp_dir) / "left.png"
            right_path = Path(tmp_dir) / "right.png"

            left = Image.new("RGB", (300, 300), "white")
            left.save(left_path)

            right = Image.new("RGB", (300, 300), "white")
            draw = ImageDraw.Draw(right)
            draw.rectangle((110, 110, 190, 190), fill="black")
            right.save(right_path)

            diff = compute_content_difference(left_path, right_path)

            self.assertGreater(diff, 0.1)


if __name__ == "__main__":
    unittest.main()
