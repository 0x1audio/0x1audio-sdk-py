"""GAB-107: units, a range slider, and files handed over with Open with (ox.beside)."""

import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.action import BadInput, bind, clear, find

from hosting import Host


class UnitAndRangeTest(unittest.TestCase):
    def setUp(self):
        clear()

    def test_a_unit_rides_on_the_hint(self):
        @ox.action("Louder")
        def louder(gain: ox.Slider(0, 12, step=0.5, unit="dB") = 6.0, size: ox.Number(1, 64, step=1, unit="ms") = 8):
            return gain

        props = find(louder).spec()["input"]["properties"]
        self.assertEqual(props["gain"]["x-ox"], {"control": "slider", "step": 0.5, "unit": "dB"})
        self.assertEqual(props["size"]["type"], "integer")
        self.assertEqual(props["size"]["x-ox"]["unit"], "ms")

    def test_a_unit_is_a_short_word(self):
        for bad in ("", "decibels relative to full scale", 3):
            with self.assertRaises(TypeError) as caught:
                ox.Slider(0, 1, unit=bad)
            self.assertIn('fix:  write it like unit="dB"', str(caught.exception))

    def test_a_range_is_two_numbers_on_one_slider(self):
        @ox.action("Band")
        def band(part: ox.Range(0, 1), hz: ox.Range(20, 20000, step=1, unit="Hz") = (200, 4000)):
            return [list(hz), list(part)]

        act = find(band)
        props = act.spec()["input"]["properties"]
        self.assertEqual(props["hz"], {
            "type": "array", "items": {"type": "integer", "minimum": 20, "maximum": 20000}, "minItems": 2, "maxItems": 2,
            "x-ox": {"control": "slider", "step": 1, "unit": "Hz"}, "title": "Hz", "default": [200, 4000],
        })
        self.assertEqual(props["part"]["items"]["type"], "number")
        self.assertEqual(props["part"]["default"], [0, 1])
        self.assertEqual(act.spec()["input"]["required"], [])
        self.assertEqual(bind(act, {"hz": [100, 300.0]}), {"hz": (100, 300), "part": (0, 1)})
        self.assertEqual(bind(act, {"part": [0.25, 0.5]})["part"], (0.25, 0.5))
        self.assertEqual(ox.test(band, hz=[50, 60])["result"], [[50, 60], [0, 1]])

    def test_a_range_says_what_is_wrong(self):
        @ox.action("Band")
        def band(hz: ox.Range(20, 20000, step=1) = (200, 4000)):
            return None

        act = find(band)
        cases = {
            "Hz is a start and an end from 20 to 20000.": [100],
            "Hz must be from 20 to 20000. It was 10 to 300.": [10, 300],
            "Hz starts after it ends: 500 to 300.": [500, 300],
            "Hz is whole numbers from 20 to 20000.": [100.5, 300],
        }
        for message, value in cases.items():
            with self.assertRaises(BadInput) as caught:
                bind(act, {"hz": value})
            self.assertEqual(str(caught.exception), message)

    def test_a_range_default_that_does_not_fit_is_refused(self):
        with self.assertRaises(TypeError) as caught:
            @ox.action("Band")
            def band(hz: ox.Range(20, 200) = (300, 400)):
                return None
        self.assertIn("the default for hz doesn't fit", str(caught.exception))


class BesideTest(unittest.TestCase):
    def setUp(self):
        clear()
        self.dir = tempfile.TemporaryDirectory()
        self.song = Path(self.dir.name) / "song.wav"
        self.song.write_bytes(b"riff")

        @ox.action("Where")
        def where(files: ox.Files("audio"), folder: ox.Folder(label="Save to") | None = None):
            return [str(folder or ox.beside(path)) if (folder or ox.beside(path)) else None for path in files]

        self.where = where

    def tearDown(self):
        self.dir.cleanup()

    def test_beside_is_the_folder_next_to_a_chosen_file(self):
        self.assertEqual(ox.test(self.where, files=[self.song])["result"], [self.dir.name])
        self.assertEqual(ox.beside(self.song), Path(self.dir.name))

    def test_a_file_from_open_with_has_nothing_beside_it(self):
        self.assertEqual(ox.test(self.where, open_with=[self.song])["result"], [None])
        # A folder the person chose still wins.
        chosen = Path(self.dir.name) / "out"
        chosen.mkdir()
        self.assertEqual(ox.test(self.where, open_with=[self.song], folder=chosen)["result"], [str(chosen)])

    def test_open_with_needs_a_files_control(self):
        @ox.action("Nothing")
        def nothing(gain: float = 1.0):
            return None

        with self.assertRaises(TypeError) as caught:
            ox.test(nothing, open_with=[self.song])
        self.assertIn("has no Files control", str(caught.exception))

    def test_the_host_says_which_files_were_handed_over(self):
        host = Host()
        try:
            host.recv()
            host.send({"type": "call", "id": 3, "action": "where", "input": {"files": [str(self.song)]}, "handed": [str(self.song)]})
            result, _ = host.until("result", 3)
            self.assertEqual(result["body"], [None])
            host.send({"type": "call", "id": 4, "action": "where", "input": {"files": [str(self.song)]}})
            result, _ = host.until("result", 4)
            self.assertEqual(result["body"], [self.dir.name])
        finally:
            host.close()


if __name__ == "__main__":
    unittest.main()
