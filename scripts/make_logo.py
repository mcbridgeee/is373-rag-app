"""Build the brain-bloom logo: a tangle of lines inside a brain that straightens
into stems and blooms into flowers.

    python scripts/make_logo.py

Writes two files from the same shapes:
- app/templates/partials/brain_bloom.svg  animated, inlined on the home page
- app/static/logo.svg                     the finished bloom, still (header, favicon)

The animation uses SVG's own <animate> tags (SMIL), not CSS, because the app's
Content-Security-Policy blocks inline styles. Every animation starts together
and uses keyTimes for its delay, so all of it shares one timeline.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DURATION = 5.2  # seconds for the whole story
FRAME = "0 0 400 440"

# Palette: purple while tangled, pink once it organizes.
PURPLE = ("#5A2A82", "#4A2270")  # left, right hemisphere
PINK = ("#EC7FA5", "#E46F98")
LINE = "#FFF4EA"
CORAL, PLUM, MARIGOLD, CREAM, SAGE, SAGE_DARK = (
    "#F0604E",
    "#5E2464",
    "#F4A23B",
    "#FFF4E4",
    "#8DB9A6",
    "#5F8F7B",
)

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

# Each stem: (messy path, clean path). Same commands in the same order, so one
# can morph into the other. All start at the brain stem, (200, 392).
STEMS = [
    (  # to the coral bloom, top center
        "M200,392 C130,320 290,300 200,250 C110,200 300,180 210,150 C120,120 280,90 190,110",
        "M200,392 C199,330 201,250 200,196 C199,160 202,132 201,118 C201,112 200,106 200,100",
    ),
    (  # to the cream five-petal, upper left
        "M200,392 C120,380 260,300 170,330 C90,360 150,200 230,250 C300,290 60,220 140,180",
        "M200,392 C200,340 198,292 188,252 C176,206 140,198 126,168 C120,154 117,142 116,130",
    ),
    (  # to the plum tulip, upper right
        "M200,392 C290,370 140,300 240,320 C320,340 260,200 180,260 C110,300 330,230 270,190",
        "M200,392 C201,336 204,288 214,250 C226,206 266,198 280,168 C285,156 288,146 290,136",
    ),
    (  # to the marigold, lower left
        "M200,392 C80,400 140,280 200,330 C250,370 60,340 90,300 C120,260 40,250 110,250",
        "M200,392 C196,360 182,336 160,320 C136,302 110,306 100,294 C94,288 91,282 90,276",
    ),
    (  # to the coral bloom, lower right
        "M200,392 C320,410 290,290 230,340 C170,380 360,330 320,280 C280,240 380,250 300,230",
        "M200,392 C206,358 222,334 246,318 C272,300 298,300 306,284 C310,276 312,268 313,260",
    ),
    (  # leafy sprig, right
        "M200,392 C260,420 300,330 240,350 C180,370 300,400 290,360 C280,320 230,330 260,310",
        "M200,392 C210,384 222,378 234,374 C246,370 256,366 264,358 C268,354 272,348 276,342",
    ),
    (  # leafy sprig, left
        "M200,392 C150,420 100,340 160,350 C220,360 110,400 120,360 C130,320 180,330 140,320",
        "M200,392 C190,386 178,380 166,376 C154,372 144,366 136,360 C131,356 128,352 125,346",
    ),
]

# Extra scribbles that only exist in the tangle; they fade out.
TANGLES = [
    "M90,180 C60,140 150,120 130,170 C110,220 60,200 80,250 C100,300 170,260 150,230 C130,200 110,300 160,320",
    "M300,170 C340,130 250,110 270,170 C290,230 340,200 320,250 C300,300 240,270 260,230 C280,190 300,300 240,330",
    "M170,120 C150,90 240,80 220,120 C200,160 170,140 190,180 C210,220 140,210 160,250",
    "M250,120 C230,80 300,90 280,130 C260,170 230,150 250,190",
]


def petals(count, rx, ry, distance, fill):
    step = 360 / count
    return "".join(
        f'<ellipse cx="0" cy="{-distance}" rx="{rx}" ry="{ry}" fill="{fill}" '
        f'transform="rotate({i * step:.1f})"/>'
        for i in range(count)
    )


LEAF = 'M0,0 C6,-10 18,-12 26,-6 C18,2 8,4 0,0 Z'

# (x, y, rotation, start of bloom as a fraction of the timeline, shape)
BLOOMS = [
    # leaves first
    (190, 246, 200, 0.60, f'<path d="{LEAF}" fill="{SAGE}"/>'),
    (215, 244, -20, 0.62, f'<path d="{LEAF}" fill="{SAGE_DARK}"/>'),
    (200, 170, 210, 0.63, f'<path d="{LEAF}" fill="{SAGE_DARK}"/>'),
    (276, 342, -40, 0.64, f'<path d="{LEAF}" fill="{SAGE}"/>'),
    (125, 346, 220, 0.65, f'<path d="{LEAF}" fill="{SAGE}"/>'),
    # flowers
    (
        200, 100, 0, 0.66,
        f'<circle r="21" fill="{CORAL}"/>'
        f'<path d="M0,0 c4,-2 6,4 2,7 c-6,4 -12,-3 -9,-9 c4,-9 18,-8 20,2 '
        f'c2,12 -12,19 -22,12" fill="none" stroke="{CREAM}" stroke-width="2.2" '
        f'stroke-linecap="round"/>',
    ),
    (
        116, 130, -10, 0.70,
        petals(5, 9, 9, 10, CREAM) + f'<circle r="6" fill="{MARIGOLD}"/>',
    ),
    (
        290, 136, 8, 0.72,
        f'<path d="M-13,-20 C-14,-8 -6,0 0,0 C6,0 14,-8 13,-20 L7,-32 L0,-22 '
        f'L-7,-32 Z" fill="{PLUM}"/>'
        f'<path d="M-6,-22 C-6,-12 -3,-6 0,-4" fill="none" stroke="#8E4A8F" '
        f'stroke-width="2" stroke-linecap="round"/>',
    ),
    (
        90, 276, 0, 0.76,
        petals(12, 3.2, 10, 12, MARIGOLD) + '<circle r="7" fill="#B4471F"/>',
    ),
    (
        313, 260, 15, 0.80,
        petals(6, 6, 11, 11, CORAL) + f'<circle r="5" fill="{CREAM}"/>',
    ),
]


def keyed(attribute, values, times, spline=None, extra=""):
    """One <animate> on the shared timeline, frozen at its last value."""
    curve = ""
    if spline:
        curve = f' calcMode="spline" keySplines="{";".join([spline] * (len(values) - 1))}"'
    return (
        f'<animate attributeName="{attribute}" values="{";".join(values)}" '
        f'keyTimes="{";".join(f"{t:g}" for t in times)}"{curve} '
        f'dur="{DURATION}s" begin="0s" fill="freeze"{extra}/>'
    )


EASE = "0.45 0 0.25 1"
SIZE = 1.5  # flowers and leaves, relative to their drawn size


def build(animated: bool) -> str:
    anim = (lambda *a, **k: keyed(*a, **k)) if animated else (lambda *a, **k: "")
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{FRAME}" '
        f'role="img" aria-label="A brain whose tangled lines grow into flowers">',
        "<defs>",
        '<filter id="bb-wash" x="-5%" y="-5%" width="110%" height="110%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.035" numOctaves="2" seed="7"/>'
        '<feDisplacementMap in="SourceGraphic" scale="5"/></filter>',
        '<radialGradient id="bb-light"><stop offset="0" stop-color="#FFFFFF" stop-opacity="0.32"/>'
        '<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>',
        '<radialGradient id="bb-shade"><stop offset="0" stop-color="#2A0F33" stop-opacity="0.26"/>'
        '<stop offset="1" stop-color="#2A0F33" stop-opacity="0"/></radialGradient>',
        f'<clipPath id="bb-brain"><path d="{LEFT}"/><path d="{RIGHT}"/></clipPath>',
        "</defs>",
        '<g filter="url(#bb-wash)">',
    ]
    for shape, (start, end) in zip((LEFT, RIGHT), zip(PURPLE, PINK)):
        out.append(
            f'<path d="{shape}" fill="{end}" stroke="{LINE}" stroke-width="3">'
            + anim("fill", [start, start, end, end], [0, 0.36, 0.7, 1], EASE)
            + "</path>"
        )
    out += [
        '<g clip-path="url(#bb-brain)">',
        '<circle cx="120" cy="150" r="90" fill="url(#bb-light)"/>',
        '<circle cx="290" cy="300" r="100" fill="url(#bb-light)"/>',
        '<circle cx="280" cy="140" r="80" fill="url(#bb-shade)"/>',
        '<circle cx="110" cy="320" r="80" fill="url(#bb-shade)"/>',
        "</g></g>",
        f'<g fill="none" stroke="{LINE}" stroke-width="3" stroke-linecap="round" '
        f'stroke-linejoin="round">',
    ]
    if animated:
        for path in TANGLES:
            out.append(
                f'<path d="{path}" pathLength="1" stroke-dasharray="1" opacity="0">'
                + keyed("stroke-dashoffset", ["1", "0", "0"], [0, 0.3, 1], EASE)
                + keyed("opacity", ["1", "1", "0", "0"], [0, 0.36, 0.58, 1])
                + "</path>"
            )
    for messy, clean in STEMS:
        out.append(
            f'<path d="{clean}" pathLength="1" stroke-dasharray="1">'
            + anim("stroke-dashoffset", ["1", "0", "0"], [0, 0.3, 1], EASE)
            + anim("d", [messy, messy, clean, clean], [0, 0.36, 0.68, 1], EASE)
            + "</path>"
        )
    out.append("</g>")
    for x, y, turn, start, shape in BLOOMS:
        grow = ""
        if animated:
            peak, end = min(start + 0.1, 0.97), min(start + 0.16, 1)
            grow = (
                f'<animateTransform attributeName="transform" type="scale" '
                f'values="0;0;1.15;1;1" keyTimes="0;{start:g};{peak:g};{end:g};1" '
                f'calcMode="spline" keySplines="{";".join([EASE] * 4)}" '
                f'dur="{DURATION}s" begin="0s" fill="freeze"/>'
            )
        out.append(
            f'<g transform="translate({x},{y}) rotate({turn}) scale({SIZE})"><g>{shape}{grow}</g></g>'
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
