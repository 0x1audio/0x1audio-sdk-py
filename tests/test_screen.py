import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.screen import clear, describe


class ScreenTest(unittest.TestCase):
    def setUp(self):
        clear()

    def test_a_screen_describes_its_controls_and_the_permissions_they_imply(self):
        @ox.screen("Audio Converter")
        def convert(files: ox.Files, format: ox.Choice("wav", "flac")):
            for audio in files:
                yield ox.sound(audio, title="Converted")

        described = describe()
        self.assertEqual(described["screens"][0]["name"], "convert")
        self.assertEqual(described["screens"][0]["fields"][0]["kind"], "files")
        self.assertEqual(described["screens"][0]["fields"][1]["options"], ["wav", "flac"])
        self.assertEqual(described["permissions"], ["files", "library"])

    def test_running_a_screen_records_the_export(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "song.wav"
            source.write_bytes(b"not really")

            @ox.screen("Export")
            def save(files: ox.Files):
                yield ox.sound(files[0], title="Song")

            outcome = ox.test(save, files=[str(source)])
        self.assertEqual(outcome["items"][0]["title"], "Song")
        self.assertEqual(outcome["items"][0]["kind"], "sound")
        self.assertEqual(outcome["result"]["items"][0]["title"], "Song")


if __name__ == "__main__":
    unittest.main()
