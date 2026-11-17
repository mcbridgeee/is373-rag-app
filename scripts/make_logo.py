"""Build the brain-bloom logo: a pink brain whose tangled lines reorganize into
stems and flowers.

    python scripts/make_logo.py

Every loop in the tangle is a petal or leaf in disguise. A petal here is one
cubic curve that leaves the flower's center and returns to it, which is also
how a loop in a scribble is drawn, so each messy loop can shrink and travel
into place as a petal. Color then washes into the petals.

Writes two files from the same shapes:
- app/templates/partials/brain_bloom.svg  animated, inlined on the home page
- app/static/logo.svg                     the finished bloom, still (header, favicon)

The animation uses SVG's own <animate> tags (SMIL), not CSS, because the app's
Content-Security-Policy blocks inline styles. Every animation starts together
and uses keyTimes for its delay, so all of it shares one timeline.
"""

from math import cos, pi, sin
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
DURATION = 5.6  # seconds for the whole story
FRAME = "0 0 400 440"
EASE = "0.45 0 0.25 1"
LINE = "#FFF4EA"
BRAIN = ("#EC7FA5", "#E46F98")  # left, right hemisphere

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

# Each bloom: the stem's three curves (ending at the flower's center), then
# its petals. Angles are in degrees, 0 = pointing right, -90 = pointing up.
BLOOMS = [
    {  # coral, top center
        "stem": ["C199,330 201,250 200,196", "C199,160 202,128 201,112", "C201,106 200,100 200,96"],
        "center": (200, 96), "petals": [-90 + 60 * i for i in range(6)],
        "length": 34, "spread": 0.55, "fill": "#F0604E", "dot": "#FFF4E4", "start": 0.70,
    },
    {  # cream five-petal, upper left
        "stem": ["C200,340 198,292 188,252", "C176,206 140,198 126,168", "C120,154 117,140 116,128"],
        "center": (116, 128), "petals": [-90 + 72 * i for i in range(5)],
        "length": 30, "spread": 0.65, "fill": "#FFF4E4", "dot": "#F4A23B", "start": 0.73,
    },
    {  # plum tulip, upper right
        "stem": ["C201,336 204,288 214,250", "C226,206 266,198 280,168", "C285,156 288,144 290,132"],
        "center": (290, 132), "petals": [-122, -90, -58],
        "length": 38, "spread": 0.42, "fill": "#5E2464", "dot": None, "start": 0.75,
    },
    {  # marigold, lower left
        "stem": ["C196,360 182,336 160,320", "C136,302 110,306 100,292", "C95,286 92,280 90,274"],
        "center": (90, 274), "petals": [-90 + 36 * i for i in range(10)],
        "length": 28, "spread": 0.3, "fill": "#F4A23B", "dot": "#B4471F", "start": 0.78,
    },
    {  # butter-yellow star, lower right
        "stem": ["C206,358 222,334 246,318", "C272,300 298,300 306,284", "C310,276 312,266 313,258"],
        "center": (313, 258), "petals": [-75 + 60 * i for i in range(6)],
        "length": 31, "spread": 0.36, "fill": "#FFD27A", "dot": "#F0604E", "start": 0.81,
    },
    {  # leafy sprig, right
        "stem": ["C210,384 222,378 234,374", "C246,370 256,366 264,358", "C268,354 272,348 276,342"],
        "center": (276, 342), "petals": [-42], "length": 32, "spread": 0.55,
        "fill": "#8DB9A6", "dot": None, "start": 0.68,
    },
    {  # leafy sprig, left
        "stem": ["C190,386 178,380 166,376", "C154,372 144,366 136,360", "C131,356 128,352 125,346"],
        "center": (125, 346), "petals": [-140], "length": 32, "spread": 0.55,
        "fill": "#5F8F7B", "dot": None, "start": 0.69,
    },
]

# Leaves along the stems: (where it sprouts, angle, color, start of color wash).
LEAVES = [
    ((190, 250), 200, "#8DB9A6", 0.70),
    ((213, 246), -25, "#5F8F7B", 0.71),
    ((200, 178), 205, "#5F8F7B", 0.72),
    ((200, 222), -20, "#8DB9A6", 0.74),
]
LEAF_LENGTH, LEAF_SPREAD = 28, 0.5

# Timeline (fractions of DURATION): draw the tangle, hold, then untangle.
DRAWN, UNTANGLE_FROM, UNTANGLE_TO = 0.30, 0.36, 0.70
WASH = 0.13  # how long each bloom's color takes to come in


def point(x, y):
    return f"{x:.1f},{y:.1f}"


def loop_curve(center, angle, length, spread):
    """One petal: a cubic that leaves the center and comes back to it."""
    cx, cy = center
    reach = length / (0.75 * cos(spread))
    theta = angle * pi / 180
    p1 = (cx + reach * cos(theta - spread), cy + reach * sin(theta - spread))
    p2 = (cx + reach * cos(theta + spread), cy + reach * sin(theta + spread))
    return f"C{point(*p1)} {point(*p2)} {point(cx, cy)}"


def inside(x, y):
    """Pull a point back inside the brain so the tangle never spills out."""
    cx, cy, rx, ry = 200, 226, 132, 160
    dx, dy = (x - cx) / rx, (y - cy) / ry
    distance = (dx * dx + dy * dy) ** 0.5
    if distance <= 1:
        return x, y
    return cx + dx / distance * rx, cy + dy / distance * ry


def scribble(start, curves, seed, drift=(0, -1)):
    """A smooth, loopy line with the same number of curves as the clean path.

    Each curve leaves in the direction the previous one arrived (so there are
    no corners), swings wide and crosses itself (the loop), then exits at a
    new angle. The ends are kept inside the brain; the lines are clipped to it.
    """
    rng = random.Random(seed)
    x, y = start
    heading = -pi / 2 + rng.uniform(-0.7, 0.7)
    parts = []
    for index in range(curves):
        side = rng.choice((-1, 1))
        pull = 1.0 if index < 2 else 0.1
        step = rng.uniform(34, 82)
        aim = heading - side * rng.uniform(0.5, 1.1)
        nx = x + step * cos(aim) + drift[0] * 26 * pull
        ny = y + step * sin(aim) + drift[1] * 26 * pull
        nx, ny = inside(nx, ny)
        turn = heading + side * rng.uniform(1.6, 2.7)
        reach_in, reach_out = rng.uniform(70, 120), rng.uniform(60, 110)
        p1 = (x + reach_in * cos(heading), y + reach_in * sin(heading))
        p2 = (nx - reach_out * cos(turn), ny - reach_out * sin(turn))
        parts.append(f"C{point(*p1)} {point(*p2)} {point(nx, ny)}")
        x, y, heading = nx, ny, turn
    return " ".join(parts)


def animate(attribute, values, times, spline=True):
    curve = ""
    if spline:
        curve = f' calcMode="spline" keySplines="{";".join([EASE] * (len(values) - 1))}"'
    return (
        f'<animate attributeName="{attribute}" values="{";".join(values)}" '
        f'keyTimes="{";".join(f"{t:g}" for t in times)}"{curve} '
        f'dur="{DURATION}s" begin="0s" fill="freeze"/>'
    )


def wash(start):
    """Color comes in after the lines settle: fade plus a small swell."""
    end = min(start + WASH, 1)
    peak = start + (end - start) * 0.7
    fade = animate("opacity", ["0", "0", "1", "1"], [0, start, end, 1])
    swell = (
        f'<animateTransform attributeName="transform" type="scale" '
        f'values="0.55;0.55;1.08;1;1" keyTimes="0;{start:g};{peak:.3f};{end:.3f};1" '
        f'calcMode="spline" keySplines="{";".join([EASE] * 4)}" '
        f'dur="{DURATION}s" begin="0s" fill="freeze"/>'
    )
    return fade, swell


def build(animated: bool) -> str:
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
    ]

    # Color layer, under the lines: each flower's petals filled in.
    for bloom in BLOOMS:
        petals = "".join(
            loop_curve((0, 0), angle, bloom["length"], bloom["spread"])
            for angle in bloom["petals"]
        )
        fade, swell = wash(bloom["start"]) if animated else ("", "")
        cx, cy = bloom["center"]
        out.append(
            f'<g transform="translate({point(cx, cy)})"><g>'
            f'<path d="M0,0 {petals}" fill="{bloom["fill"]}">{fade}</path>{swell}</g></g>'
        )
    leaf_lines = []
    for index, (base, angle, color, start) in enumerate(LEAVES):
        fade, swell = wash(start) if animated else ("", "")
        shape = loop_curve((0, 0), angle, LEAF_LENGTH, LEAF_SPREAD)
        out.append(
            f'<g transform="translate({point(*base)})"><g>'
            f'<path d="M0,0 {shape}" fill="{color}">{fade}</path>{swell}</g></g>'
        )
        clean = f"M{point(*base)} {loop_curve(base, angle, LEAF_LENGTH, LEAF_SPREAD)}"
        messy = f"M{point(*base)} {scribble(base, 1, seed=100 + index, drift=(0, 0))}"
        leaf_lines.append((messy, clean))

    # Line layer: the tangle that becomes stems, petals and leaves.
    out.append(
        f'<g fill="none" stroke="{LINE}" stroke-width="2.4" stroke-linecap="round" '
        f'stroke-linejoin="round" clip-path="url(#bb-brain)">'
    )
    lines = []
    for index, bloom in enumerate(BLOOMS):
        petals = " ".join(
            loop_curve(bloom["center"], angle, bloom["length"], bloom["spread"])
            for angle in bloom["petals"]
        )
        clean = f"M{point(*STEM_ROOT)} {' '.join(bloom['stem'])} {petals}"
        curves = 3 + len(bloom["petals"])
        messy = f"M{point(*STEM_ROOT)} {scribble(STEM_ROOT, curves, seed=index * 7 + 3)}"
        lines.append((messy, clean))
    for messy, clean in lines + leaf_lines:
        motion = ""
        if animated:
            motion = animate(
                "stroke-dashoffset", ["1", "0", "0"], [0, DRAWN, 1]
            ) + animate(
                "d", [messy, messy, clean, clean], [0, UNTANGLE_FROM, UNTANGLE_TO, 1]
            )
        out.append(f'<path d="{clean}" pathLength="1" stroke-dasharray="1">{motion}</path>')
    out.append("</g>")

    # Flower centers sit on top, hiding where the petal lines meet.
    for bloom in BLOOMS:
        if bloom["dot"]:
            fade, _ = wash(bloom["start"] + 0.04) if animated else ("", "")
            out.append(
                f'<circle cx="{bloom["center"][0]}" cy="{bloom["center"][1]}" r="6" '
                f'fill="{bloom["dot"]}">{fade}</circle>'
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
