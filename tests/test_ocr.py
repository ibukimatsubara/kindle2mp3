import tempfile
import unittest
from pathlib import Path

from kindle2mp3.ndlocr import parse_xml_body_text, _overlaps_any


SAMPLE_XML = """\
<OCRDATASET>
<PAGE IMAGENAME="page_000001.png" WIDTH="1476" HEIGHT="1778">
  <TEXTBLOCK CONF="0.973">
    <LINE TYPE="本文" X="358" Y="243" WIDTH="714" HEIGHT="20" CONF="0.951" PRED_CHAR_CNT="2.000" ORDER="2" STRING="本文テキストです。" />
    <LINE TYPE="本文" X="339" Y="283" WIDTH="733" HEIGHT="20" CONF="0.945" PRED_CHAR_CNT="2.000" ORDER="3" STRING="二行目のテキストです。" />
  </TEXTBLOCK>
  <TEXTBLOCK CONF="0.419">
    <LINE TYPE="本文" X="697" Y="91" WIDTH="79" HEIGHT="21" CONF="0.311" PRED_CHAR_CNT="1.000" ORDER="0" STRING="Kindle" />
  </TEXTBLOCK>
  <TEXTBLOCK CONF="0.970">
    <LINE TYPE="タイトル本文" X="254" Y="211" WIDTH="225" HEIGHT="22" CONF="0.966" PRED_CHAR_CNT="3.000" ORDER="1" STRING="章タイトル" />
  </TEXTBLOCK>
  <BLOCK TYPE="柱" X="697" Y="91" WIDTH="79" HEIGHT="21" CONF="0.581" />
  <BLOCK TYPE="ノンブル" X="285" Y="1522" WIDTH="18" HEIGHT="16" CONF="0.840" />
</PAGE>
</OCRDATASET>
"""


class ParseXmlBodyTextTest(unittest.TestCase):
    def test_filters_body_and_title_lines(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(SAMPLE_XML)
            f.flush()
            xml_path = Path(f.name)

        text, line_count = parse_xml_body_text(xml_path)
        xml_path.unlink()

        # "Kindle" (ORDER=0) overlaps with 柱 block, should be excluded
        self.assertNotIn("Kindle", text)
        # タイトル本文 (ORDER=1) should be included
        self.assertIn("章タイトル", text)
        # 本文 lines should be included
        self.assertIn("本文テキストです。", text)
        self.assertIn("二行目のテキストです。", text)
        # Should be sorted by ORDER: タイトル, then 本文 lines
        lines = text.strip().split("\n")
        self.assertEqual(lines[0], "章タイトル")
        self.assertEqual(lines[1], "本文テキストです。")
        self.assertEqual(lines[2], "二行目のテキストです。")
        self.assertEqual(line_count, 3)

    def test_empty_xml(self) -> None:
        xml_content = "<OCRDATASET><PAGE></PAGE></OCRDATASET>"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=False) as f:
            f.write(xml_content)
            f.flush()
            xml_path = Path(f.name)

        text, line_count = parse_xml_body_text(xml_path)
        xml_path.unlink()

        self.assertEqual(text, "")
        self.assertEqual(line_count, 0)


class OverlapsTest(unittest.TestCase):
    def test_overlapping(self) -> None:
        self.assertTrue(_overlaps_any(10, 10, 50, 50, [(20, 20, 60, 60)]))

    def test_non_overlapping(self) -> None:
        self.assertFalse(_overlaps_any(10, 10, 50, 50, [(100, 100, 200, 200)]))

    def test_empty_boxes(self) -> None:
        self.assertFalse(_overlaps_any(10, 10, 50, 50, []))


if __name__ == "__main__":
    unittest.main()
