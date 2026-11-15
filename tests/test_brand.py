"""Geometry guards for the brand images shipped in ``brand/``.

Home Assistant serves the PNG files under ``custom_components/traefik_proxy/brand/``
to its frontend and to the Marketplace. Its brand rules ask for trimmed images
(no padding around the artwork), lossless and interlaced PNGs with a
transparent background, and square icons of 256x256 (``@2x``: 512x512). SVG is
not served, so the vector source lives in ``docs/`` instead.

These checks read the shipped files with Pillow (a Home Assistant core
dependency) and measure the artwork on the alpha channel, because trimming on
the corner colour reports a wrong offset for RGBA images. The helpers check
themselves against planted samples, so the guard cannot pass vacuously.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "custom_components" / "traefik_proxy"
BRAND = PACKAGE / "brand"

# Icon file name -> required square edge in pixels.
ICONS = {"icon.png": 256, "icon@2x.png": 512}
# Shipped images stay well below the repository's 500 KB large-file hook.
MAX_IMAGE_BYTES = 500 * 1024
# Allowed difference between the two margins on the axis the artwork does not fill.
CENTRE_TOLERANCE_PX = 1

type Box = tuple[int, int, int, int]


def open_image(path: Path) -> Image.Image:
    """Open an image and load its pixels, so the file handle is closed on return."""
    with Image.open(path) as image:
        image.load()
        return image


def alpha_bbox(image: Image.Image) -> Box:
    """Return the bounding box (left, top, right, bottom) of all non-transparent pixels."""
    bbox = image.getchannel("A").getbbox()
    assert bbox is not None, "image is fully transparent"
    return bbox


def margins(image: Image.Image) -> Box:
    """Return the transparent margins (left, top, right, bottom) around the artwork."""
    left, top, right, bottom = alpha_bbox(image)
    width, height = image.size
    return left, top, width - right, height - bottom


def trim_problems(image: Image.Image) -> list[str]:
    """Describe why the artwork is not trimmed to two opposite edges and centred on the other axis."""
    left, top, right, bottom = margins(image)
    if left == 0 and right == 0:
        if abs(top - bottom) > CENTRE_TOLERANCE_PX:
            return [f"not centred vertically: top {top} px, bottom {bottom} px"]
        return []
    if top == 0 and bottom == 0:
        if abs(left - right) > CENTRE_TOLERANCE_PX:
            return [f"not centred horizontally: left {left} px, right {right} px"]
        return []
    return [f"padded on every axis: margins left {left}, top {top}, right {right}, bottom {bottom} px"]


def _planted(size: tuple[int, int], box: Box) -> Image.Image:
    """Return a transparent RGBA image with an opaque rectangle covering ``box``."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    image.paste((42, 162, 193, 255), box)
    return image


@pytest.mark.parametrize(
    ("box", "trimmed"),
    [
        ((0, 12, 256, 243), True),  # full width, 12/13 px top/bottom
        ((10, 0, 246, 256), True),  # full height, centred
        ((0, 0, 256, 256), True),  # fills the canvas
        ((13, 25, 238, 228), False),  # the padded, off-centre icon the re-export replaced
        ((0, 10, 256, 240), False),  # full width, but 10/16 px top/bottom
        ((0, 0, 250, 256), False),  # touches only three edges
    ],
)
def test_trim_helper_against_planted_samples(box: Box, trimmed: bool) -> None:
    """The trim/centre detector accepts trimmed samples and rejects padded or off-centre ones."""
    image = _planted((256, 256), box)
    assert alpha_bbox(image) == box
    assert (trim_problems(image) == []) is trimmed


@pytest.mark.parametrize(("name", "edge"), ICONS.items())
def test_icon_size_mode_and_interlacing(name: str, edge: int) -> None:
    """Each icon is a square RGBA PNG of the required size, interlaced and below the size gate."""
    path = BRAND / name
    image = open_image(path)
    assert image.format == "PNG"
    assert image.size == (edge, edge)
    assert image.mode == "RGBA"
    assert image.info.get("interlace"), f"{name} is not interlaced"
    assert path.stat().st_size < MAX_IMAGE_BYTES


@pytest.mark.parametrize("name", ICONS)
def test_icon_is_trimmed_and_centred(name: str) -> None:
    """The icon artwork touches two opposite edges and is centred on the other axis."""
    image = open_image(BRAND / name)
    assert trim_problems(image) == [], f"{name}: alpha bbox {alpha_bbox(image)}"


def test_brand_folder_ships_no_svg() -> None:
    """SVG is not served from ``brand/``; the vector source lives in ``docs/``."""
    assert sorted(p.name for p in BRAND.rglob("*.svg")) == []
