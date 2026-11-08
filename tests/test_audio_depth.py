"""GAB-103: lossless copies keep the source's bit depth."""

import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.cli import tone


class BitDepthTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)
        self.song = self.folder / "song.wav"
        self.song.write_bytes(tone(0.5))  # 16-bit

    def tearDown(self):
        self.dir.cleanup()

    def test_a_16_bit_wav_stays_16_bit(self):
        out = ox.audio.convert(self.song, "wav")
        self.assertEqual(ox.audio.probe(out).codec, "pcm_s16le")
        self.assertLess(out.stat().st_size, self.song.stat().st_size * 1.01, "no up-convert: the same size")
        self.assertEqual(ox.audio.probe(ox.audio.convert(self.song, "aiff")).codec, "pcm_s16be")
        self.assertEqual(ox.audio.probe(ox.audio.convert(self.song, "flac")).bits, 16)

    def test_24_bit_stays_24_and_bits_asks_for_another(self):
        deep = ox.audio.convert(self.song, "wav", bits=24)
        self.assertEqual(ox.audio.probe(deep).bits, 24)
        self.assertEqual(ox.audio.probe(ox.audio.convert(deep, "flac")).bits, 24)
        self.assertEqual(ox.audio.probe(ox.audio.convert(deep, "wav", bits=16)).bits, 16)

    def test_lossy_sources_become_24_bit(self):
        mp3 = ox.audio.convert(self.song, "mp3")
        self.assertIsNone(ox.audio.probe(mp3).bits)
        self.assertEqual(ox.audio.probe(ox.audio.convert(mp3, "wav")).bits, 24)

    def test_a_wrong_depth_names_the_fix(self):
        with self.assertRaisesRegex(ValueError, r"16, 24 or 32[\s\S]*fix:"):
            ox.audio.convert(self.song, "wav", bits=20)


if __name__ == "__main__":
    unittest.main()
