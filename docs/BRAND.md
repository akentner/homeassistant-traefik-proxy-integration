# Brand images

This document records where the brand images in
`custom_components/traefik_proxy/brand/` come from, under which terms they are
used, and how to rebuild them from the vector sources in `docs/`.

Home Assistant serves these PNG files to its frontend and to the Marketplace
(`/api/brands/integration/traefik_proxy/<image>`). SVG files are not served,
so the vector sources live here in `docs/` and are not shipped by HACS.

## Files

| Shipped file (`brand/`) | Size (px) | Vector source | Upstream component |
|---|---|---|---|
| `icon.png` | 256 x 256 | `docs/icon.svg` | `Logo` (small-screen mark) |
| `icon@2x.png` | 512 x 512 | `docs/icon.svg` | `Logo` (small-screen mark) |
| `logo.png` | 337 x 128 | `docs/logo.svg` | `ProxyLogo`, black wordmark |
| `logo@2x.png` | 674 x 256 | `docs/logo.svg` | `ProxyLogo`, black wordmark |
| `dark_logo.png` | 337 x 128 | `docs/logo-dark.svg` | `ProxyLogo`, white wordmark |
| `dark_logo@2x.png` | 674 x 256 | `docs/logo-dark.svg` | `ProxyLogo`, white wordmark |

`brand/` holds exactly these six files. `tests/test_brand.py` pins their
sizes, trimming, mode (RGBA), interlacing, the file set and the wordmark
contrast.

## Source

- Repository: [traefik/traefik](https://github.com/traefik/traefik)
- File: `webui/src/components/icons/Logo.tsx`
- Tag: `v3.7.19`, commit `7dafd6dba371bd1aee70c443c2975c229c969711`
- `Logo` (`viewBox="0 0 101 103"`) is the small-screen mark of the Traefik
  Proxy dashboard; it is the source of `docs/icon.svg`.
- `ProxyLogo` (`viewBox="0 0 280 108"`) is the landscape "traefik proxy"
  lockup: the mark in `#2AA2C1` and the wordmark in `textColor` (default
  `#000`; the dashboard passes `#fff` in dark mode). It is the source of
  `docs/logo.svg` (`#000`) and `docs/logo-dark.svg` (`#fff`).

The JSX element was converted to a standalone SVG by text substitution only:
`fill={textColor}` became `fill="#000"` (or `fill="#fff"`), the `clipPath`
attribute became `clip-path`, the `{...props}` spread was dropped, and a
provenance comment was added. The path data is unchanged. `xmllint --noout`
accepts all three SVG files.

## Licence

The file is part of the traefik/traefik repository, which is published under
the MIT licence (`LICENSE.md` at tag `v3.7.19`):

```text
The MIT License (MIT)

Copyright (c) 2016-2020 Containous SAS; 2020-2025 Traefik Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```

## Trademark

Traefik is a trademark of Traefik Labs, and the Traefik logo is its brand
artwork. The MIT licence covers the copyright of the artwork file, not the
trademark. This project is not affiliated with or endorsed by Traefik Labs;
the logo is used only to identify the software this integration connects to.

## Export commands

Run from the repository root with `rsvg-convert` (librsvg) and ImageMagick 7
(`magick`). `big.png` is a temporary file.

Icons (trimmed, centred on a square transparent canvas):

```sh
rsvg-convert -w 2048 -h 2048 --keep-aspect-ratio docs/icon.svg -o big.png
magick big.png -trim +repage -resize 256x256 -background none -gravity center -extent 256x256 -strip -define png:color-type=6 -interlace PNG custom_components/traefik_proxy/brand/icon.png
magick big.png -trim +repage -resize 512x512 -background none -gravity center -extent 512x512 -strip -define png:color-type=6 -interlace PNG custom_components/traefik_proxy/brand/icon@2x.png
```

Logo (trimmed to the artwork, landscape):

```sh
rsvg-convert -h 1024 --keep-aspect-ratio docs/logo.svg -o big.png
magick big.png -trim +repage -resize x128 -strip -define png:color-type=6 -interlace PNG custom_components/traefik_proxy/brand/logo.png
magick big.png -trim +repage -resize x256 -strip -define png:color-type=6 -interlace PNG custom_components/traefik_proxy/brand/logo@2x.png
```

Dark-theme logo (same pipeline, white wordmark):

```sh
rsvg-convert -h 1024 --keep-aspect-ratio docs/logo-dark.svg -o big.png
magick big.png -trim +repage -resize x128 -strip -define png:color-type=6 -interlace PNG custom_components/traefik_proxy/brand/dark_logo.png
magick big.png -trim +repage -resize x256 -strip -define png:color-type=6 -interlace PNG custom_components/traefik_proxy/brand/dark_logo@2x.png
```

Check the geometry on the alpha channel (trimming on the corner colour reports
a wrong offset for RGBA images):

```sh
magick custom_components/traefik_proxy/brand/logo.png -alpha extract -format %@ info:
```

Expected: `256x231+0+12` (`icon.png`), `512x461+0+25` (`icon@2x.png`),
`337x128+0+0` (`logo.png`, `dark_logo.png`), `674x256+0+0` (`logo@2x.png`,
`dark_logo@2x.png`).

## Why `dark_logo` exists and `dark_icon` does not

On a dark theme the frontend looks for `dark_logo.png`, then `dark_icon.png`,
then `logo.png`, then `icon.png`. Without `dark_logo.png` it would fall back
to `logo.png`, whose black wordmark is unreadable on a dark background. The
dark logo is the same lockup with the white wordmark the Traefik dashboard
itself uses in dark mode.

The icon is only the teal mark (`#2AA2C1`), which reads well on both light
and dark backgrounds, so no `dark_icon.png` is shipped and the dark theme
falls back to `icon.png`.
