"""Read and write audio with the ffmpeg that ships in the imageio-ffmpeg wheel."""

from __future__ import annotations

import functools
import os
import re
import stat
import subprocess
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
    # Bit depth of PCM and lossless sources (16, 24, 32), None for lossy ones like MP3.
    bits: int | None = None
    # True for 32-bit float PCM.
    float: bool = False


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

        raise Problem(f"{source.name} isn't a sound file Mixel can open.", hint="Choose a WAV, AIFF, FLAC, MP3 or similar file.")
    duration = 0.0
    found = _duration.search(result.stderr)
    if found:
        hours, minutes, seconds = found.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    bitrate = int(stream.group(5)) if stream.group(5) else None
    codec = stream.group(1).split(" ")[0]
    bits, is_float = _depth(codec, stream.group(4) or "")
    return Info(
        path=str(source),
        name=source.name,
        codec=codec,
        rate=int(stream.group(2)),
        channels=channel_count(stream.group(3)),
        duration=duration,
        bitrate=bitrate,
        bits=bits,
        float=is_float,
    )


def _depth(codec: str, sample: str) -> tuple[int | None, bool]:
    """The bit depth ffmpeg reports, like "s16" or "s32 (24 bit)". Lossy decoders report float: None."""
    raw = re.search(r"\((\d+) bit\)", sample)
    if raw:
        return int(raw.group(1)), False
    name = sample.strip().split(" ")[0].rstrip("p")
    if name in {"flt", "dbl"}:
        return (32, True) if codec.startswith("pcm_f") else (None, False)
    if name in {"u8", "s16"}:
        return 16, False
    if name in {"s32", "s64"}:
        return 32, False
    return None, False


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


def convert(
    path: str | Path,
    format_id: str,
    folder: str | Path | None = None,
    on_progress: Callable[[float], None] | None = None,
    bits: int | None = None,
) -> Path:
    """Write ``path`` as ``format_id`` and return the new file.

    It goes in ``folder`` (a new temporary folder when None) and never replaces a file
    that is already there: next to the original, ``song.wav`` becomes ``song 2.wav``.
    WAV, AIFF and FLAC keep the source's bit depth (24-bit from lossy sources like MP3);
    ``bits=16`` or ``24`` (or ``32`` for WAV and AIFF) asks for another.
    """
    if bits is not None and bits not in (16, 24, 32):
        from ox1audio.action import _teach

        raise ValueError(_teach(f"ox.audio.convert(bits={bits!r}): the bit depth is 16, 24 or 32.", 'ox.audio.convert(path, "wav", bits=16)', "actions#helpers"))
    source = probe(path)
    fmt = find(format_id)
    out = Path(folder) if folder else _temp()
    target = _unused(out / f"{Path(source.name).stem}.{fmt.ext}")
    channels = source.channels if fmt.max_channels is None else min(source.channels, fmt.max_channels)
    rate = source.rate
    if fmt.rates and rate not in fmt.rates:
        lower = [item for item in fmt.rates if item <= rate]
        rate = max(lower) if lower else min(fmt.rates)
    args = [
        ffmpeg(), "-hide_banner", "-nostdin", "-y",
        "-i", source.path,
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        *_codec(fmt, source, bits),
        "-ar", str(rate), "-ac", str(channels),
    ]
    if fmt.bitrates:
        args += ["-b:a", f"{fmt.bitrates[-1]}k"]
    args += list(fmt.extra)
    args += ["-f", fmt.muxer, "-progress", "pipe:1", "-nostats", str(target)]
    step = _Plan(source, fmt, target, args)
    return _run(step, on_progress)


def _codec(fmt: Format, source: Info, bits: int | None) -> list[str]:
    """The encoder for ``fmt``. Lossless targets keep the source's depth: a 16-bit WAV stays 16-bit."""
    if not fmt.lossless:
        return ["-c:a", fmt.encoder]
    depth = bits or source.bits or 24
    floating = bits is None and source.float
    if fmt.id == "flac":
        # FLAC is integer only, up to 24 bits here.
        return ["-c:a", "flac", "-sample_fmt", "s16"] if depth <= 16 else ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"]
    endian = "be" if fmt.id == "aiff" else "le"
    if floating:
        return ["-c:a", f"pcm_f32{endian}"]
    return ["-c:a", f"pcm_s{depth if depth in (16, 24, 32) else 24}{endian}"]


def _unused(path: Path) -> Path:
    """Never write over a file that is there, the original included: song.wav, then song 2.wav."""
    if not path.exists():
        return path
    number = 2
    while path.with_name(f"{path.stem} {number}{path.suffix}").exists():
        number += 1
    return path.with_name(f"{path.stem} {number}{path.suffix}")


def _run(step: _Plan, on_progress: Callable[[float], None] | None) -> Path:
    step.target.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    total = step.source.duration
    # Only ever remove what this call created. (A failed run once removed the source it was reading.)
    created = not step.target.exists()

    def discard() -> None:
        if created:
            step.target.unlink(missing_ok=True)

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
            discard()
            raise
        process.wait()
        reader.join(timeout=5)
    if process.returncode != 0:
        discard()
        tail = [line.strip() for line in errors if line.strip()][-3:]
        raise RuntimeError(" ".join(tail) or f"ffmpeg exited with {process.returncode}.")
    if on_progress:
        try:
            on_progress(1.0)
        except BaseException:
            # Stop pressed as the file finished: the same rule as during it, no file left behind.
            discard()
            raise
    return step.target


def _temp() -> Path:
    from ox1audio.action import temp

    return temp()


def _numpy():
    try:
        import numpy
    except ImportError:
        from ox1audio.action import _teach

        raise ImportError(_teach("ox.audio.read and ox.audio.write give samples as numpy arrays, and numpy isn't installed.", 'add "numpy" to pyproject.toml › [project].dependencies', "actions#helpers")) from None
    return numpy


def read(path: str | Path):
    """The samples of any file ffmpeg can open, as ``(samples, rate)``.

    ``samples`` is a float32 numpy array shaped ``(frames, channels)``, from -1 to 1.
    """
    np = _numpy()
    info = probe(path)
    result = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", "-i", info.path, "-map", "0:a:0", "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "-ac", str(info.channels), "-"],
        capture_output=True,
        timeout=3600,
    )
    if result.returncode != 0:
        from ox1audio.action import Problem

        raise Problem(f"{info.name} couldn't be read.", hint="Choose a WAV, AIFF, FLAC, MP3 or similar file.")
    samples = np.frombuffer(result.stdout, dtype="<f4")
    return samples[: samples.size // info.channels * info.channels].reshape(-1, info.channels).copy(), info.rate


def write(samples, rate: int, format_id: str = "wav", folder: str | Path | None = None, name: str = "audio", bits: int | None = None) -> Path:
    """Write samples (``(frames, channels)`` or one channel) as a new file and return it.

    It goes in ``folder`` (a new temporary folder when None) as ``name.<ext>``, never over
    a file that is there. WAV, AIFF and FLAC are 24-bit unless ``bits`` says 16 (or 32).
    """
    if bits is not None and bits not in (16, 24, 32):
        from ox1audio.action import _teach

        raise ValueError(_teach(f"ox.audio.write(bits={bits!r}): the bit depth is 16, 24 or 32.", 'ox.audio.write(samples, rate, "wav", bits=16)', "actions#helpers"))
    np = _numpy()
    data = np.asarray(samples, dtype="<f4")
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2 or data.shape[1] < 1 or data.shape[1] > 32:
        raise ValueError("ox.audio.write takes samples shaped (frames, channels).")
    fmt = find(format_id)
    rate = int(rate)
    out = Path(folder) if folder else _temp()
    out.mkdir(parents=True, exist_ok=True)
    target = _unused(out / f"{name}.{fmt.ext}")
    channels = data.shape[1] if fmt.max_channels is None else min(data.shape[1], fmt.max_channels)
    if fmt.rates and rate not in fmt.rates:
        lower = [item for item in fmt.rates if item <= rate]
        out_rate = max(lower) if lower else min(fmt.rates)
    else:
        out_rate = rate
    depth = Info(path="", name=name, codec="pcm_f32le", rate=rate, channels=data.shape[1], duration=0.0, bitrate=None, bits=24)
    args = [ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", "-f", "f32le", "-ar", str(rate), "-ac", str(data.shape[1]), "-i", "-", *_codec(fmt, depth, bits), "-ar", str(out_rate), "-ac", str(channels)]
    if fmt.bitrates:
        args += ["-b:a", f"{fmt.bitrates[-1]}k"]
    args += [*fmt.extra, "-f", fmt.muxer, str(target)]
    result = subprocess.run(args, input=np.ascontiguousarray(np.clip(data, -1, 1)).tobytes(), capture_output=True, timeout=3600)
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.decode(errors="replace").strip().splitlines()[-1:] or "The file couldn't be written.")
    return target
