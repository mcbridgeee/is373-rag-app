"""Build the brain-bloom logo: a pink brain full of tangled strands that settle
into stems, then pop open into flowers and leaves.

    python scripts/make_logo.py

How it moves:
- Loopy strands draw themselves in, each wandering along one stem's route.
- From the bottom up, each tangled strand rewinds: it pulls back along its own
  path, undoing its loops, like thread being reeled in.
- Its stem then grows back out clean from the brain stem. Leaves open as the
  stem passes them, and the flower opens when the stem reaches it.

Writes two files from the same shapes:
- app/templates/partials/brain_bloom.svg  animated, inlined on the home page
- app/static/logo.svg                     the finished bloom, still (header, favicon)

The animation uses SVG's own <animate> tags (SMIL), not CSS, because the app's
Content-Security-Policy blocks inline styles. Every animation starts together
and uses keyTimes for its delay, so all of it shares one timeline.
"""

from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
FRAME = "0 0 400 440"
LINE = "#FFF4EA"
BRAIN = ("#EC7FA5", "#E46F98")  # left, right hemisphere
CORAL, PLUM, MARIGOLD, CREAM, SAGE, SAGE_DARK = (
    "#F0604E", "#5E2464", "#F4A23B", "#FFF4E4", "#8DB9A6", "#5F8F7B",
)

# Timeline, in seconds. Each stem rewinds, then regrows clean.
DURATION = 6.6
DRAW_IN = 1.4  # the tangle draws itself in
REWIND_FROM = 1.8  # the lowest stem starts pulling back
REWIND = 0.75  # one tangled line pulling back along itself
REGROW = 0.7  # the clean stem growing back out
OVERLAP = 0.4  # regrowth starts while the rewind is still reeling in
STAGGER = 0.3  # delay between stems, bottom to top
POP = 0.7  # how long a flower or leaf takes to open
EASE = "0.45 0 0.25 1"
PULL = "0.5 0 0.9 0.6"  # rewinding speeds up, like thread being pulled in
GROW = "0.2 0.6 0.4 1"  # regrowth starts fast and lands softly
STRANDS_PER_STEM = 2  # each stem's tangle is drawn as two lines
SIZE = 1.5  # flowers and leaves, relative to their drawn size

LEFT = (
    "M194,40 C150,30 98,46 72,90 C66,100 60,104 56,112 C42,140 36,170 38,204 "
    "C39,226 34,244 36,262 C40,296 46,318 60,338 C78,366 108,400 156,412 "
    "C174,417 188,414 194,404 Z"
)
RIGHT = (
    "M206,40 C254,32 304,52 330,96 C336,106 342,110 346,118 C360,146 366,176 "
    "362,210 C360,232 366,250 364,268 C360,300 352,322 338,342 C320,370 288,402 "
    "244,412 C226,416 212,413 206,404 Z"
)
STEM_ROOT = (200, 392)

# The finished stems, all starting at the brain stem.
STEMS = {
    "top": "C199,330 201,250 200,196 C199,160 202,132 201,118 C201,112 200,106 200,100",
    "upper-left": "C200,340 198,292 188,252 C176,206 140,198 126,168 C120,154 117,142 116,130",
    "upper-right": "C201,336 204,288 214,250 C226,206 266,198 280,168 C285,156 288,146 290,136",
    "lower-left": "C196,360 182,336 160,320 C136,302 110,306 100,294 C94,288 91,282 90,276",
    "lower-right": "C206,358 222,334 246,318 C272,300 298,300 306,284 C310,276 312,268 313,260",
    "sprig-right": "C210,384 222,378 234,374 C246,370 256,366 264,358 C268,354 272,348 276,342",
    "sprig-left": "C190,386 178,380 166,376 C154,372 144,366 136,360 C131,356 128,352 125,346",
}


def petals(count, rx, ry, distance, fill):
    step = 360 / count
    return "".join(
        f'<ellipse cx="0" cy="{-distance}" rx="{rx}" ry="{ry}" fill="{fill}" '
        f'transform="rotate({i * step:.1f})"/>'
        for i in range(count)
    )


LEAF = "M0,0 C6,-10 18,-12 26,-6 C18,2 8,4 0,0 Z"

# Leaves open as the regrowing stem passes them: (stem, x, y, rotation, shape,
# how far along the stem). Flowers open when the stem reaches them.
LEAVES = [
    ("upper-left", 190, 246, 200, f'<path d="{LEAF}" fill="{SAGE}"/>', 0.45),
    ("upper-right", 215, 244, -20, f'<path d="{LEAF}" fill="{SAGE_DARK}"/>', 0.45),
    ("top", 200, 170, 210, f'<path d="{LEAF}" fill="{SAGE_DARK}"/>', 0.75),
]
BLOOMS = [
    ("sprig-right", 276, 342, -40, f'<path d="{LEAF}" fill="{SAGE}"/>'),
    ("sprig-left", 125, 346, 220, f'<path d="{LEAF}" fill="{SAGE}"/>'),
    (
        "top", 200, 100, 0,
        f'<circle r="21" fill="{CORAL}"/>'
        f'<path d="M0,0 c4,-2 6,4 2,7 c-6,4 -12,-3 -9,-9 c4,-9 18,-8 20,2 '
        f'c2,12 -12,19 -22,12" fill="none" stroke="{CREAM}" stroke-width="2.2" '
        f'stroke-linecap="round"/>',
    ),
    ("upper-left", 116, 130, -10, petals(5, 9, 9, 10, CREAM) + f'<circle r="6" fill="{MARIGOLD}"/>'),
    (
        "upper-right", 290, 136, 8,
        f'<path d="M-13,-20 C-14,-8 -6,0 0,0 C6,0 14,-8 13,-20 L7,-32 L0,-22 '
        f'L-7,-32 Z" fill="{PLUM}"/>'
        f'<path d="M-6,-22 C-6,-12 -3,-6 0,-4" fill="none" stroke="#8E4A8F" '
        f'stroke-width="2" stroke-linecap="round"/>',
    ),
    ("lower-left", 90, 276, 0, petals(12, 3.2, 10, 12, MARIGOLD) + '<circle r="7" fill="#B4471F"/>'),
    ("lower-right", 313, 260, 15, petals(6, 6, 11, 11, CORAL) + f'<circle r="5" fill="{CREAM}"/>'),
]


def point(x, y):
    return f"{x:.1f},{y:.1f}"


def inside(x, y):
    """Pull a point back inside the brain so strand ends never leave it."""
    cx, cy, rx, ry = 200, 226, 132, 160
    dx, dy = (x - cx) / rx, (y - cy) / ry
    distance = (dx * dx + dy * dy) ** 0.5
    if distance <= 1:
        return x, y
    return cx + dx / distance * rx, cy + dy / distance * ry


def ends(stem):
    """The end point of each of a stem's three curves."""
    values = [float(v) for v in stem.replace("C", " ").replace(",", " ").split()]
    return [(values[i], values[i + 1]) for i in (4, 10, 16)]


def strand(stem, rng, wander, start=STEM_ROOT):
    """A smooth, loopy strand that roughly follows the stem's route.

    Each curve leaves in the direction the previous one arrived (no corners),
    swings wide, crosses itself (the loop) and lands near the stem's matching
    point. Extra strands start partway up so the bottom doesn't pile up.
    """
    from math import atan2, cos, sin

    x, y = start
    heading = -1.5708 + rng.uniform(-0.8, 0.8)  # roughly upward
    parts = []
    for ex, ey in ends(stem):
        nx, ny = inside(ex + rng.uniform(-wander, wander), ey + rng.uniform(-wander, wander))
        toward = atan2(ny - y, nx - x)
        side = rng.choice((-1, 1))
        turn = toward + side * rng.uniform(1.3, 2.4)
        reach_in, reach_out = rng.uniform(55, 105), rng.uniform(55, 100)
        p1 = (x + reach_in * cos(heading), y + reach_in * sin(heading))
        p2 = (nx - reach_out * cos(turn), ny - reach_out * sin(turn))
        parts.append(f"C{point(*p1)} {point(*p2)} {point(nx, ny)}")
        x, y, heading = nx, ny, turn
    return f"M{point(*start)} " + " ".join(parts)


def keyed(attribute, values, times, eases):
    """One <animate> on the shared timeline. times are in seconds."""
    return (
        f'<animate attributeName="{attribute}" values="{";".join(values)}" '
        f'keyTimes="{";".join(f"{t / DURATION:.4f}" for t in times)}" '
        f'calcMode="spline" keySplines="{";".join(eases)}" '
        f'dur="{DURATION}s" begin="0s" fill="freeze"/>'
    )


def hidden_after(moment):
    """Switch a line off once it has fully rewound (its round end leaves a dot)."""
    return f'<set attributeName="opacity" to="0" begin="{moment:.2f}s" fill="freeze"/>'


def shown_after(moment):
    """Keep a line hidden until it starts growing, for the same reason."""
    return (
        f'<set attributeName="opacity" to="0" begin="0s" fill="freeze"/>'
        f'<set attributeName="opacity" to="1" begin="{moment:.2f}s" fill="freeze"/>'
    )


def pop(start):
    """Open from nothing with a small overshoot. start is in seconds."""
    end = min(start + POP, DURATION - 0.01)
    peak = start + (end - start) * 0.65
    times = ";".join(f"{t / DURATION:.4f}" for t in (0, start, peak, end, DURATION))
    return (
        f'<animateTransform attributeName="transform" type="scale" '
        f'values="0;0;1.15;1;1" keyTimes="{times}" calcMode="spline" '
        f'keySplines="{";".join([EASE] * 4)}" dur="{DURATION}s" begin="0s" fill="freeze"/>'
    )


def build(animated: bool) -> str:
    # Lower stems settle first, so the plant seems to grow upward.
    order = sorted(STEMS, key=lambda name: -ends(STEMS[name])[-1][1])
    begins = {name: REWIND_FROM + STAGGER * rank for rank, name in enumerate(order)}

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{FRAME}" '
        f'role="img" aria-label="A brain whose tangled lines grow into flowers">',
        "<defs>",
        '<filter id="bb-wash" x="-5%" y="-5%" width="110%" height="110%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="7"/>'
        '<feDisplacementMap in="SourceGraphic" scale="5"/></filter>',
        '<radialGradient id="bb-light"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.32"/>'
        '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>',
        '<radialGradient id="bb-shade"><stop offset="0" stop-color="#7A1F48" stop-opacity="0.22"/>'
        '<stop offset="1" stop-color="#7A1F48" stop-opacity="0"/></radialGradient>',
        f'<clipPath id="bb-brain"><path d="{LEFT}"/><path d="{RIGHT}"/></clipPath>',
        "</defs>",
        '<g filter="url(#bb-wash)">',
        *(
            f'<path d="{shape}" fill="{color}" stroke="{LINE}" stroke-width="3"/>'
            for shape, color in zip((LEFT, RIGHT), BRAIN)
        ),
        '<g clip-path="url(#bb-brain)">',
        '<circle cx="120" cy="150" r="90" fill="url(#bb-light)"/>',
        '<circle cx="290" cy="300" r="100" fill="url(#bb-light)"/>',
        '<circle cx="280" cy="140" r="80" fill="url(#bb-shade)"/>',
        '<circle cx="110" cy="320" r="80" fill="url(#bb-shade)"/>',
        "</g></g>",
        f'<g fill="none" stroke="{LINE}" stroke-width="3" stroke-linecap="round" '
        f'stroke-linejoin="round" clip-path="url(#bb-brain)">',
    ]
    reached = {}
    for index, (name, stem) in enumerate(STEMS.items()):
        clean = f"M{point(*STEM_ROOT)} {stem}"
        if not animated:
            out.append(f'<path d="{clean}"/>')
            continue
        rewind = begins[name]
        regrow = rewind + REWIND - OVERLAP
        reached[name] = (regrow, regrow + REGROW)
        # The tangle: draws in, waits, then pulls back along itself.
        for copy in range(STRANDS_PER_STEM):
            rng = random.Random(index * 31 + copy * 7 + 5)
            first = ends(stem)[0]
            begin_at = STEM_ROOT if copy == 0 else inside(
                first[0] + rng.uniform(-40, 40), first[1] + rng.uniform(-50, 10)
            )
            messy = strand(stem, rng, wander=24 + 20 * copy, start=begin_at)
            pull = rewind + 0.08 * copy
            out.append(
                f'<path d="{messy}" pathLength="1" stroke-dasharray="1">'
                + keyed(
                    "stroke-dashoffset", ["1", "0", "0", "1", "1"],
                    [0, DRAW_IN, pull, pull + REWIND, DURATION], [EASE, EASE, PULL, EASE],
                )
                + hidden_after(pull + REWIND - 0.02)
                + "</path>"
            )
        # The clean stem grows back out from the brain stem.
        out.append(
            f'<path d="{clean}" pathLength="1" stroke-dasharray="1">'
            + keyed(
                "stroke-dashoffset", ["1", "1", "0", "0"],
                [0, regrow, regrow + REGROW, DURATION], [EASE, GROW, EASE],
            )
            + shown_after(regrow + 0.02)
            + "</path>"
        )
    out.append("</g>")

    for name, x, y, turn, shape, along in LEAVES:
        grow = ""
        if animated:
            start, end = reached[name]
            grow = pop(start + (end - start) * along)
        out.append(
            f'<g transform="translate({x},{y}) rotate({turn}) scale({SIZE})">'
            f"<g>{shape}{grow}</g></g>"
        )
    for name, x, y, turn, shape in BLOOMS:
        grow = pop(reached[name][1] - 0.12) if animated else ""
        out.append(
            f'<g transform="translate({x},{y}) rotate({turn}) scale({SIZE})">'
            f"<g>{shape}{grow}</g></g>"
        )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    partials = ROOT / "app" / "templates" / "partials"
    partials.mkdir(exist_ok=True)
    (partials / "brain_bloom.svg").write_text(build(animated=True), encoding="utf-8")
    (ROOT / "app" / "static" / "logo.svg").write_text(build(animated=False), encoding="utf-8")
    print("wrote partials/brain_bloom.svg and static/logo.svg")


if __name__ == "__main__":
    main()
