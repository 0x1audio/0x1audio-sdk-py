"""Read and write audio with the ffmpeg that ships in the imageio-ffmpeg wheel."""

from __future__ import annotations

import functools
import os
import re
import stat
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_duration = re.compile(r"Duration: (\d+):(\d{2}):(\d{2}(?:\.\d+)?)")
_stream = re.compile(r"Stream #\d+:\d+[^:]*: Audio: ([^,\n]+), (\d+) Hz, ([^,\n]+)(?:, ([^,\n]+))?(?:, (\d+) kb/s)?")
_layouts = {"mono": 1, "stereo": 2, "2.1": 3, "3.0": 3, "quad": 4, "4.0": 4, "5.0": 5, "5.1": 6, "6.1": 7, "7.1": 8}


@dataclass(frozen=True)
class Info:
    path: str
    name: str
    codec: str
    rate: int
    channels: int
    duration: float
    bitrate: int | None


@dataclass(frozen=True)
class Format:
    id: str
    label: str
    ext: str
    encoder: str
    lossless: bool
    muxer: str
    bitrates: tuple[int, ...] = ()
    rates: tuple[int, ...] = ()
    max_channels: int | None = None
    extra: tuple[str, ...] = ()


_mp3_rates = (8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000)

FORMATS: tuple[Format, ...] = (
    Format("wav", "WAV", "wav", "pcm_s24le", True, "wav"),
    Format("aiff", "AIFF", "aiff", "pcm_s24be", True, "aiff"),
    Format("flac", "FLAC", "flac", "flac", True, "flac"),
    Format("mp3", "MP3", "mp3", "libmp3lame", False, "mp3", bitrates=(320,), rates=_mp3_rates, max_channels=2, extra=("-id3v2_version", "3")),
    Format("aac", "AAC", "m4a", "aac", False, "ipod", bitrates=(256,), extra=("-movflags", "+faststart")),
    Format("ogg", "Ogg Vorbis", "ogg", "libvorbis", False, "ogg", bitrates=(192,)),
    Format("opus", "Opus", "opus", "libopus", False, "opus", bitrates=(128,), rates=(48000,), max_channels=2),
)

_by_id = {item.id: item for item in FORMATS}


@functools.cache
def ffmpeg() -> str:
    import imageio_ffmpeg

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    mode = os.stat(exe).st_mode
    if not mode & stat.S_IXUSR:
        os.chmod(exe, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return exe


@functools.cache
def encoders() -> frozenset[str]:
    out = subprocess.run([ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
    found = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("A"):
            found.add(parts[1])
    return frozenset(found)


def probe(path: str | Path) -> Info:
    source = Path(path)
    if not source.is_file():
        from ox1audio.action import Problem

        raise Problem(f"{source.name} is not there anymore.", hint="Choose it again.")
    result = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostdin", "-i", str(source)],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )
    stream = _stream.search(result.stderr)
    if not stream:
        from ox1audio.action import Problem

        raise Problem(f"{source.name} isn't a sound file 0x1audio can open.", hint="Choose a WAV, AIFF, FLAC, MP3 or similar file.")
    duration = 0.0
    found = _duration.search(result.stderr)
    if found:
        hours, minutes, seconds = found.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    bitrate = int(stream.group(5)) if stream.group(5) else None
    return Info(
        path=str(source),
        name=source.name,
        codec=stream.group(1).split(" ")[0],
        rate=int(stream.group(2)),
        channels=channel_count(stream.group(3)),
        duration=duration,
        bitrate=bitrate,
    )


def channel_count(layout: str) -> int:
    layout = layout.strip()
    counted = re.match(r"(\d+) channels", layout)
    if counted:
        return int(counted.group(1))
    return _layouts.get(layout.split("(")[0], 2)


def available() -> list[str]:
    have = encoders()
    return [item.id for item in FORMATS if item.id in {"wav", "aiff"} or item.encoder in have]


def find(format_id: str) -> Format:
    found = _by_id.get(format_id)
    if found is None or found.id not in available():
        raise ValueError(f"{format_id} is not a format this computer can write.")
    return found


@dataclass
class _Plan:
    source: Info
    format: Format
    target: Path
    args: list[str] = field(default_factory=list)


def convert(path: str | Path, format_id: str, folder: str | Path | None = None, on_progress: Callable[[float], None] | None = None) -> Path:
    """Write ``path`` as ``format_id`` and return the new file."""
    source = probe(path)
    fmt = find(format_id)
    out = Path(folder) if folder else Path(tempfile.mkdtemp(prefix="ox1-audio-"))
    target = out / f"{Path(source.name).stem}.{fmt.ext}"
    channels = source.channels if fmt.max_channels is None else min(source.channels, fmt.max_channels)
    rate = source.rate
    if fmt.rates and rate not in fmt.rates:
        lower = [item for item in fmt.rates if item <= rate]
        rate = max(lower) if lower else min(fmt.rates)
    args = [
        ffmpeg(), "-hide_banner", "-nostdin", "-y",
        "-i", source.path,
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-c:a", fmt.encoder if not fmt.lossless or fmt.id in {"flac"} else fmt.encoder,
        "-ar", str(rate), "-ac", str(channels),
    ]
    if fmt.bitrates:
        args += ["-b:a", f"{fmt.bitrates[-1]}k"]
    args += list(fmt.extra)
    args += ["-f", fmt.muxer, "-progress", "pipe:1", "-nostats", str(target)]
    step = _Plan(source, fmt, target, args)
    return _run(step, on_progress)


def _run(step: _Plan, on_progress: Callable[[float], None] | None) -> Path:
    step.target.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    total = step.source.duration
    with subprocess.Popen(step.args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace") as process:
        reader = threading.Thread(target=lambda: errors.extend(process.stderr or []), daemon=True)
        reader.start()
        try:
            for line in process.stdout or []:
                key, _, value = line.strip().partition("=")
                if key == "out_time_us" and total > 0 and on_progress:
                    try:
                        fraction = min(1.0, max(0.0, int(value) / 1_000_000 / total))
                    except ValueError:
                        continue
                    on_progress(fraction)
        except BaseException:
            # Stop (ox.Cancelled from the progress callback) or any error: don't leave ffmpeg or half a file.
            process.kill()
            process.wait()
            step.target.unlink(missing_ok=True)
            raise
        process.wait()
        reader.join(timeout=5)
    if process.returncode != 0:
        step.target.unlink(missing_ok=True)
        tail = [line.strip() for line in errors if line.strip()][-3:]
        raise RuntimeError(" ".join(tail) or f"ffmpeg exited with {process.returncode}.")
    if on_progress:
        on_progress(1.0)
    return step.target
