"""GAB-103: what an action finished before Stop is kept, and the person is told."""

import tempfile
import time
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.action import clear
from ox1audio.cli import tone

from hosting import Host


class StopKeepsTest(unittest.TestCase):
    def setUp(self):
        clear()
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        self.song = self.folder / "song.wav"
        self.song.write_bytes(tone(1.0))

    def tearDown(self):
        self.dir.cleanup()

    hold = False

    def convert_action(self):
        @ox.action("Convert")
        def convert(files: ox.Files("audio"), formats: ox.Choice("wav", "flac", "mp3", multiple=True)):
            made = []
            for i, kind in enumerate(formats):
                ox.progress(i / len(formats), kind)
                if kind == "mp3" and self.hold:
                    while True:  # a long step: only Stop ends it
                        ox.progress(i / len(formats), kind)
                        time.sleep(0.01)
                out = ox.audio.convert(files[0], kind, folder=self.folder, on_progress=lambda f, i=i: ox.progress((i + f) / len(formats), kind))
                made.append(ox.sound(out, title=f"song {kind}"))
            return made

        return convert

    def test_stop_keeps_what_was_finished_and_says_so(self):
        convert = self.convert_action()
        with self.assertRaises(ox.Cancelled) as stopped:
            ox.test(convert, files=[self.song], formats=["wav", "flac", "mp3"], stop_at=0.67)
        kept = stopped.exception.kept
        self.assertEqual([Path(item["path"]).suffix for item in kept], [".wav", ".flac"])
        self.assertEqual([item["title"] for item in kept], ["song wav", "song flac"])
        self.assertTrue(all(item["id"] for item in kept), "kept items reached the Library")
        self.assertFalse((self.folder / "song.mp3").exists(), "the unfinished file is not left behind")

    def test_stop_before_anything_finished_keeps_nothing(self):
        @ox.action("Wait")
        def wait():
            made = [ox.sound(self.folder / "not-written.wav", title="never")]
            while True:
                ox.progress(0.9, "Waiting")
            return made

        with self.assertRaises(ox.Cancelled) as stopped:
            ox.test(wait, stop_at=0.5)
        self.assertEqual(stopped.exception.kept, [])

    def test_the_cancelled_error_lists_what_was_kept(self):
        self.hold = True
        self.convert_action()
        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 3, "action": "convert", "input": {"files": [str(self.song)], "formats": ["wav", "flac", "mp3"]}})
            added = 0
            while True:
                message = host.recv()
                if message["type"] == "progress" and message["label"] == "mp3":
                    host.send({"type": "cancel", "id": 3})
                if message["type"] == "library":
                    added += 1
                    host.send({"type": "library-result", "rid": message["rid"], "status": 200, "body": {"id": str(added), "kind": "sound", "title": message["title"]}})
                if message["type"] == "error" and message["id"] == 3:
                    error = message["error"]
                    break
            self.assertEqual(error["code"], "cancelled")
            self.assertEqual(error["message"], "Stopped. Kept 2: song 2.wav, song.flac.")
            self.assertEqual([item["id"] for item in error["kept"]], ["1", "2"])
        finally:
            host.close()


if __name__ == "__main__":
    unittest.main()
