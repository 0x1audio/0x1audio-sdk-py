"""The link to the host, the Library sink ``ox.test`` swaps in, and what a running action made."""

from __future__ import annotations

import contextvars
from typing import Callable

link_var: contextvars.ContextVar[object | None] = contextvars.ContextVar("ox_link", default=None)
sink_var: contextvars.ContextVar[Callable[[dict], object] | None] = contextvars.ContextVar("ox_sink", default=None)
# Every ox.sound/midi/file made while an action runs, so Stop can keep the finished ones.
made_var: contextvars.ContextVar[list | None] = contextvars.ContextVar("ox_made", default=None)
