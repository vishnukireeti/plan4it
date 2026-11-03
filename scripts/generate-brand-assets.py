#!/usr/bin/env python3
"""
Regenerates the favicon / app-icon / social-preview-image set in assets/.

Run this any time the app is renamed or recoloured — it's the one place
that bakes the name into actual image pixels (everything else is plain
text in index.html / robots.txt / sitemap.xml, which a normal find-and-
replace handles fine).

Usage:
    python3 scripts/generate-brand-assets.py

Requires Pillow (PIL) — already a dependency of nothing else here, so if
it's missing: pip install --break-system-packages Pillow

Mark: a rounded-square tile in the brand accent color with a white
checkmark (the "plan it, do it, done" idea). Keep TILE_RGB in sync with
the --color-brand-600 value in scripts/build-tailwind.mjs.
"""
from PIL import Image, ImageDraw, ImageFont

# ---- EDIT THESE WHEN RENAMING OR RECOLOURING --------------------------
APP_NAME = "Plan4it"
APP_TAGLINE = "Plan it. Do it. Done."
APP_DOMAIN_DISPLAY = "margai.netlify.app"   # shown as plain text on the OG image — still the
                                   # old domain; update once a custom domain is registered
TILE_RGB = (14, 165, 233)         # #0ea5e9 — sky-500, must match --color-brand-600
                                   # in scripts/build-tailwind.mjs
BG_RGB = (13, 17, 22)             # #0d1116 — dark graphite page background (OG image only)
ACCENT_TEXT_RGB = (56, 189, 248)  # #38bdf8 — the "4" in the wordmark
# ------------------------------------------------------------------------

WHITE = (255, 255, 255)
MUTED_RGB = (134, 149, 161)       # #8695a1 — tagline / domain text


def get_font(size, bold=True):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def draw_checkmark(draw, box, color, width_ratio=0.11):
    """box = (x0, y0, x1, y1) the square area the check is centered in."""
    x0, y0, x1, y1 = box
    w = x1 - x0
    lw = max(2, int(w * width_ratio))
    p1 = (x0 + w * 0.17, y0 + w * 0.52)
    p2 = (x0 + w * 0.40, y0 + w * 0.74)
    p3 = (x0 + w * 0.83, y0 + w * 0.28)
    draw.line([p1, p2, p3], fill=color, width=lw, joint="curve")
    # round the line caps/joints
    for pt in (p1, p2, p3):
        r = lw / 2
        draw.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r], fill=color)


def icon_tile(size, radius_ratio=0.22):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=TILE_RGB)
    draw_checkmark(d, (0, 0, size, size), WHITE)
    return img


def main():
    for size, name in [(32, "favicon-32.png"), (180, "apple-touch-icon.png"), (512, "icon-512.png")]:
        img = icon_tile(size)
        img.save(f"assets/{name}")
        print("wrote", name, img.size)

    # Open Graph / social preview image, 1200x630 (the size most platforms expect)
    W, H = 1200, 630
    og = Image.new("RGB", (W, H), BG_RGB)
    d = ImageDraw.Draw(og)

    mark_size = 92
    mark = icon_tile(mark_size)
    og.paste(mark, (90, 70), mark)

    # Wordmark: "Plan" + "4" (accent) + "it"
    word_font = get_font(84)
    x = 90
    y = 192
    for part, color in (("Plan", WHITE), ("4", ACCENT_TEXT_RGB), ("it", WHITE)):
        d.text((x, y), part, font=word_font, fill=color)
        bbox = d.textbbox((x, y), part, font=word_font)
        x = bbox[2]

    tag_font = get_font(24, bold=True)
    d.text((90, 300), APP_TAGLINE.upper(), font=tag_font, fill=MUTED_RGB)
    d.text((90, 556), f"{APP_DOMAIN_DISPLAY}  ·  Career & college guidance for Class 10–12 students in India",
           font=get_font(20, bold=False), fill=(91, 103, 113))

    og.save("assets/og-image.png")
    print("wrote og-image.png", og.size)


if __name__ == "__main__":
    main()
