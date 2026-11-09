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
_known = {"mono": 1, "stereo": 2, "2.1": 3, "3.0": 3, "quad": 4, "4.0": 4, "5.0": 5, "5.1": 6, "6.1": 7, "7.1": 8}


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


@functools.cache
def _layouts() -> dict[str, int]:
    """Every standard layout this ffmpeg knows, with its channel count: "hexagonal" is 6 (GAB-135)."""
    table = dict(_known)
    try:
        listed = subprocess.run([ffmpeg(), "-hide_banner", "-layouts"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return table
    standard = listed.split("Standard channel layouts:", 1)[-1]
    for line in standard.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] != "NAME":
            table[parts[0]] = len(parts[1].split("+"))
    return table


def channel_count(layout: str) -> int:
    layout = layout.strip()
    counted = re.match(r"(\d+) channels", layout)
    if counted:
        return int(counted.group(1))
    table = _layouts()
    name = layout.split(" ")[0]
    if name in table:
        return table[name]
    if name.split("(")[0] in table:
        return table[name.split("(")[0]]
    # A custom layout like "FL+FR+LFE": one channel per name.
    if "+" in name:
        return len(name.split("+"))
    raise ValueError(f"The channel layout {layout!r} isn't one Mixel knows, so its channels can't be counted.")


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
    ``bits=16`` or ``24`` asks for another, and ``bits=32`` is 32-bit float (WAV and AIFF).
    Going to fewer bits adds TPDF dither, so quiet audio doesn't distort.
    Tags, cover art, BPM, key and loop points come along wherever the format can hold them.
    """
    _check_bits("convert", bits)
    source = probe(path)
    fmt = find(format_id)
    _check_float(fmt, bits, "convert")
    out = Path(folder) if folder else _temp()
    target = _unused(out / f"{Path(source.name).stem}.{fmt.ext}")
    channels = source.channels if fmt.max_channels is None else min(source.channels, fmt.max_channels)
    rate = source.rate
    if fmt.rates and rate not in fmt.rates:
        lower = [item for item in fmt.rates if item <= rate]
        rate = max(lower) if lower else min(fmt.rates)
    from ox1audio import _tags

    extras = _tags.read(Path(source.path))
    codec, dither = _codec(fmt, source, bits)
    args = [ffmpeg(), "-hide_banner", "-nostdin", "-y", "-i", source.path, "-map", "0:a:0"]
    # Cover art rides along where the format holds a picture; everything else stays behind.
    picture = fmt.id in _tags.PICTURE_FORMATS and extras.cover
    args += ["-map", "0:v:disp:attached_pic?", "-c:v", "copy", "-disposition:v", "attached_pic"] if picture else ["-vn"]
    args += ["-sn", "-dn", *codec]
    if dither:
        args += ["-af", dither]
    args += ["-ar", str(rate)]
    # Only ever fewer channels, when the format can't hold more: never a remix of a known layout (GAB-135).
    if channels != source.channels:
        args += ["-ac", str(channels)]
    if fmt.bitrates:
        args += ["-b:a", f"{fmt.bitrates[-1]}k"]
    args += [*fmt.extra, *_tags.metadata_args(fmt.id, extras, rate / source.rate if source.rate else 1.0)]
    args += ["-f", fmt.muxer, "-progress", "pipe:1", "-nostats", str(target)]
    step = _Plan(source, fmt, target, args)
    done = _run(step, on_progress)
    try:
        _tags.finish(done, fmt.id, extras)
    except BaseException:
        done.unlink(missing_ok=True)
        raise
    return done


def _check_bits(name: str, bits: int | None) -> None:
    if bits is not None and (isinstance(bits, bool) or bits not in (16, 24, 32)):
        from ox1audio.action import _teach

        example = 'ox.audio.convert(path, "wav", bits=16)' if name == "convert" else 'ox.audio.write(samples, rate, "wav", bits=16)'
        raise ValueError(_teach(f"ox.audio.{name}(bits={bits!r}): the bit depth is 16, 24, or 32 for float.", example, "audio#bit-depth"))


def _check_float(fmt: Format, bits: int | None, name: str) -> None:
    if bits == 32 and fmt.id not in ("wav", "aiff"):
        from ox1audio.action import _teach

        raise ValueError(_teach(f"ox.audio.{name}(..., \"{fmt.id}\", bits=32): 32 bits is float, which only WAV and AIFF hold.", f'"wav" with bits=32, or "{fmt.id}" with bits=24' if fmt.lossless else '"wav" with bits=32', "audio#bit-depth"))


def _codec(fmt: Format, source: Info, bits: int | None) -> tuple[list[str], str | None]:
    """The encoder for ``fmt``, and the dither filter when the depth goes down (GAB-132).

    Lossless targets keep the source's depth: a 16-bit WAV stays 16-bit, bit for bit.
    ``bits=32`` is 32-bit float. A float source stays float in WAV and AIFF unless ``bits`` says otherwise.
    """
    if not fmt.lossless:
        return ["-c:a", fmt.encoder], None
    endian = "be" if fmt.id == "aiff" else "le"
    floating = bits == 32 or (bits is None and source.float and fmt.id != "flac")
    if floating:
        return ["-c:a", f"pcm_f32{endian}"], None
    # 32-bit integer sources become 24-bit: FLAC holds 24 at most, and float is how to keep more.
    depth = bits or (source.bits if source.bits in (16, 24) else 24)
    # Lossy and float sources have more precision than any integer depth; so does 32-bit integer.
    deeper = source.float or source.bits is None or source.bits > depth
    if depth == 16:
        codec = ["-c:a", "flac", "-sample_fmt", "s16"] if fmt.id == "flac" else ["-c:a", f"pcm_s16{endian}"]
        return codec, "aresample=osf=s16:dither_method=triangular" if deeper else None
    codec = ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"] if fmt.id == "flac" else ["-c:a", f"pcm_s24{endian}"]
    # 24 bits travel in a 32-bit container: dither at the 24th bit (2^8 of the container's last bit).
    return codec, "aresample=osf=s32:dither_method=triangular:dither_scale=256" if deeper else None


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
        # No -ac: every channel as it is, never a downmix (GAB-135).
        [ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", "-i", info.path, "-map", "0:a:0", "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "-"],
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
    a file that is there. WAV, AIFF and FLAC are 24-bit unless ``bits`` says 16, or 32 for
    float (WAV and AIFF). Fewer bits than the samples carry get TPDF dither; samples that
    already fit the depth are written exactly. Samples over full scale (above 1.0) are
    refused rather than clipped, unless the file is float.
    """
    _check_bits("write", bits)
    np = _numpy()
    data = np.asarray(samples, dtype="<f4")
    if data.ndim == 1:
        data = data[:, None]
    if data.ndim != 2 or data.shape[1] < 1 or data.shape[1] > 32:
        raise ValueError("ox.audio.write takes samples shaped (frames, channels).")
    fmt = find(format_id)
    _check_float(fmt, bits, "write")
    from ox1audio.action import _teach

    if not np.isfinite(data).all():
        raise ValueError(_teach("ox.audio.write: the samples have NaN or infinite values.", "find the division by zero or the empty mean that made them", "audio#levels"))
    floating = fmt.lossless and bits == 32
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 1.0 and not floating:
        import math

        over = 20 * math.log10(peak)
        what = f"{bits or 24}-bit {fmt.label}" if fmt.lossless else fmt.label
        raise ValueError(_teach(
            f"ox.audio.write: the samples peak at +{over:.1f} dBFS, over full scale, so {what} would clip them.",
            f"lower the gain (samples * {math.floor(1 / peak * 100) / 100}), or write \"wav\" with bits=32 (float keeps overs)",
            "audio#levels",
        ))
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
    endian = "be" if fmt.id == "aiff" else "le"
    if not fmt.lossless:
        raw, codec = ("f32le", np.ascontiguousarray(data).tobytes()), ["-c:a", fmt.encoder]
    elif floating:
        raw, codec = ("f32le", np.ascontiguousarray(data).tobytes()), ["-c:a", f"pcm_f32{endian}"]
    else:
        depth = bits or 24
        pcm = _quantize(np, data, depth)
        if depth == 16:
            raw = ("s16le", pcm.astype("<i2").tobytes())
            codec = ["-c:a", "flac", "-sample_fmt", "s16"] if fmt.id == "flac" else ["-c:a", f"pcm_s16{endian}"]
        else:
            # 24 bits in a 32-bit container, low byte zero, so the encoder keeps them exactly.
            raw = ("s32le", (pcm.astype("<i4") << 8).tobytes())
            codec = ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"] if fmt.id == "flac" else ["-c:a", f"pcm_s24{endian}"]
    args = [ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", "-f", raw[0], "-ar", str(rate), "-ac", str(data.shape[1]), "-i", "-", *codec, "-ar", str(out_rate)]
    if channels != data.shape[1]:
        args += ["-ac", str(channels)]
    if fmt.bitrates:
        args += ["-b:a", f"{fmt.bitrates[-1]}k"]
    args += [*fmt.extra, "-f", fmt.muxer, str(target)]
    result = subprocess.run(args, input=raw[1], capture_output=True, timeout=3600)
    if result.returncode != 0:
        target.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.decode(errors="replace").strip().splitlines()[-1:] or "The file couldn't be written.")
    return target


def _quantize(np, data, depth: int):
    """Samples as integers at ``depth`` bits: exact when they already fit, else with TPDF dither (GAB-132)."""
    scale = float(2 ** (depth - 1))
    scaled = data.astype(np.float64) * scale
    rounded = np.round(scaled)
    if not np.array_equal(scaled, rounded):
        # Triangular dither of one step, the same every run so outputs can be compared.
        noise = np.random.default_rng(0x0A0D10)
        rounded = np.round(scaled + noise.random(scaled.shape) - noise.random(scaled.shape))
    return np.clip(rounded, -scale, scale - 1).astype(np.int32)
