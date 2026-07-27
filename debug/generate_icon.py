"""
OrionLead AI - App Icon Generator
Design: Dark navy background, glowing indigo ring, Orion constellation in cyan/white,
        central bright star node, lightning bolt accent.
"""
from PIL import Image, ImageDraw, ImageFilter
import math

SIZE = 1024
C = SIZE // 2  # center

# Brand colors
BG       = (15,  23,  42)    # #0f172a  deep navy
PURPLE   = (30,  27,  75)    # #1e1b4b  deep purple (gradient center)
INDIGO   = (99,  102, 241)   # #6366f1  primary
CYAN     = (34,  211, 238)   # #22d3ee  accent
WHITE    = (255, 255, 255)
AMBER    = (251, 191, 36)    # #fbbf24  warm star highlight


def new_layer():
    return Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))


def composite(base, layer):
    return Image.alpha_composite(base, layer)


def draw_glow(img, cx, cy, radius, color, intensity=180, blur=30):
    layer = new_layer()
    d = ImageDraw.Draw(layer)
    d.ellipse([cx-radius, cy-radius, cx+radius, cy+radius],
              fill=(*color, intensity))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    return composite(img, layer)


def draw_star(img, cx, cy, size, color=WHITE, glow_color=None, glow_r=None):
    if glow_color:
        img = draw_glow(img, cx, cy, glow_r or size*3, glow_color,
                        intensity=160, blur=size*1.5)
    layer = new_layer()
    d = ImageDraw.Draw(layer)
    d.ellipse([cx-size, cy-size, cx+size, cy+size], fill=(*color, 255))
    # Bright white core
    core = max(2, size//3)
    d.ellipse([cx-core, cy-core, cx+core, cy+core], fill=(*WHITE, 255))
    return composite(img, layer)


# ── 1. Background ─────────────────────────────────────────────────────────────
img = new_layer()
bg = new_layer()
bg_draw = ImageDraw.Draw(bg)
bg_draw.rounded_rectangle([0, 0, SIZE, SIZE], radius=210, fill=(*BG, 255))
img = composite(img, bg)

# Radial purple glow from center (brand depth)
for r in range(380, 0, -6):
    alpha = int(55 * (1 - r / 380))
    g = new_layer()
    ImageDraw.Draw(g).ellipse([C-r, C-r, C+r, C+r], fill=(*PURPLE, alpha))
    img = composite(img, g)

# ── 2. Outer ring glow ────────────────────────────────────────────────────────
RING_R = 375
# Soft outer aura
for width, alpha in [(80, 25), (50, 40), (25, 60)]:
    aura = new_layer()
    ImageDraw.Draw(aura).ellipse(
        [C-RING_R-width//2, C-RING_R-width//2,
         C+RING_R+width//2, C+RING_R+width//2],
        outline=(*INDIGO, alpha), width=width)
    aura = aura.filter(ImageFilter.GaussianBlur(radius=18))
    img = composite(img, aura)

# Solid ring
ring = new_layer()
ImageDraw.Draw(ring).ellipse(
    [C-RING_R, C-RING_R, C+RING_R, C+RING_R],
    outline=(*INDIGO, 230), width=7)
img = composite(img, ring)

# Cyan highlight arc points on the ring (top-right quadrant)
for angle_deg in [30, 60, 330, 300]:
    a = math.radians(angle_deg - 90)
    rx = int(C + RING_R * math.cos(a))
    ry = int(C + RING_R * math.sin(a))
    img = draw_glow(img, rx, ry, 18, CYAN, intensity=220, blur=8)
    dot = new_layer()
    ImageDraw.Draw(dot).ellipse([rx-5, ry-5, rx+5, ry+5], fill=(*CYAN, 255))
    img = composite(img, dot)

# ── 3. Orion constellation (simplified: belt + key stars) ─────────────────────
# Belt: 3 stars diagonal at center (Mintaka, Alnilam, Alnitak)
BELT_ANGLE = math.radians(18)   # slight tilt like real Orion
BELT_SPACING = 95

belt = [
    (C - int(BELT_SPACING * math.cos(BELT_ANGLE)),
     C + int(BELT_SPACING * math.sin(BELT_ANGLE))),
    (C, C),
    (C + int(BELT_SPACING * math.cos(BELT_ANGLE)),
     C - int(BELT_SPACING * math.sin(BELT_ANGLE))),
]

# Shoulders: Betelgeuse (top-left, warm/amber) and Bellatrix (top-right)
betelgeuse = (C - 200, C - 190)
bellatrix  = (C + 185, C - 175)

# Feet: Rigel (bottom-right, bright/cyan) and Saiph (bottom-left)
rigel  = (C + 195, C + 205)
saiph  = (C - 185, C + 195)

all_stars = [
    # (x, y, radius, color, glow_color)
    (belt[0][0], belt[0][1], 14, WHITE,  INDIGO),   # Mintaka
    (belt[1][0], belt[1][1], 18, WHITE,  CYAN),      # Alnilam (center belt)
    (belt[2][0], belt[2][1], 14, WHITE,  INDIGO),   # Alnitak
    (betelgeuse[0], betelgeuse[1], 22, (255,220,180), AMBER),  # Betelgeuse warm
    (bellatrix[0],  bellatrix[1],  14, WHITE, INDIGO),
    (rigel[0],  rigel[1],  22, (200,240,255), CYAN),  # Rigel blue-white
    (saiph[0],  saiph[1],  12, WHITE, INDIGO),
]

# Constellation lines first (drawn below stars)
connections = [
    (belt[0], belt[1]), (belt[1], belt[2]),      # belt
    (betelgeuse, belt[0]),                        # left shoulder to belt
    (bellatrix,  belt[2]),                        # right shoulder to belt
    (belt[0], saiph),                             # belt to left foot
    (belt[2], rigel),                             # belt to right foot
    (betelgeuse, bellatrix),                      # across shoulders
]

for p1, p2 in connections:
    line_layer = new_layer()
    ImageDraw.Draw(line_layer).line([p1, p2], fill=(*INDIGO, 90), width=2)
    line_layer = line_layer.filter(ImageFilter.GaussianBlur(radius=1))
    img = composite(img, line_layer)

# Draw all stars
for (sx, sy, sr, sc, sgc) in all_stars:
    img = draw_star(img, sx, sy, sr, color=sc, glow_color=sgc, glow_r=sr*4)

# ── 4. Central super-node (Alnilam — center of belt, most prominent) ──────────
cx, cy = belt[1]
# Large outer glow
img = draw_glow(img, cx, cy, 70, CYAN, intensity=120, blur=30)
img = draw_glow(img, cx, cy, 45, WHITE, intensity=200, blur=15)
# Rings
for r, alpha, color in [(32, 255, CYAN), (22, 255, WHITE), (12, 255, WHITE)]:
    node = new_layer()
    ImageDraw.Draw(node).ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*color, alpha))
    img = composite(img, node)

# ── 5. Lightning bolt overlay on center star ──────────────────────────────────
bolt = new_layer()
bd = ImageDraw.Draw(bolt)
# Simple lightning bolt polygon centered on (cx, cy)
bx, by = cx, cy
pts = [
    (bx+5,  by-22),
    (bx-3,  by-3),
    (bx+7,  by-3),
    (bx-6,  by+22),
    (bx+2,  by+4),
    (bx-8,  by+4),
]
bd.polygon(pts, fill=(*AMBER, 255))
# Glow around bolt
bolt_g = bolt.filter(ImageFilter.GaussianBlur(radius=4))
img = composite(img, bolt_g)
img = composite(img, bolt)

# ── 6. Subtle sparkle dots scattered in background ────────────────────────────
import random
random.seed(42)
sparkles = new_layer()
sd = ImageDraw.Draw(sparkles)
for _ in range(60):
    sx = random.randint(60, SIZE-60)
    sy = random.randint(60, SIZE-60)
    # Skip center area
    if abs(sx - C) < 280 and abs(sy - C) < 280:
        continue
    sr2 = random.randint(1, 3)
    sa = random.randint(60, 160)
    sd.ellipse([sx-sr2, sy-sr2, sx+sr2, sy+sr2], fill=(*WHITE, sa))
img = composite(img, sparkles)

# ── 7. Vignette (darken corners to focus center) ──────────────────────────────
vignette = new_layer()
for r in range(500, 350, -8):
    alpha = int(12 * (r - 350) / 150)
    ImageDraw.Draw(vignette).ellipse([C-r, C-r, C+r, C+r],
                                      outline=(0, 0, 0, alpha), width=8)
vignette = vignette.filter(ImageFilter.GaussianBlur(radius=10))
img = composite(img, vignette)

# ── Save icon.png (with rounded corners mask for transparency) ─────────────────
mask = Image.new('L', (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, SIZE, SIZE], radius=210, fill=255)
img.putalpha(mask)
img.save('mobile/assets/icon.png')
print('icon.png saved')

# ── Adaptive icon (same design, slightly zoomed out, flat background) ──────────
adap = new_layer()
adap_bg = new_layer()
ImageDraw.Draw(adap_bg).rectangle([0, 0, SIZE, SIZE], fill=(*BG, 255))
adap = composite(adap, adap_bg)
# Paste the icon design (without rounded mask) scaled to 82% to leave padding
inner_size = int(SIZE * 0.82)
offset = (SIZE - inner_size) // 2
# Re-composite at full size, then scale
content = img.copy().convert('RGBA')
content_resized = content.resize((inner_size, inner_size), Image.LANCZOS)
adap_full = new_layer()
ImageDraw.Draw(adap_full).rectangle([0, 0, SIZE, SIZE], fill=(*BG, 255))
adap_full.paste(content_resized, (offset, offset), content_resized)
adap_full = adap_full.convert('RGBA')
adap_full.save('mobile/assets/adaptive-icon.png')
print('adaptive-icon.png saved')

# ── Favicon (32x32) ───────────────────────────────────────────────────────────
fav = img.copy().convert('RGBA')
fav = fav.resize((48, 48), Image.LANCZOS)
fav.save('mobile/assets/favicon.png')
print('favicon.png saved')

print('\nAll icons generated successfully!')
