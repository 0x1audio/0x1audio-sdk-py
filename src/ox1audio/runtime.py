"""The worker link for the call that is running."""

from __future__ import annotations

import contextvars
from typing import Callable

link_var: contextvars.ContextVar[object | None] = contextvars.ContextVar("ox_link", default=None)
sink_var: contextvars.ContextVar[Callable[[dict], object] | None] = contextvars.ContextVar("ox_sink", default=None)
