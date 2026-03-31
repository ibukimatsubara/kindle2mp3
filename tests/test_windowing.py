import unittest

from kindle2mp3.windowing import WindowInfo


class WindowInfoTest(unittest.TestCase):
    def test_window_area_dimensions(self) -> None:
        window = WindowInfo(
            window_id=1,
            owner_name="Kindle",
            owner_pid=100,
            title="Sample",
            bounds={"X": 10, "Y": 20, "Width": 300, "Height": 400},
            layer=0,
            alpha=1.0,
            on_screen=True,
        )

        self.assertEqual(window.width, 300)
        self.assertEqual(window.height, 400)
        self.assertEqual(window.area, 120000)

    def test_window_to_dict_includes_computed_fields(self) -> None:
        window = WindowInfo(
            window_id=2,
            owner_name="Kindle",
            owner_pid=101,
            title="",
            bounds={"X": 0, "Y": 0, "Width": 800, "Height": 600},
            layer=0,
            alpha=1.0,
            on_screen=True,
        )

        payload = window.to_dict()

        self.assertEqual(payload["width"], 800)
        self.assertEqual(payload["height"], 600)
        self.assertEqual(payload["area"], 480000)


if __name__ == "__main__":
    unittest.main()
