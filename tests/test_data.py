import os
import tempfile
import unittest
from pathlib import Path

from ox1audio import data


class DataTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self._tmp.name) / "data"
        os.environ["OX1_DATA"] = str(self.folder)

    def tearDown(self):
        os.environ.pop("OX1_DATA", None)
        self._tmp.cleanup()

    def test_write_read_list_and_remove(self):
        data.write("notes/today.txt", "hello")
        self.assertEqual(data.read_text("notes/today.txt"), "hello")
        self.assertEqual(data.read("notes/today.txt"), b"hello")
        self.assertEqual(data.list(), ["notes"])
        self.assertEqual(data.list("notes"), ["today.txt"])
        data.remove("notes/today.txt")
        self.assertEqual(data.list("notes"), [])
        self.assertTrue(data.root().is_dir())

    def test_a_path_outside_the_folder_is_refused(self):
        with self.assertRaises(ValueError):
            data.read("../secret")
        with self.assertRaises(ValueError):
            data.write("/etc/passwd", "no")
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir()
        link = self.folder / "escape"
        link.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            data.write("escape/note.txt", "no")
        self.assertEqual(list(outside.iterdir()), [])

    def test_missing_folder_is_an_error(self):
        os.environ.pop("OX1_DATA", None)
        with self.assertRaises(RuntimeError):
            data.root()


if __name__ == "__main__":
    unittest.main()
