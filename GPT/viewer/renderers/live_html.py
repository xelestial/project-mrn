"""Compatibility wrapper for the current live spectator HTML renderer."""

from __future__ import annotations

from .live_html_renderer import render_live_html as _render_live_html


def render_live_html(
    session_id: str = "",
    seed: int = 0,
    poll_interval_ms: int = 300,
) -> str:
    """Return the shared live spectator/playable HTML shell.

    The legacy Phase 3 call site still imports ``renderers.live_html``.
    Keep that import stable while routing to the newer unified renderer.
    """

    _ = (session_id, seed, poll_interval_ms)
    return _render_live_html()
