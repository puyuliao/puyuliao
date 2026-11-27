#!/usr/bin/env python3
"""Generate theme-aware Gemini Hagemi neofetch SVG cards and plain-text ASCII art."""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SPRITE = Path(
    "/home/puyu/.gemini/config/plugins/hagemi-pet-agy/sidecars/pet/art/idle.webp"
)
ASSETS_DIR = REPO_ROOT / "assets"

ASCII_RAMP = "@#%MW8B&*$+=:-"
MONO_FONT = (
    "'DejaVu Sans Mono', 'JetBrains Mono', 'Fira Code', "
    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace"
)


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    bg_inner: str
    header_bg: str
    border_outer: str
    divider: str
    text: str
    muted: str
    accent_primary: str
    accent_secondary: str
    accent_pink: str
    prompt_user: str
    prompt_host: str
    cursor: str
    chip_stroke: str
    dark_mode: bool


DARK_THEME = Theme(
    name="dark",
    bg="#0d1117",
    bg_inner="#111424",
    header_bg="#171b2e",
    border_outer="#2a2f4a",
    divider="#2d3352",
    text="#e6edf3",
    muted="#8b94b3",
    accent_primary="#b794f6",
    accent_secondary="#7dd3fc",
    accent_pink="#f472b6",
    prompt_user="#c4b5fd",
    prompt_host="#67e8f9",
    cursor="#a78bfa",
    chip_stroke="#2f3556",
    dark_mode=True,
)

LIGHT_THEME = Theme(
    name="light",
    bg="#ffffff",
    bg_inner="#faf9fe",
    header_bg="#f1effb",
    border_outer="#ddd6fe",
    divider="#dfd9f6",
    text="#1f2328",
    muted="#5f6682",
    accent_primary="#6d28d9",
    accent_secondary="#0284c7",
    accent_pink="#db2777",
    prompt_user="#6d28d9",
    prompt_host="#0369a1",
    cursor="#7c3aed",
    chip_stroke="#d8d4ee",
    dark_mode=False,
)


PROFILE_ROWS: list[tuple[str, str, str]] = [
    ("ORCID", "0009-0005-5248-0063", "secondary"),
    ("Role", "A&R Capital · Research Team (2022–now)", "primary"),
    ("Education", "M.S. CSIE, National Taiwan University", "primary"),
    ("ICPC 2019", "Asia Taipei-Hsinchu Regional · 5th Place", "pink"),
    ("ICPC 2019", "Asia Seoul Regional · 7th Place", "pink"),
    ("Vibe", "Antigravity CLI Lover ✦ (w/ Hagemi)", "secondary"),
    ("Formal Math", "P vs NP (Lean 4) · 3 Merged PRs", "primary"),
    ("Paper", "JMIR Formative Research '26 (DEPRESAR)", "primary"),
    ("Focus", "Quant Research · Systems · AI Agents", "secondary"),
    ("Stack", "C++ · Python · Lean 4 · Linux · tmux", "primary"),
]

PALETTE_SWATCHES = [
    "#2e2659",
    "#7c6cf6",
    "#a5b4fc",
    "#67e8f9",
    "#f9a8d4",
    "#ec4899",
    "#f59e0b",
    "#f8fafc",
]


def load_cropped_sprite(
    sprite_path: Path, crop_bottom_ratio: float = 1.0
) -> Image.Image:
    im = Image.open(sprite_path).convert("RGBA")
    bbox = im.getchannel("A").point(lambda a: 255 if a > 20 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    if 0.0 < crop_bottom_ratio < 1.0:
        w, h = im.size
        im = im.crop((0, 0, w, int(round(h * crop_bottom_ratio))))
    return im


def tune_color(r: int, g: int, b: int, dark_mode: bool) -> tuple[int, int, int]:
    """Tune pixel RGB for crisp, vibrant contrast against dark or light themes."""
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    if dark_mode:
        s = min(1.0, s * 1.35)
        # Lift dark hair/outline tones so Hagemi glows vibrantly on dark slate.
        l = 0.28 + 0.66 * (l ** 0.72)
        if s < 0.20 and l < 0.45:
            h = 0.72
            s = 0.38
    else:
        s = min(1.0, s * 1.38)
        # Keep highlights saturated enough to read clearly on light porcelain.
        l = 0.20 + 0.40 * (l ** 0.85)
        if s < 0.18:
            h = 0.72
            s = 0.30
    nr, ng, nb = colorsys.hls_to_rgb(h, l, s)
    return (
        max(0, min(255, int(round(nr * 255)))),
        max(0, min(255, int(round(ng * 255)))),
        max(0, min(255, int(round(nb * 255)))),
    )


def choose_ascii_char(
    r: int, g: int, b: int, dark_mode: bool, edge_strength: float = 0.0
) -> str:
    """Map pixel luminance + edge contrast to dense, expressive printable ASCII."""
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    if dark_mode:
        # Brighter highlights get dense glyphs (@#MW), outlines stay solid (&%*).
        intensity = 0.70 * lum + 0.30 * edge_strength
        idx = int(round((1.0 - max(0.0, min(1.0, intensity))) * (len(ASCII_RAMP) - 1)))
        idx = max(0, min(len(ASCII_RAMP) - 3, idx))
    else:
        # On light backgrounds, darker/outline features get heavy glyphs (@#MW).
        intensity = 0.75 * (1.0 - lum) + 0.25 * edge_strength
        idx = int(round((1.0 - max(0.0, min(1.0, intensity))) * (len(ASCII_RAMP) - 1)))
        idx = max(0, min(len(ASCII_RAMP) - 3, idx))
    return ASCII_RAMP[idx]


def sample_ascii_grid(
    im: Image.Image,
    cols: int,
    cell_aspect: float,
    dark_mode: bool,
) -> list[list[tuple[str, tuple[int, int, int]] | None]]:
    w, h = im.size
    rows = max(1, int(round(cols * (h / w) * cell_aspect)))
    resized = im.resize((cols, rows), Image.Resampling.LANCZOS)
    px = resized.load()
    # Compute simple Sobel-like luminance gradient for crisp eye/hair linework.
    lum_map = [
        [
            (0.299 * px[x, y][0] + 0.587 * px[x, y][1] + 0.114 * px[x, y][2]) / 255.0
            for x in range(cols)
        ]
        for y in range(rows)
    ]
    grid: list[list[tuple[str, tuple[int, int, int]] | None]] = []
    for y in range(rows):
        row_cells: list[tuple[str, tuple[int, int, int]] | None] = []
        for x in range(cols):
            r, g, b, a = px[x, y]
            if a < 64:
                row_cells.append(None)
            else:
                lx0 = lum_map[y][max(0, x - 1)]
                lx1 = lum_map[y][min(cols - 1, x + 1)]
                ly0 = lum_map[max(0, y - 1)][x]
                ly1 = lum_map[min(rows - 1, y + 1)][x]
                edge = min(1.0, abs(lx1 - lx0) + abs(ly1 - ly0))
                tr, tg, tb = tune_color(r, g, b, dark_mode=dark_mode)
                ch = choose_ascii_char(
                    r, g, b, dark_mode=dark_mode, edge_strength=edge
                )
                row_cells.append((ch, (tr, tg, tb)))
        grid.append(row_cells)
    return grid


def color_dist(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2
    )


def render_ascii_svg_lines(
    grid: list[list[tuple[str, tuple[int, int, int]] | None]],
    x_start: float,
    y_start: float,
    line_height: float,
    merge_threshold: float = 7.0,
) -> list[str]:
    """Run-length encode colored ASCII rows into compact SVG <text> lines."""
    lines_out: list[str] = []
    for row_idx, row in enumerate(grid):
        # Trim trailing transparent cells
        last_non_empty = -1
        for i, cell in enumerate(row):
            if cell is not None:
                last_non_empty = i
        if last_non_empty < 0:
            continue

        # Build runs of (color_or_none, text)
        runs: list[tuple[tuple[int, int, int] | None, str]] = []
        cur_color: tuple[int, int, int] | None = None
        cur_chars: list[str] = []
        cur_samples: list[tuple[int, int, int]] = []

        for cell in row[: last_non_empty + 1]:
            if cell is None:
                if cur_color is not None or not runs and not cur_chars:
                    if cur_chars:
                        avg = (
                            tuple(
                                round(sum(c[i] for c in cur_samples) / len(cur_samples))
                                for i in range(3)
                            )
                            if cur_samples
                            else None
                        )
                        runs.append((avg, "".join(cur_chars)))
                        cur_chars = []
                        cur_samples = []
                    cur_color = None
                cur_chars.append(" ")
            else:
                ch, rgb = cell
                if cur_color is None and cur_chars:
                    runs.append((None, "".join(cur_chars)))
                    cur_chars = []
                    cur_samples = []
                if cur_color is not None and color_dist(cur_color, rgb) <= merge_threshold:
                    cur_chars.append(ch)
                    cur_samples.append(rgb)
                else:
                    if cur_chars:
                        avg = tuple(
                            round(sum(c[i] for c in cur_samples) / len(cur_samples))
                            for i in range(3)
                        )
                        runs.append((avg, "".join(cur_chars)))
                    cur_color = rgb
                    cur_chars = [ch]
                    cur_samples = [rgb]

        if cur_chars:
            avg = (
                tuple(
                    round(sum(c[i] for c in cur_samples) / len(cur_samples))
                    for i in range(3)
                )
                if cur_samples
                else None
            )
            runs.append((avg, "".join(cur_chars)))

        tspans: list[str] = []
        for color, text in runs:
            escaped = escape(text)
            if color is None:
                tspans.append(escaped)
            else:
                hex_c = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
                tspans.append(f'<tspan fill="{hex_c}">{escaped}</tspan>')

        y_pos = y_start + row_idx * line_height
        lines_out.append(
            f'<text x="{x_start:.1f}" y="{y_pos:.1f}" xml:space="preserve">'
            f"{''.join(tspans)}</text>"
        )
    return lines_out


def build_svg(theme: Theme, sprite_path: Path) -> str:
    width = 960
    height = 520

    # Sample Hagemi bust/upper-body portrait into crisp 62-column ASCII art
    # (keeps cat ears, ahoge, Gemini star hairpin, heterochromatic eyes & :3 face large and sharp)
    im = load_cropped_sprite(sprite_path, crop_bottom_ratio=0.72)
    cols = 62
    font_size = 9.7
    line_height = 11.2
    char_width = 5.84
    cell_aspect = char_width / line_height  # ~0.521
    grid = sample_ascii_grid(im, cols=cols, cell_aspect=cell_aspect, dark_mode=theme.dark_mode)

    art_block_w = cols * char_width
    art_block_h = len(grid) * line_height
    left_box_x = 20.0
    left_box_w = 392.0
    art_x = left_box_x + (left_box_w - art_block_w) / 2.0
    art_y = 56.0 + ((height - 56.0 - 18.0) - art_block_h) / 2.0 + 9.0

    ascii_svg_lines = render_ascii_svg_lines(
        grid, x_start=art_x, y_start=art_y, line_height=line_height
    )

    # Right column geometry
    right_x = 442.0
    key_x = right_x
    val_x = 552.0
    title_y = 86.0
    subtitle_y = 108.0
    divider_y = 123.0
    rows_start_y = 152.0
    row_step = 25.0

    def accent_color(kind: str) -> str:
        if kind == "secondary":
            return theme.accent_secondary
        if kind == "pink":
            return theme.accent_pink
        return theme.accent_primary

    row_elements: list[str] = []
    for idx, (label, value, kind) in enumerate(PROFILE_ROWS):
        y = rows_start_y + idx * row_step
        c = accent_color(kind)
        row_elements.append(
            f'<text x="{key_x:.0f}" y="{y:.0f}" fill="{c}" font-weight="700">{escape(label)}</text>'
            f'<text x="{val_x:.0f}" y="{y:.0f}" fill="{theme.text}">{escape(value)}</text>'
        )

    # Color palette swatches
    palette_y = rows_start_y + len(PROFILE_ROWS) * row_step + 14.0
    swatch_elements: list[str] = []
    swatch_w = 28
    swatch_h = 14
    swatch_gap = 7
    for i, col in enumerate(PALETTE_SWATCHES):
        sx = right_x + i * (swatch_w + swatch_gap)
        swatch_elements.append(
            f'<rect x="{sx:.0f}" y="{palette_y:.0f}" width="{swatch_w}" height="{swatch_h}" '
            f'rx="4" fill="{col}" stroke="{theme.chip_stroke}" stroke-width="1" />'
        )

    prompt_y = palette_y + 42.0

    # Subtle decorative sparkles & ambient starlight
    sparkles = [
        (410, 74, 7, theme.accent_primary, 0.70),
        (922, 82, 8, theme.accent_secondary, 0.75),
        (904, 466, 6, theme.accent_pink, 0.70),
        (42, 476, 6, theme.accent_secondary, 0.55),
    ]
    sparkle_paths = []
    for cx, cy, r, col, op in sparkles:
        ir = r * 0.28
        d = (
            f"M {cx} {cy - r} Q {cx} {cy} {cx + r} {cy} "
            f"Q {cx} {cy} {cx} {cy + r} "
            f"Q {cx} {cy} {cx - r} {cy} "
            f"Q {cx} {cy} {cx} {cy - r} Z"
        )
        sparkle_paths.append(f'<path d="{d}" fill="{col}" opacity="{op}" />')
        _ = ir

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="Pu-Yu Liao — Gemini Hagemi Neofetch Profile ({theme.name})">
  <defs>
    <linearGradient id="geminiBorder-{theme.name}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#8b5cf6" stop-opacity="0.75" />
      <stop offset="50%" stop-color="#38bdf8" stop-opacity="0.65" />
      <stop offset="100%" stop-color="#f472b6" stop-opacity="0.75" />
    </linearGradient>
    <radialGradient id="hagemiGlow-{theme.name}" cx="23%" cy="54%" r="32%">
      <stop offset="0%" stop-color="#8b5cf6" stop-opacity="{'0.16' if theme.dark_mode else '0.10'}" />
      <stop offset="60%" stop-color="#38bdf8" stop-opacity="{'0.06' if theme.dark_mode else '0.04'}" />
      <stop offset="100%" stop-color="#8b5cf6" stop-opacity="0" />
    </radialGradient>
    <clipPath id="cardClip-{theme.name}">
      <rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="16" />
    </clipPath>
    <style>
      .mono {{ font-family: {MONO_FONT}; }}
      .ascii {{ font-family: {MONO_FONT}; font-size: {font_size}px; letter-spacing: 0px; }}
      .info {{ font-family: {MONO_FONT}; font-size: 13px; }}
      .cursor {{ animation: blink 1.15s steps(2, start) infinite; }}
      @keyframes blink {{ to {{ visibility: hidden; }} }}
    </style>
  </defs>

  <g clip-path="url(#cardClip-{theme.name})">
    <!-- Card background -->
    <rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="16" fill="{theme.bg_inner}" />
    <rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="16" fill="url(#hagemiGlow-{theme.name})" />

    <!-- Terminal title bar -->
    <rect x="2" y="2" width="{width - 4}" height="40" fill="{theme.header_bg}" />
    <line x1="2" y1="42" x2="{width - 2}" y2="42" stroke="{theme.divider}" stroke-width="1" />

    <!-- Window controls -->
    <circle cx="26" cy="22" r="6" fill="#ff5f56" />
    <circle cx="46" cy="22" r="6" fill="#ffbd2e" />
    <circle cx="66" cy="22" r="6" fill="#27c93f" />
    <text x="480" y="26" text-anchor="middle" class="mono" font-size="12.5" fill="{theme.muted}">puyuliao@antigravity: ~ — hagemi-fetch</text>

    <!-- Ambient Gemini sparkles -->
    {"".join(sparkle_paths)}

    <!-- Left column: True-color Hagemi ASCII art -->
    <g class="ascii">
      {"".join(ascii_svg_lines)}
    </g>

    <!-- Subtle vertical separator -->
    <line x1="422" y1="62" x2="422" y2="492" stroke="{theme.divider}" stroke-width="1" stroke-dasharray="3 5" opacity="0.7" />

    <!-- Right column: Profile header -->
    <text x="{right_x:.0f}" y="{title_y:.0f}" class="mono" font-size="18" font-weight="700">
      <tspan fill="{theme.prompt_user}">puyuliao</tspan><tspan fill="{theme.muted}">@</tspan><tspan fill="{theme.prompt_host}">antigravity</tspan>
    </text>
    <text x="{right_x:.0f}" y="{subtitle_y:.0f}" class="mono" font-size="12.5" fill="{theme.muted}">Pu-Yu Liao (廖普宇) · Quant &amp; Algorithms</text>
    <line x1="{right_x:.0f}" y1="{divider_y:.0f}" x2="928" y2="{divider_y:.0f}" stroke="{theme.divider}" stroke-width="1.2" />

    <!-- Right column: Key-value metadata -->
    <g class="info">
      {"".join(row_elements)}
    </g>

    <!-- Palette label & swatches -->
    <text x="{right_x:.0f}" y="{palette_y - 8:.0f}" class="mono" font-size="11" fill="{theme.muted}">hagemi palette</text>
    {"".join(swatch_elements)}

    <!-- Footer command status -->
    <text x="{right_x:.0f}" y="{prompt_y:.0f}" class="mono" font-size="12.5">
      <tspan fill="{theme.accent_secondary}">$</tspan>
      <tspan fill="{theme.muted}"> hagemi status </tspan>
      <tspan fill="{theme.accent_pink}">✦</tspan>
      <tspan fill="{theme.text}"> quant · algorithms · lean4 </tspan>
      <tspan fill="{theme.cursor}" class="cursor">▋</tspan>
    </text>
  </g>

  <!-- Gradient border frame -->
  <rect x="2" y="2" width="{width - 4}" height="{height - 4}" rx="16" fill="none" stroke="url(#geminiBorder-{theme.name})" stroke-width="1.6" />
</svg>
"""
    return svg


def build_plaintext_ascii(sprite_path: Path) -> str:
    """Generate a compact monochrome pure-ASCII neofetch block for README <details>."""
    im = load_cropped_sprite(sprite_path, crop_bottom_ratio=0.72)
    cols = 36
    cell_aspect = 0.50
    w, h = im.size
    rows = max(1, int(round(cols * (h / w) * cell_aspect)))
    resized = im.resize((cols, rows), Image.Resampling.LANCZOS)
    px = resized.load()

    ramp = " .:-=+*#%@"
    art_lines: list[str] = []
    for y in range(rows):
        chars: list[str] = []
        for x in range(cols):
            r, g, b, a = px[x, y]
            if a < 64:
                chars.append(" ")
            else:
                lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
                # Invert so dark hair/eyes use dense glyphs on light or dark code blocks.
                idx = int(round((1.0 - lum) * (len(ramp) - 1)))
                idx = max(1, min(len(ramp) - 1, idx))
                chars.append(ramp[idx])
        art_lines.append("".join(chars))

    info_lines = [
        "puyuliao@antigravity",
        "----------------------------------------",
        "Name        : Pu-Yu Liao",
        "ORCID       : 0009-0005-5248-0063",
        "Role        : A&R Capital · Research Team (2022-now)",
        "Education   : M.S. CSIE, National Taiwan University",
        "ICPC 2019   : Asia Taipei-Hsinchu · 5th Place",
        "ICPC 2019   : Asia Seoul · 7th Place",
        "Vibe        : Antigravity CLI Lover (w/ Hagemi)",
        "Formal Math : P vs NP (Lean 4) · 3 Merged PRs",
        "Paper       : JMIR Formative Research '26 (DEPRESAR)",
        "Stack       : C++ · Python · Lean 4 · Linux · tmux",
    ]

    total = max(len(art_lines), len(info_lines))
    merged: list[str] = []
    for i in range(total):
        left = art_lines[i] if i < len(art_lines) else " " * cols
        right = info_lines[i] if i < len(info_lines) else ""
        merged.append(f"{left}   {right}".rstrip())
    return "\n".join(merged)


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for theme in (DARK_THEME, LIGHT_THEME):
        svg_text = build_svg(theme, DEFAULT_SPRITE)
        out_path = ASSETS_DIR / f"profile-{theme.name}.svg"
        out_path.write_text(svg_text, encoding="utf-8")
        print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")

    plain_path = ASSETS_DIR / "profile-plain.txt"
    plain_text = build_plaintext_ascii(DEFAULT_SPRITE)
    plain_path.write_text(plain_text + "\n", encoding="utf-8")
    print(f"Wrote {plain_path} ({plain_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
