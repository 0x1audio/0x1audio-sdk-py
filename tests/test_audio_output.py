"""SDK 0.3.1, the output stage: dither (GAB-132), no silent clipping and float (GAB-133),
tags, cover and loops through convert (GAB-134), and every channel kept (GAB-135).

Every check runs on generated signals and compares samples, never file hashes."""

import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio import _tags
from ox1audio.audio import ffmpeg

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

RATE = 48000


def sine(db: float, seconds: float = 1.0, freq: float = 1000.0, channels: int = 1):
    t = np.arange(int(RATE * seconds)) / RATE
    wave = (10 ** (db / 20) * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(wave[:, None], channels, axis=1)


def harmonics(samples, freq: float = 1000.0) -> list[float]:
    """Level in dBFS of the fundamental and the 3rd and 5th harmonics (Hann window)."""
    x = samples[:, 0].astype(np.float64)
    window = np.hanning(len(x))
    spectrum = np.abs(np.fft.rfft(x * window)) / (window.sum() / 2)
    bins = np.fft.rfftfreq(len(x), 1 / RATE)
    return [20 * np.log10(spectrum[np.argmin(abs(bins - k * freq))] + 1e-30) for k in (1, 3, 5)]


@unittest.skipIf(np is None, "numpy is not installed")
class OutputTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def ff(self, *args: str) -> None:
        subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", "-y", *args], check=True, timeout=60)

    # GAB-132 --------------------------------------------------------------------------------

    def test_24_to_16_bit_is_dithered(self):
        quiet = ox.audio.write(sine(-90), RATE, "wav", self.folder, "quiet")  # 24-bit
        for target in ("wav", "aiff", "flac"):
            out = ox.audio.convert(quiet, target, self.folder, bits=16)
            samples, _ = ox.audio.read(out)
            levels = len(np.unique(samples))
            fundamental, third, fifth = harmonics(samples)
            self.assertGreater(levels, 4, f"{target}: not a square wave")
            self.assertAlmostEqual(fundamental, -90, delta=0.5)
            self.assertLess(third, -120, f"{target}: truncation harmonics")
            self.assertLess(fifth, -120, f"{target}: truncation harmonics")

    def test_write_to_16_bit_is_dithered(self):
        samples, _ = ox.audio.read(ox.audio.write(sine(-90), RATE, "wav", self.folder, bits=16))
        self.assertLess(max(harmonics(samples)[1:]), -120)

    def test_float_to_24_bit_is_dithered(self):
        source = self.folder / "float.wav"
        subprocess.run([ffmpeg(), "-v", "error", "-y", "-f", "f32le", "-ar", str(RATE), "-ac", "1", "-i", "-", "-c:a", "pcm_f32le", str(source)], input=sine(-135).tobytes(), check=True)
        samples, _ = ox.audio.read(ox.audio.convert(source, "wav", self.folder, bits=24))
        self.assertLess(max(harmonics(samples)[1:]), -165)

    def test_the_same_depth_stays_bit_exact(self):
        for bits in (16, 24):
            first = ox.audio.write(sine(-20, 0.2), RATE, "wav", self.folder, f"first{bits}", bits=bits)
            samples, _ = ox.audio.read(first)
            again = ox.audio.write(samples, RATE, "wav", self.folder, f"again{bits}", bits=bits)
            self.assertEqual(Path(first).read_bytes()[-2000:], Path(again).read_bytes()[-2000:], f"{bits}-bit write of {bits}-bit samples")
            converted, _ = ox.audio.read(ox.audio.convert(first, "flac", self.folder))
            self.assertTrue(np.array_equal(samples, converted), f"{bits}-bit WAV to FLAC nulls")

    def test_dither_is_the_same_every_run(self):
        one, _ = ox.audio.read(ox.audio.write(sine(-60, 0.1), RATE, "wav", self.folder, "one", bits=16))
        two, _ = ox.audio.read(ox.audio.write(sine(-60, 0.1), RATE, "wav", self.folder, "two", bits=16))
        self.assertTrue(np.array_equal(one, two))

    # GAB-133 --------------------------------------------------------------------------------

    def test_write_refuses_overs_and_names_the_fix(self):
        loud = sine(0, 0.1) * 1.8
        for target, bits in (("wav", None), ("flac", 16), ("mp3", None)):
            with self.assertRaises(ValueError) as caught:
                ox.audio.write(loud, RATE, target, self.folder, bits=bits)
            message = str(caught.exception)
            self.assertIn("+5.1 dBFS", message)
            self.assertIn("fix:  lower the gain (samples * 0.55), or write \"wav\" with bits=32", message)
        self.assertEqual(list(self.folder.iterdir()), [], "nothing half written")

    def test_full_scale_is_not_an_over(self):
        ox.audio.write(np.array([[1.0], [-1.0], [0.5]], dtype=np.float32), RATE, "wav", self.folder)

    def test_bits_32_is_float_and_keeps_overs(self):
        loud = sine(0, 0.1) * 1.8
        for target in ("wav", "aiff"):
            out = ox.audio.write(loud, RATE, target, self.folder, bits=32)
            info = ox.audio.probe(out)
            self.assertTrue(info.float, target)
            back, _ = ox.audio.read(out)
            self.assertTrue(np.array_equal(back, loud), f"{target}: float is exact, overs included")
        with self.assertRaisesRegex(ValueError, r"only WAV and AIFF[\s\S]*fix:"):
            ox.audio.write(loud, RATE, "flac", self.folder, bits=32)
        quiet = ox.audio.write(sine(-6, 0.1), RATE, "wav", self.folder, "quiet")
        self.assertTrue(ox.audio.probe(ox.audio.convert(quiet, "wav", self.folder, bits=32)).float)

    def test_nan_is_refused(self):
        bad = sine(-6, 0.1)
        bad[10, 0] = np.nan
        with self.assertRaisesRegex(ValueError, "NaN"):
            ox.audio.write(bad, RATE, "wav", self.folder)

    # GAB-134 --------------------------------------------------------------------------------

    def kit_wav(self) -> Path:
        """The kit's tagged, looped WAV: 2 s of 24-bit stereo, a loop from 1000 to 40000, 124 BPM in D minor, a cover."""
        plain = ox.audio.write(sine(-12, 2.0, 220, channels=2), RATE, "wav", self.folder, "plain")
        cover = self.folder / "cover.png"
        self.ff("-f", "lavfi", "-i", "color=c=red:s=32x32:d=1", "-frames:v", "1", str(cover))
        tagged = self.folder / "tagged.mp3"
        self.ff("-i", str(plain), "-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:a", "libmp3lame", "-c:v", "png", "-disposition:v", "attached_pic",
                "-id3v2_version", "3", "-metadata", "title=Kit loop", "-metadata", "TBPM=124", "-metadata", "TKEY=D minor", str(tagged))
        # A WAV with the same tags and cover, by converting, then a smpl loop added by hand.
        kit = ox.audio.convert(tagged, "wav", self.folder, bits=24)
        smpl = struct.pack("<9I", 0, 0, int(1e9 / RATE), 62, 0, 0, 0, 1, 0) + struct.pack("<6I", 0, 0, 1000, 40000, 0, 0)
        _tags._append(kit, [(b"smpl", smpl)], big=False)
        return kit

    def test_convert_keeps_tags_cover_and_loops(self):
        kit = self.kit_wav()
        found = _tags.read(kit)
        self.assertEqual((found.bpm, found.key, found.loops, found.cover), (124.0, "D minor", [(1000, 40000)], True))
        expect = {
            # format: (bpm, key, loops, cover)
            "wav": (124.0, "D minor", [(1000, 40000)], True),
            "aiff": (124.0, "D minor", [(1000, 40000)], True),
            "flac": (124.0, "D minor", [(1000, 40000)], True),
            "mp3": (124.0, "D minor", [], True),
            "aac": (124.0, None, [], True),
            "ogg": (124.0, "D minor", [(1000, 40000)], False),
        }
        for target, want in expect.items():
            out = ox.audio.convert(kit, target, self.folder)
            got = _tags.read(out)
            self.assertEqual((got.bpm, got.key, got.loops, got.cover), want, target)
            if target != "aac":
                self.assertIn("Kit loop", subprocess.run([ffmpeg(), "-hide_banner", "-i", str(out)], capture_output=True, text=True).stderr, f"{target}: title")

    def test_a_wav_copy_keeps_its_loop_chunks_byte_for_byte(self):
        kit = self.kit_wav()
        copy = ox.audio.convert(kit, "wav", self.folder)
        self.assertEqual(_tags.read(copy).chunks.get("smpl"), _tags.read(kit).chunks.get("smpl"))
        self.assertIn("acid", _tags.read(copy).chunks)
        back, _ = ox.audio.read(copy)
        source, _ = ox.audio.read(kit)
        self.assertTrue(np.array_equal(back, source), "the samples null")

    # GAB-135 --------------------------------------------------------------------------------

    def test_every_channel_of_an_unusual_layout_is_kept(self):
        six = self.folder / "hexagonal.wav"
        self.ff("-f", "lavfi", "-i", "sine=frequency=440:duration=0.5:sample_rate=48000", "-af", "pan=hexagonal|c0=c0|c1=c0|c2=c0|c3=c0|c4=c0|c5=c0", "-c:a", "pcm_s24le", str(six))
        self.assertEqual(ox.audio.probe(six).channels, 6)
        samples, _ = ox.audio.read(six)
        self.assertEqual(samples.shape[1], 6)
        self.assertEqual(ox.audio.probe(ox.audio.convert(six, "flac", self.folder)).channels, 6)
        self.assertEqual(ox.audio.channel_count("6.0(front)"), 6)
        self.assertEqual(ox.audio.channel_count("22.2"), 24)
        self.assertEqual(ox.audio.channel_count("FL+FR+LFE"), 3)


if __name__ == "__main__":
    unittest.main()
