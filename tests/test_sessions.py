import tempfile
import unittest

from kindle2mp3.sessions import SessionManager


class SessionManagerTest(unittest.TestCase):
    def test_create_initializes_session_structure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = SessionManager(tmp_dir)
            session = manager.create(title="Sample")

            self.assertEqual(session.session_id, "book_0001")
            self.assertTrue((session.root / "capture" / "raw").is_dir())
            self.assertTrue((session.root / "output").is_dir())
            self.assertEqual(session.metadata["title"], "Sample")

    def test_create_increments_session_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = SessionManager(tmp_dir)
            first = manager.create()
            second = manager.create()

            self.assertEqual(first.session_id, "book_0001")
            self.assertEqual(second.session_id, "book_0002")


if __name__ == "__main__":
    unittest.main()
