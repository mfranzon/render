"""Defensive wrapper around ``fontTools.ttLib.TTFont`` for build123d imports.

build123d traverses every system-font folder at import time
(``build123d.text`` runs ``FontManager().available_fonts`` at module level)
and does **not** wrap ``TTFont(path)`` in ``try/except``. A single un-parseable
font file therefore crashes the whole library on import.

This shim is platform-agnostic but in practice only fires on Windows, where
files like ``C:\\Windows\\Fonts\\mstmc.ttf`` (Microsoft Tai Le) raise
``TTLibError: Not a TrueType or OpenType font``. When that happens we return
a tiny stub font with a unique placeholder name so ``_get_font_faces`` can
register it as a no-op rather than aborting the rest of the folder.

Import this module **before** any ``import build123d`` — the standard place
is from a ``sitecustomize.py`` inside the render venv. setup.sh installs it
there on first run.
"""

from __future__ import annotations

import fontTools.ttLib as _ttlib

_real_TTFont = _ttlib.TTFont
_skipped_counter = [0]


class _NameRecord:
    """Minimal fontTools name-record stand-in."""

    def __init__(self, name_id: int, value: str) -> None:
        self.nameID = name_id
        self._value = value

    def toUnicode(self) -> str:
        return self._value


class _NameTable:
    """Just enough of fontTools' name table for build123d._get_font_faces."""

    def __init__(self, family: str) -> None:
        # nameID 1 = font family; nameID 2 = subfamily ("Regular").
        # Anything else build123d may probe is intentionally absent.
        self.names = [
            _NameRecord(1, family),
            _NameRecord(2, "Regular"),
        ]


class _StubFont:
    """A TTFont look-alike that exposes only what build123d touches.

    Used in place of a TTFont that fontTools refuses to parse. The font is
    registered with a synthetic, unique name so it cannot collide with any
    real installed font and so build123d's empty-name guard does not trip.
    """

    def __init__(self) -> None:
        _skipped_counter[0] += 1
        self._family = f"_unparseable_font_{_skipped_counter[0]}"

    def __getitem__(self, key: str):
        if key == "name":
            return _NameTable(self._family)
        raise KeyError(key)

    def __contains__(self, key: str) -> bool:  # build123d checks ``"fvar" in ft_font``
        return False


def _safe_TTFont(*args, **kwargs):
    try:
        return _real_TTFont(*args, **kwargs)
    except _ttlib.TTLibError:
        return _StubFont()


# Only patch once, even if this module is imported multiple times.
if getattr(_ttlib.TTFont, "__name__", "") != "_safe_TTFont":
    _safe_TTFont.__name__ = "_safe_TTFont"
    _ttlib.TTFont = _safe_TTFont
