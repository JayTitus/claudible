"""Pre-generated tray icons for claudible.

Icons are rendered to ~/.cache/claudible/icons/ using Pillow BEFORE pystray
is imported, avoiding the GTK/Pillow freetype corruption on KDE Plasma.
After generation, icons are loaded from disk — no Pillow drawing needed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from claudible.paths import CACHE_DIR

if TYPE_CHECKING:
    from PIL import Image

ICONS_DIR = CACHE_DIR / "icons"

_ICON_COLORS = {
    "active": "#22c55e",
    "inactive": "#6b7280",
    "error": "#ef4444",
    "listening": "#f59e0b",
}


def ensure_icons(size: int = 64) -> None:
    """Generate icon PNGs to cache dir if they don't already exist.

    Must be called BEFORE pystray is imported to avoid Pillow/GTK conflict.
    """
    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    all_exist = all((ICONS_DIR / f"{name}.png").exists() for name in _ICON_COLORS)
    if all_exist:
        return

    from PIL import Image as _Image
    from PIL import ImageDraw

    for name, color in _ICON_COLORS.items():
        img = _Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([2, 2, size - 3, size - 3], fill=color)
        inset = size // 4
        draw.ellipse(
            [inset, inset, size - inset - 1, size - inset - 1],
            fill="white",
            outline=None,
        )
        img.save(ICONS_DIR / f"{name}.png")


def load_icon(name: str) -> Image.Image:
    """Load a pre-generated icon PNG from cache. Safe to call after pystray import."""
    from PIL import Image as _Image

    path = ICONS_DIR / f"{name}.png"
    if not path.exists():
        raise FileNotFoundError(
            f"Icon '{name}' not found at {path}. Call ensure_icons() first."
        )
    return _Image.open(path)


def icon_active() -> Image.Image:
    return load_icon("active")


def icon_inactive() -> Image.Image:
    return load_icon("inactive")


def icon_error() -> Image.Image:
    return load_icon("error")


def icon_listening() -> Image.Image:
    return load_icon("listening")
