import unittest

from kindle2mp3.clean import TextCleaner


class TextCleanerTest(unittest.TestCase):
    def test_removes_blank_lines(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("一行目。\n\n\n二行目。")
        self.assertEqual(result, "一行目。\n二行目。")

    def test_collapses_spaces(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("テスト　　テスト")
        self.assertEqual(result, "テスト テスト")

    def test_joins_line_wraps_into_sentences(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page(
            "コミュニケーションに焦点を当てて\n"
            "います。コードレビューでのやりとりは、\n"
            "開発の質を左右する重要なプロセスです。"
        )
        self.assertEqual(
            result,
            "コミュニケーションに焦点を当てています。\n"
            "コードレビューでのやりとりは、開発の質を左右する重要なプロセスです。"
        )

    def test_short_complete_line_stays_separate(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("一行目です。\n二行目です。")
        self.assertEqual(result, "一行目です。\n二行目です。")

    def test_tilde_normalization(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("テスト～テスト。")
        self.assertIn("〜", result)
        self.assertNotIn("～", result)


if __name__ == "__main__":
    unittest.main()
