"""Build 0x1audio apps: typed Python actions that run on the person's computer.

    import ox1audio as ox

    @ox.action("Make it louder")
    def louder(files: ox.Files("audio"), gain: ox.Slider(0, 12, step=0.5) = 6.0):
        ...

The whole public API is ``__all__`` below. AGENTS.md in every app explains it.
"""

__version__ = "0.3.0"

from ox1audio.action import Cancelled, Problem, action, progress, temp, test
from ox1audio.app import run
from ox1audio.fields import Choice, Files, Folder, Number, Slider, Text, Toggle, file, midi, sound

from . import audio, data, library

__all__ = [
    "Cancelled",
    "Choice",
    "Files",
    "Folder",
    "Number",
    "Problem",
    "Slider",
    "Text",
    "Toggle",
    "action",
    "audio",
    "data",
    "file",
    "library",
    "midi",
    "progress",
    "run",
    "sound",
    "temp",
    "test",
]

_DOCS = "https://docs.0x1audio.com"

# Names that 0.2 had. Using one says what replaced it instead of a bare AttributeError.
_removed = {
    "screen": ('@ox.screen("Title") is now @ox.action("Title").', 'rename the decorator: @ox.action("Title")', "actions"),
    "job": (
        "@ox.job is gone: every @ox.action already runs in the background with progress and Stop.",
        'use @ox.action("Title") with typed parameters, call ox.progress() as you go, and return the result',
        "actions#progress-and-stop",
    ),
    "serve": (
        "ox.serve is gone: 0x1audio finds your @ox.action functions and runs them.",
        'decorate each handler with @ox.action("Title") and delete the serve({...}) call',
        "actions",
    ),
    "Call": (
        "The call object is gone: actions take typed parameters.",
        "replace call.body[...] with parameters, call.progress(...) with ox.progress(...), and call.cancelled() with letting ox.Cancelled propagate",
        "actions#controls",
    ),
    "exercise": ("ox.exercise is now ox.test.", "ox.test(action, files=[...])", "actions#testing"),
    "convert": ("ox.convert is now ox.audio.convert.", 'ox.audio.convert(path, "wav")', "actions#helpers"),
    "Client": ("The cloud client is not part of the app API.", "remove it; apps reach the cloud only through what 0x1audio allows", "permissions"),
    "AuthenticatedClient": ("The cloud client is not part of the app API.", "remove it; apps reach the cloud only through what 0x1audio allows", "permissions"),
}


class RemovedError(ImportError):
    """A name from an older SDK. The message says what to use instead."""


def __getattr__(name: str) -> object:
    found = _removed.get(name)
    if found is None:
        raise AttributeError(f"module 'ox1audio' has no attribute {name!r}. The API is: {', '.join(__all__)}.")
    problem, fix, page = found
    # ImportError (not AttributeError), so `from ox1audio import job` shows this message too.
    raise RemovedError(f"{problem}\nfix:  {fix}\ndocs: {_DOCS}/{page}", name=name)
