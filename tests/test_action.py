import tempfile
import unittest
from pathlib import Path

import ox1audio as ox
from ox1audio.action import BadInput, bind, clear, find


class ActionTest(unittest.TestCase):
    def setUp(self):
        clear()
        self.dir = tempfile.TemporaryDirectory()
        self.song = Path(self.dir.name) / "song.wav"
        self.song.write_bytes(b"riff")

    def tearDown(self):
        self.dir.cleanup()

    def test_the_signature_is_the_input_schema(self):
        @ox.action("Convert files")
        def convert(files: ox.Files("audio"), format: ox.Choice("wav", "mp3"), gain: ox.Slider(0, 12, step=0.5) = 6.0, normalize: ox.Toggle = True, voices: int = 2):
            return None

        spec = find(convert).spec()
        self.assertEqual(spec["name"], "convert")
        self.assertEqual(spec["title"], "Convert files")
        props = spec["input"]["properties"]
        self.assertEqual(props["files"]["type"], "array")
        self.assertEqual(props["files"]["x-ox"], {"control": "files", "accept": "audio", "multiple": True})
        self.assertEqual(props["format"]["enum"], ["wav", "mp3"])
        self.assertEqual(props["format"]["default"], "wav")
        self.assertEqual(props["gain"]["default"], 6.0)
        self.assertEqual((props["gain"]["minimum"], props["gain"]["maximum"]), (0, 12))
        self.assertEqual(props["normalize"]["default"], True)
        self.assertEqual(props["voices"]["type"], "integer")
        self.assertEqual(props["voices"]["title"], "Voices")
        self.assertEqual(spec["input"]["required"], ["files"])
        self.assertFalse(spec["input"]["additionalProperties"])
        self.assertEqual(find(convert).permissions(), {"files"})

    def test_files_arrive_as_paths(self):
        @ox.action("Name it")
        def name(files: ox.Files("audio")):
            return ", ".join(path.stem for path in files)

        self.assertEqual(ox.test(name, files=[str(self.song)])["result"], "song")

    def test_one_file_and_a_folder_arrive_as_a_path(self):
        @ox.action("Place")
        def place(file: ox.Files("any", multiple=False), folder: ox.Folder()):
            return f"{file.name} in {folder.name}"

        result = ox.test(place, file=self.song, folder=self.song.parent)["result"]
        self.assertEqual(result, f"song.wav in {self.song.parent.name}")

    def test_defaults_fill_what_is_not_given(self):
        @ox.action("Defaults")
        def defaults(format: ox.Choice("wav", "mp3"), gain: ox.Slider(-6, 6), note: ox.Text(), loud: ox.Toggle, take: int = 3):
            return {"format": format, "gain": gain, "note": note, "loud": loud, "take": take}

        self.assertEqual(ox.test(defaults)["result"], {"format": "wav", "gain": -6.0, "note": "", "loud": False, "take": 3})

    def test_input_is_checked_and_the_message_says_what_to_do(self):
        @ox.action("Louder")
        def louder(files: ox.Files("audio"), gain: ox.Slider(0, 12, step=0.5) = 6.0):
            return None

        act = find(louder)
        with self.assertRaisesRegex(BadInput, "Add a file first"):
            bind(act, {})
        with self.assertRaisesRegex(BadInput, "Gain must be a number from 0 to 12. It was 40"):
            bind(act, {"files": [str(self.song)], "gain": 40})
        with self.assertRaisesRegex(BadInput, "gone.wav is not there anymore"):
            bind(act, {"files": [str(self.song.with_name("gone.wav"))]})
        with self.assertRaisesRegex(BadInput, "no control called volume"):
            bind(act, {"files": [str(self.song)], "volume": 3})

    def test_exports_go_to_the_library_and_come_back_with_their_path(self):
        @ox.action("Copy")
        def copy(files: ox.Files("audio")):
            made = []
            for index, path in enumerate(files):
                ox.progress(index / len(files), path.name)
                made.append(ox.sound(path, title=f"{path.stem} copy", bpm=120))
            return made

        run = ox.test(copy, files=[self.song])
        self.assertEqual(run["items"][0]["title"], "song copy")
        self.assertEqual(run["items"][0]["metadata"], {"bpm": 120})
        self.assertEqual(run["result"]["items"][0]["path"], str(self.song))
        self.assertEqual(run["progress"], [(0.0, "song.wav")])

    def test_a_problem_carries_its_hint(self):
        @ox.action("Fail")
        def fail():
            raise ox.Problem("That file has no audio.", hint="Try a WAV or MP3.")

        with self.assertRaises(ox.Problem) as caught:
            ox.test(fail)
        self.assertEqual(caught.exception.hint, "Try a WAV or MP3.")

    def test_optional_parameters_accept_nothing(self):
        @ox.action("Maybe")
        def maybe(folder: ox.Folder() | None = None, label: str | None = None):
            return [str(folder), label]

        self.assertEqual(ox.test(maybe)["result"], ["None", None])
        self.assertIn("anyOf", find(maybe).spec()["input"]["properties"]["folder"])

    def test_a_wrong_type_hint_is_refused_with_the_fix(self):
        with self.assertRaises(TypeError) as caught:
            @ox.action("Bad")
            def bad(files: list):
                return None
        message = str(caught.exception)
        self.assertIn('bad(): the parameter "files" is a list, which is not a control.', message)
        self.assertIn("fix:  annotate it with a control", message)
        self.assertIn("docs: https://docs.0x1audio.com/actions#controls", message)

    def test_a_missing_type_hint_is_refused(self):
        with self.assertRaisesRegex(TypeError, 'parameter "name" has no type'):
            @ox.action("Hello")
            def hello(name):
                return name

    def test_a_default_that_does_not_fit_is_refused(self):
        with self.assertRaisesRegex(TypeError, "the default for format doesn't fit"):
            @ox.action("Bad")
            def bad(format: ox.Choice("wav", "mp3") = "ogg"):
                return None

    def test_a_title_is_required(self):
        with self.assertRaisesRegex(TypeError, '@ox.action\\("Hello"\\)'):
            @ox.action
            def hello(name: str):
                return name

    def test_a_result_that_is_not_json_is_explained(self):
        @ox.action("Odd")
        def odd():
            return {"when": object()}

        with self.assertRaisesRegex(TypeError, "can't be sent to the page"):
            ox.test(odd)


if __name__ == "__main__":
    unittest.main()


class ChoiceAndAudioTest(unittest.TestCase):
    def setUp(self):
        clear()

    def test_a_multiple_choice_is_a_list_in_option_order(self):
        @ox.action("Convert")
        def convert(formats: ox.Choice("wav", "flac", "mp3", multiple=True)):
            return formats

        spec = find(convert).spec()["input"]["properties"]["formats"]
        self.assertEqual(spec["default"], ["wav"])
        self.assertEqual(spec["x-ox"], {"control": "choice", "multiple": True})
        self.assertEqual(ox.test(convert, formats=["mp3", "wav"])["result"], ["wav", "mp3"])
        with self.assertRaisesRegex(BadInput, "Choose at least one option for formats"):
            bind(find(convert), {"formats": []})

    def test_a_file_that_is_not_audio_is_a_problem_in_plain_words(self):
        with tempfile.TemporaryDirectory() as folder:
            notes = Path(folder) / "notes.wav"
            notes.write_text("not audio")
            with self.assertRaises(ox.Problem) as caught:
                ox.audio.probe(notes)
        self.assertEqual(str(caught.exception), "notes.wav isn't a sound file 0x1audio can open.")
        self.assertNotIn("ffmpeg", str(caught.exception) + caught.exception.hint)


class ConvertTest(unittest.TestCase):
    def test_converting_next_to_the_original_never_replaces_it(self):
        from ox1audio.cli import tone

        with tempfile.TemporaryDirectory() as folder:
            song = Path(folder) / "song.wav"
            song.write_bytes(tone())
            before = song.read_bytes()
            out = ox.audio.convert(song, "wav", folder=song.parent)
            self.assertEqual(out.name, "song 2.wav")
            self.assertEqual(song.read_bytes(), before)
            self.assertEqual(ox.audio.convert(song, "flac", folder=song.parent).name, "song.flac")
