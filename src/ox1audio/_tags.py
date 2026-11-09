"""What a converted copy keeps besides its samples: tags, cover art, BPM, key and loop points (GAB-134).

ffmpeg copies the usual tags (title, artist, album...) itself. This module reads the rest from the
source and writes it the way each format holds it:

| Format | Cover | BPM | Key | Loop points |
| --- | --- | --- | --- | --- |
| WAV | ID3 chunk | ID3 chunk, acid | ID3 chunk, acid (root note) | smpl (cue and acid copied from a WAV) |
| AIFF | ID3 chunk | ID3 chunk | ID3 chunk | MARK + INST |
| FLAC | picture | BPM | KEY | LOOPSTART, LOOPLENGTH |
| MP3 | APIC | TBPM | TKEY | none |
| AAC (.m4a) | covr | tmpo | none | none |
| Ogg, Opus | none | BPM | KEY | LOOPSTART, LOOPLENGTH |
"""

from __future__ import annotations

import re
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PICTURE_FORMATS = {"mp3", "aac", "flac", "aiff"}
_NOTES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass
class Extras:
    bpm: float | None = None
    key: str | None = None
    # (start, end) in frames at the source's rate, end included, as WAV smpl has them.
    loops: list[tuple[int, int]] = field(default_factory=list)
    cover: bool = False
    # A WAV source's own chunks, copied as they are into a WAV copy: "smpl", "cue ", "acid".
    chunks: dict[str, bytes] = field(default_factory=dict)
    source: Path | None = None


def read(path: Path) -> Extras:
    from ox1audio.audio import ffmpeg

    extras = Extras(source=path)
    done = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-i", str(path)], capture_output=True, text=True, errors="replace", timeout=60)
    tags = _metadata(done.stderr)
    extras.cover = "(attached pic)" in done.stderr
    extras.bpm = _number(tags.get("tbpm") or tags.get("bpm") or tags.get("tmpo"))
    extras.key = tags.get("tkey") or tags.get("key") or tags.get("initialkey") or None
    start = _number(tags.get("loopstart"))
    if start is not None:
        length, end = _number(tags.get("looplength")), _number(tags.get("loopend"))
        if length:
            extras.loops = [(int(start), int(start + length) - 1)]
        elif end:
            extras.loops = [(int(start), int(end) - 1)]
    with path.open("rb") as handle:
        head = handle.read(12)
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        _read_wav(path, extras)
    elif head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        _read_aiff(path, extras)
    elif extras.bpm is None and path.suffix.lower() in (".m4a", ".mp4", ".aac"):
        extras.bpm = _mp4_tempo(path)
    return extras


def metadata_args(format_id: str, extras: Extras, ratio: float) -> list[str]:
    """ffmpeg output options that write BPM, key and loop tags into ``format_id``."""
    out: list[str] = []
    bpm = _bpm_text(extras.bpm)
    if format_id == "mp3":
        out += ["-metadata", f"TBPM={bpm}"] if bpm else []
        out += ["-metadata", f"TKEY={extras.key}"] if extras.key else []
    elif format_id == "aac":
        out += ["-metadata", f"tmpo={round(extras.bpm)}"] if extras.bpm else []
    elif format_id in ("flac", "ogg", "opus"):
        out += ["-metadata", f"BPM={bpm}"] if bpm else []
        out += ["-metadata", f"KEY={extras.key}"] if extras.key else []
        if extras.loops:
            start, end = extras.loops[0]
            out += ["-metadata", f"LOOPSTART={round(start * ratio)}", "-metadata", f"LOOPLENGTH={round((end - start + 1) * ratio)}"]
    elif format_id == "aiff":
        out += ["-write_id3v2", "1", "-id3v2_version", "3"]
        out += ["-metadata", f"TBPM={bpm}"] if bpm else []
        out += ["-metadata", f"TKEY={extras.key}"] if extras.key else []
    return out


def finish(target: Path, format_id: str, extras: Extras) -> None:
    """Add what ffmpeg can't write: WAV chunks, and AIFF loop markers."""
    if format_id == "wav":
        _finish_wav(target, extras)
    elif format_id == "aiff" and extras.loops:
        start, end = extras.loops[0]
        mark = struct.pack(">H", 2) + _marker(1, start, "Loop start") + _marker(2, end + 1, "Loop end")
        # INST: base note 60, no detune, full ranges; a forward sustain loop between markers 1 and 2.
        inst = struct.pack(">bbbbbbh", 60, 0, 0, 127, 1, 127, 0) + struct.pack(">hhh", 1, 1, 2) + struct.pack(">hhh", 0, 0, 0)
        _append(target, [(b"MARK", mark), (b"INST", inst)], big=True)


# --- reading ----------------------------------------------------------------------------------


def _metadata(report: str) -> dict[str, str]:
    """Every "Metadata:" block of ffmpeg's report on the input, lowercased keys, the file's own first.

    Ogg and Opus keep their tags on the stream, so stream blocks count too (never overriding the file's).
    """
    tags: dict[str, str] = {}
    depth = None
    for line in report.splitlines():
        if line.startswith("Output") or line.startswith("At least one output"):
            break
        indent = len(line) - len(line.lstrip())
        if line.strip() == "Metadata:":
            depth = indent
            continue
        if depth is None:
            continue
        if indent <= depth:
            depth = None
            continue
        key, sep, value = line.strip().partition(":")
        if sep and key.strip():
            tags.setdefault(key.strip().lower(), value.strip())
    return tags



# Only these small chunks are read into memory; the audio itself (data, SSND) is skipped by seeking,
# so a file of any size is read in constant memory.
_WANTED = {b"smpl", b"cue ", b"acid", b"MARK", b"INST"}
_MAX_CHUNK = 1 << 20


def _chunks(path: Path, big: bool):
    order = ">I" if big else "<I"
    with path.open("rb") as handle:
        total = handle.seek(0, 2)
        at = 12
        while at + 8 <= total:
            handle.seek(at)
            header = handle.read(8)
            if len(header) < 8:
                return
            cid = header[:4]
            size = struct.unpack(order, header[4:8])[0]
            if cid in _WANTED and size <= _MAX_CHUNK:
                yield cid, handle.read(size)
            at += 8 + size + (size & 1)


def _read_wav(path: Path, extras: Extras) -> None:
    for cid, body in _chunks(path, big=False):
        if cid == b"smpl" and len(body) >= 36:
            count = struct.unpack("<I", body[28:32])[0]
            loops = []
            for n in range(min(count, 16)):
                at = 36 + 24 * n
                if at + 24 <= len(body):
                    start, end = struct.unpack("<II", body[at + 8 : at + 16])
                    loops.append((start, end))
            if loops:
                extras.loops = loops
            extras.chunks["smpl"] = body
        elif cid == b"cue ":
            extras.chunks["cue "] = body
        elif cid == b"acid" and len(body) >= 24:
            extras.chunks["acid"] = body
            flags, root = struct.unpack("<IH", body[:6])
            tempo = struct.unpack("<f", body[20:24])[0]
            if extras.bpm is None and 20 <= tempo <= 999:
                extras.bpm = round(tempo, 3)
            if extras.key is None and flags & 2 and 48 <= root <= 59:
                extras.key = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"][root - 48]


def _read_aiff(path: Path, extras: Extras) -> None:
    markers: dict[int, int] = {}
    sustain = None
    for cid, body in _chunks(path, big=True):
        if cid == b"MARK" and len(body) >= 2:
            at = 2
            for _ in range(struct.unpack(">H", body[:2])[0]):
                if at + 7 > len(body):
                    break
                mid, position, length = struct.unpack(">hIB", body[at : at + 7])
                markers[mid] = position
                at += 7 + length + (0 if length % 2 else 1)
        elif cid == b"INST" and len(body) >= 20:
            mode, begin, end = struct.unpack(">hhh", body[8:14])
            if mode:
                sustain = (begin, end)
    if sustain and sustain[0] in markers and sustain[1] in markers and markers[sustain[1]] > markers[sustain[0]]:
        extras.loops = [(markers[sustain[0]], markers[sustain[1]] - 1)]


def _mp4_tempo(path: Path) -> float | None:
    """The iTunes tmpo atom, found by reading the file 1 MB at a time."""
    block = 1 << 20
    with path.open("rb") as handle:
        carry = b""
        while True:
            data = handle.read(block)
            if not data:
                return None
            window = carry + data
            at = window.find(b"tmpo")
            if at >= 0:
                window += handle.read(32)
                if window[at + 8 : at + 12] != b"data" or at + 22 > len(window):
                    return None
                tempo = struct.unpack(">H", window[at + 20 : at + 22])[0]
                return float(tempo) if tempo else None
            carry = window[-8:]


# --- writing ----------------------------------------------------------------------------------


def _finish_wav(target: Path, extras: Extras) -> None:
    chunks: list[tuple[bytes, bytes]] = []
    for name in ("smpl", "cue ", "acid"):
        if name in extras.chunks:
            chunks.append((name.encode(), extras.chunks[name]))
    from ox1audio.audio import probe

    info = probe(target)
    if "smpl" not in extras.chunks and extras.loops:
        start, end = extras.loops[0]
        header = struct.pack("<9I", 0, 0, int(1e9 / info.rate), _root(extras.key) or 60, 0, 0, 0, 1, 0)
        chunks.append((b"smpl", header + struct.pack("<6I", 0, 0, start, end, 0, 0)))
    if "acid" not in extras.chunks and extras.bpm:
        root = _root(extras.key)
        beats = max(1, round(info.duration * extras.bpm / 60))
        flags = (0x02 if root is not None else 0) | (0x00 if extras.loops or beats > 1 else 0x01)
        chunks.append((b"acid", struct.pack("<IHHfIHHf", flags, (root or 60) - 12, 0x8000, 0.0, beats, 4, 4, float(extras.bpm))))
    frames = []
    if extras.bpm:
        frames.append(_text_frame(b"TBPM", _bpm_text(extras.bpm) or ""))
    if extras.key:
        frames.append(_text_frame(b"TKEY", extras.key))
    picture = _cover(extras) if extras.cover else None
    if picture:
        frames.append(picture)
    if frames:
        body = b"".join(frames)
        size = len(body)
        synchsafe = bytes([(size >> 21) & 0x7F, (size >> 14) & 0x7F, (size >> 7) & 0x7F, size & 0x7F])
        chunks.append((b"id3 ", b"ID3\x03\x00\x00" + synchsafe + body))
    if chunks:
        _append(target, chunks, big=False)


def _append(target: Path, chunks: list[tuple[bytes, bytes]], big: bool) -> None:
    """Add chunks at the end of a RIFF or FORM file in place, and fix its size: constant memory."""
    order = ">I" if big else "<I"
    with target.open("r+b") as handle:
        end = handle.seek(0, 2)
        if end & 1:
            handle.write(b"\0")
            end += 1
        for cid, body in chunks:
            handle.write(cid + struct.pack(order, len(body)) + body + (b"\0" if len(body) & 1 else b""))
        end = handle.tell()
        if end - 8 > 0xFFFFFFFF:
            return  # past what a RIFF size can say: leave the header as ffmpeg wrote it
        handle.seek(4)
        handle.write(struct.pack(order, end - 8))


def _marker(mid: int, position: int, name: str) -> bytes:
    text = name.encode("ascii")
    pstring = bytes([len(text)]) + text + (b"" if (len(text) + 1) % 2 == 0 else b"\0")
    return struct.pack(">hI", mid, position) + pstring


def _text_frame(fid: bytes, text: str) -> bytes:
    try:
        body = b"\x00" + text.encode("latin-1")
    except UnicodeEncodeError:
        body = b"\x01" + text.encode("utf-16")
    return fid + struct.pack(">I", len(body)) + b"\0\0" + body


def _cover(extras: Extras) -> bytes | None:
    from ox1audio.audio import ffmpeg

    if extras.source is None:
        return None
    done = subprocess.run(
        [ffmpeg(), "-hide_banner", "-nostdin", "-v", "error", "-i", str(extras.source), "-map", "0:v:disp:attached_pic", "-c", "copy", "-frames:v", "1", "-f", "image2pipe", "-"],
        capture_output=True,
        timeout=60,
    )
    image = done.stdout
    if done.returncode != 0 or not image or len(image) > 8 * 1024 * 1024:
        return None
    mime = b"image/png" if image[:8] == b"\x89PNG\r\n\x1a\n" else b"image/jpeg"
    body = b"\x00" + mime + b"\x00" + b"\x03" + b"\x00" + image
    return b"APIC" + struct.pack(">I", len(body)) + b"\0\0" + body


def _root(key: str | None) -> int | None:
    """The MIDI note (C4 = 60) of a key's tonic: "D minor", "Dm", "F#", "Bb major"."""
    if not key:
        return None
    found = re.match(r"\s*([A-Ga-g])([#b♯♭]?)", key)
    if not found:
        return None
    note = _NOTES[found.group(1).upper()] + {"#": 1, "♯": 1, "b": -1, "♭": -1}.get(found.group(2), 0)
    return 60 + note % 12


def _number(value: str | None) -> float | None:
    if not value:
        return None
    found = re.match(r"\s*(\d+(?:\.\d+)?)", value)
    return float(found.group(1)) if found else None


def _bpm_text(bpm: float | None) -> str | None:
    if not bpm:
        return None
    return str(int(bpm)) if float(bpm).is_integer() else f"{bpm:g}"
