import json
import shutil
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from ox1audio import local
from ox1audio.local import Found, Mixel, MixelError, MixelTimeoutError, MixelUnavailableError, Sound

from fake_mixel import FakeMixel

unix = unittest.skipIf(sys.platform == "win32", "the Library socket is a Unix socket here")


@unix
class LibraryTest(unittest.TestCase):
    def test_overview_search_similar_and_a_crate(self):
        with FakeMixel() as fake:
            mixel = Mixel(data_dir=fake.data_dir, caller="my-script")
            self.assertEqual(mixel.overview(), local.Overview(4, {"snare": 2, "clap": 1, "loop": 1}, 0))

            found = mixel.search("snare", avoid=["clap"])
            self.assertTrue(found.answerable)
            self.assertEqual(found.sounds[0], Sound("s1", "Snare Tape 04.wav", "one-shot", None, None, 0.1, "named", "named snare"))
            self.assertEqual([sound.id for sound in found], ["s1", "s2"])
            self.assertEqual(len(found), 2)
            # A model gets Mixel's compact rows, as sent, not the objects.
            self.assertEqual(str(found), found.text)
            self.assertEqual(json.loads(found.text)["columns"][:2], ["id", "title"])
            self.assertEqual(fake.calls[-1], {"caller": "my-script", "tool": "library_search", "args": {"want": "snare", "avoid": ["clap"]}})

            like = mixel.similar("s1", type="one-shot")
            self.assertEqual([sound.id for sound in like], ["s2", "s3"])
            self.assertEqual(fake.calls[-1]["args"], {"filters": {"type": "one-shot"}, "like": "s1"})

            loops = mixel.search(type="loop", bpm=(90, None))
            self.assertEqual([sound.title for sound in loops], ["Dusty Loop 92.wav"])
            self.assertEqual(fake.calls[-1]["args"], {"filters": {"type": "loop", "bpm": [90, None]}})

            none = mixel.search("bagpipes")
            self.assertFalse(none.answerable)
            self.assertEqual(none.sounds, [])
            self.assertEqual(none.nearest, {"snare": 2, "clap": 1})

            self.assertEqual(mixel.propose_crate("Snares", "two snares, not claps", ["s1", "s2", "s9"]), {"sounds": 2, "unknown": 1})

    def test_rows_cost_about_a_third_less_than_objects(self):
        rows = [[f"s{n}", f"Snare {n} dusty tape.wav", "one-shot", "F minor", 92, 0.4, "named", "named snare"] for n in range(10)]
        found = Found.from_text(json.dumps({"answerable": True, "columns": list(local.COLUMNS), "results": rows}))
        as_objects = json.dumps([sound.__dict__ for sound in found])
        self.assertLess(len(found.text), len(as_objects) * 0.7)

    def test_what_mixel_refuses_is_a_mixel_error_with_its_code_and_fix(self):
        with FakeMixel(crates=False) as fake:
            mixel = Mixel(data_dir=fake.data_dir)
            with self.assertRaises(MixelError) as caught:
                mixel.similar("s99")
            self.assertNotIsInstance(caught.exception, MixelUnavailableError)
            self.assertEqual(caught.exception.code, "unknown_id")
            self.assertEqual(caught.exception.to_dict(), {"code": "unknown_id", "message": "s99 isn't an id from a library_search result.", "fix": "search again and use the ids it returns"})
            self.assertEqual(str(caught.exception), "s99 isn't an id from a library_search result. (fix: search again and use the ids it returns)")
            self.assertEqual(len(fake.calls), 1, "a refusal is never retried")
            with self.assertRaises(MixelError) as off:
                mixel.propose_crate("Snares", "snares", ["s1"])
            self.assertEqual(off.exception.code, "crates_off")
            with self.assertRaises(MixelError) as empty:
                mixel.search("")
            self.assertEqual(empty.exception.code, "bad_input")

    def test_mixel_closed_is_unavailable_at_once_with_the_fix(self):
        empty = Path(tempfile.mkdtemp(prefix="no-mixel-"))
        try:
            started = time.monotonic()
            with self.assertRaises(MixelUnavailableError) as caught:
                Mixel(data_dir=empty, retries=5).search("snare")
            # Five retries would wait 0.1 + 0.2 + 0.4 + 0.8 + 1.6 s.
            self.assertLess(time.monotonic() - started, 2, "no retries when nothing is there")
            self.assertEqual(caught.exception.code, "library_search_off")
            self.assertIn("Settings › Your assistant", caught.exception.fix)
            with mock.patch.object(local, "sys", types.SimpleNamespace(platform="win32")):
                with self.assertRaises(MixelUnavailableError):
                    Mixel(data_dir=empty).overview()
            with self.assertRaises(MixelUnavailableError) as dev:
                Mixel(data_dir=empty).status()
            self.assertEqual(dev.exception.code, "desktop_unavailable")
            self.assertIn("Developer mode", dev.exception.fix)
        finally:
            shutil.rmtree(empty)

    def test_a_dropped_connection_is_retried_for_a_search_never_for_a_crate(self):
        with FakeMixel(drop=1) as fake:
            self.assertEqual(len(Mixel(data_dir=fake.data_dir).search("snare")), 2)
            self.assertEqual(len(fake.calls), 1)
        with FakeMixel(drop=1) as fake:
            with self.assertRaises(MixelUnavailableError) as caught:
                Mixel(data_dir=fake.data_dir).propose_crate("Snares", "snares", ["s1"])
            self.assertEqual(caught.exception.message, "Mixel stopped answering before it replied.")
            self.assertEqual(fake.calls, [])

    def test_a_slow_mixel_is_a_timeout_after_the_retries(self):
        with FakeMixel(delay=0.4) as fake:
            with self.assertRaises(MixelTimeoutError) as caught:
                Mixel(data_dir=fake.data_dir, timeout=0.05, retries=1).overview()
            self.assertEqual(caught.exception.code, "timeout")
            self.assertEqual(len(fake.calls), 2)

    def test_windows_uses_127_0_0_1_and_the_token_from_endpoint_json(self):
        with FakeMixel(windows=True) as fake, mock.patch.object(local, "sys", types.SimpleNamespace(platform="win32")):
            self.assertEqual(Mixel(data_dir=fake.data_dir).overview().sounds, 4)
            self.assertEqual(fake.calls[0]["token"], "t" * 43)

    def test_a_search_pages_with_next_and_offset(self):
        with FakeMixel(page=1) as fake:
            mixel = Mixel(data_dir=fake.data_dir)
            first = mixel.search("snare")
            self.assertEqual(([sound.id for sound in first], first.more, first.next), (["s1"], 1, 1))
            second = mixel.search("snare", offset=first.next)
            self.assertEqual(([sound.id for sound in second], second.more, second.next), (["s2"], 0, None))
            self.assertEqual(fake.calls[-1]["args"], {"want": "snare", "offset": 1})

    def test_without_the_sound_model_similar_is_refused_with_not_ready(self):
        with FakeMixel(no_model=True) as fake:
            with self.assertRaises(MixelError) as caught:
                Mixel(data_dir=fake.data_dir).similar("s1")
            self.assertEqual(caught.exception.code, "not_ready")
            self.assertEqual(caught.exception.fix, "search with words instead, or ask the person to check Mixel")

    def test_the_data_folder_is_mixels_own_or_mixel_data_dir(self):
        with mock.patch.dict("os.environ", {"MIXEL_DATA_DIR": "/tmp/profile"}):
            self.assertEqual(local.data_dir(), Path("/tmp/profile"))
            self.assertEqual(Mixel().data_dir, Path("/tmp/profile"))


@unix
class DeveloperModeTest(unittest.TestCase):
    def test_status_open_reload_log_and_close(self):
        folder = Path(tempfile.mkdtemp(prefix="make-it-mono-"))
        try:
            with FakeMixel(developer=True) as fake:
                mixel = Mixel(data_dir=fake.data_dir)
                self.assertEqual(mixel.status(), {"mixel": "0.1.17", "sdk": "0.3.4", "protocol": 1})
                app = mixel.open_app(folder)
                self.assertEqual((app.id, app.display_name, app.version), ("dev-1", folder.name, "0.1.0"))
                app.reload(["app.py"])
                self.assertEqual([line["type"] for line in app.log()], ["info", "log", "closed"])
                app.close()
                self.assertEqual([f"{method} {path}" for method, path, _ in fake.dev_calls],
                                 ["GET /v1/status", "POST /v1/apps", "POST /v1/apps/dev-1/reload", "GET /v1/apps/dev-1/log", "DELETE /v1/apps/dev-1"])
                self.assertEqual(fake.dev_calls[2][2], {"changed": ["app.py"]})
                self.assertEqual(fake.dev_calls[1][2], {"dir": str(folder.resolve())})
        finally:
            shutil.rmtree(folder)


    def test_a_log_that_has_said_nothing_yet_ends_quietly_at_its_timeout(self):
        folder = Path(tempfile.mkdtemp(prefix="quiet-app-"))
        try:
            with FakeMixel(developer=True, quiet_log=True) as fake:
                app = Mixel(data_dir=fake.data_dir).open_app(folder)
                started = time.monotonic()
                self.assertEqual(list(app.log(timeout=0.2)), [])
                self.assertLess(time.monotonic() - started, 2.5, "it stopped at its timeout, not when Mixel hung up")
                app.close()
        finally:
            shutil.rmtree(folder)


class RunAppTest(unittest.TestCase):
    def test_an_action_runs_the_way_mixel_runs_it_and_failures_are_mixel_errors(self):
        from ox1audio.cli import new

        scratch = Path(tempfile.mkdtemp(prefix="run-app-"))
        try:
            folder = scratch / "make-it-flac"
            with mock.patch("builtins.print"):
                new.new(folder, "Make It Flac")
            run = local.run_app(folder, "convert", files=[folder / "tests" / "tone.wav"], input={"format": "flac"}, out=scratch / "out")
            self.assertEqual(run.items[0]["title"], "tone")
            self.assertTrue((scratch / "out").is_dir())
            self.assertTrue(any(path.suffix == ".flac" for path in (scratch / "out").iterdir()))
            with self.assertRaises(MixelError) as missing:
                local.run_app(folder, "nope", files=[folder / "tests" / "tone.wav"])
            self.assertEqual(missing.exception.code, "no_such_action")
            with self.assertRaises(MixelError) as bad:
                local.run_app(folder, "convert", files=[folder / "tests" / "tone.wav"], input={"format": "ogg"})
            self.assertEqual(bad.exception.code, "bad_input")
        finally:
            shutil.rmtree(scratch)


if __name__ == "__main__":
    unittest.main()
