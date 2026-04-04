import unittest

from kindle2mp3.clean import TextCleaner, _fix_katakana_long_vowel


class KatakanaLongVowelTest(unittest.TestCase):
    def test_between_katakana(self) -> None:
        self.assertEqual(_fix_katakana_long_vowel("チ一ム"), "チーム")

    def test_at_end(self) -> None:
        self.assertEqual(_fix_katakana_long_vowel("メンバ一"), "メンバー")

    def test_multiple(self) -> None:
        self.assertEqual(
            _fix_katakana_long_vowel("コ一ドレビュ一"),
            "コードレビュー",
        )

    def test_kanji_one_preserved(self) -> None:
        # 一 between kanji should not be replaced
        self.assertEqual(_fix_katakana_long_vowel("一番"), "一番")
        self.assertEqual(_fix_katakana_long_vowel("統一"), "統一")


class TextCleanerTest(unittest.TestCase):
    def test_removes_blank_lines(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("一行目\n\n\n二行目")
        self.assertEqual(result, "一行目\n二行目")

    def test_fixes_katakana_long_vowel(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("コードレビュ一でのチ一ムワーク")
        self.assertEqual(result, "コードレビューでのチームワーク")

    def test_fixes_similar_chars(self) -> None:
        cleaner = TextCleaner()
        self.assertIn("バージョン", cleaner.clean_page("バージョソ管理"))
        self.assertIn("プラット", cleaner.clean_page("プラツトフォーム"))
        self.assertIn("コミット", cleaner.clean_page("コミツトを積む"))

    def test_collapses_spaces(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean_page("テスト　　テスト")
        self.assertEqual(result, "テスト テスト")


if __name__ == "__main__":
    unittest.main()
