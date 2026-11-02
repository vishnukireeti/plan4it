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
"""
from PIL import Image, ImageDraw, ImageFont

# ---- EDIT THESE WHEN RENAMING -------------------------------------------
APP_NAME = "Plan4it"
APP_INITIAL = "P"                 # the single letter shown on the icon mark
APP_TAGLINE_LINE1 = "Career & college guidance for Class 10–12"
APP_TAGLINE_LINE2 = "students in India."
APP_DOMAIN_DISPLAY = "margai.netlify.app"   # shown as plain text on the OG image — still the
                                   # old domain; update once a custom domain is registered
BRAND_RGB = (37, 99, 235)         # #2563eb — must match the `brand.600` value
                                   # in tailwind.config inside index.html
# ---------------------------------------------------------------------------

WHITE = (255, 255, 255)

def rounded_bg(size, radius_ratio=0.22):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BRAND_RGB)
    return img, d

def get_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def main():
    # Favicon / app icons (letter mark on a brand-colour rounded square)
    for size, name in [(32, "favicon-32.png"), (180, "apple-touch-icon.png"), (512, "icon-512.png")]:
        img, d = rounded_bg(size, 0.22)
        font = get_font(int(size * 0.58))
        bbox = d.textbbox((0, 0), APP_INITIAL, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]), APP_INITIAL, font=font, fill=WHITE)
        img.save(f"assets/{name}")
        print("wrote", name, img.size)

    # Open Graph / social preview image, 1200x630 (the size most platforms expect)
    W, H = 1200, 630
    og = Image.new("RGB", (W, H), BRAND_RGB)
    d = ImageDraw.Draw(og)

    mark_size = 96
    mark = Image.new("RGBA", (mark_size, mark_size), (0, 0, 0, 0))
    dm = ImageDraw.Draw(mark)
    dm.rounded_rectangle([0, 0, mark_size - 1, mark_size - 1], radius=int(mark_size * 0.22), fill=WHITE)
    fm = get_font(int(mark_size * 0.58))
    bbox = dm.textbbox((0, 0), APP_INITIAL, font=fm)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    dm.text(((mark_size - tw) / 2 - bbox[0], (mark_size - th) / 2 - bbox[1]), APP_INITIAL, font=fm, fill=BRAND_RGB)
    og.paste(mark, (80, 70), mark)

    title_font = get_font(66)
    tag_font = get_font(32)
    d.text((80, 200), APP_NAME.upper(), font=title_font, fill=WHITE)
    d.text((80, 290), APP_TAGLINE_LINE1, font=tag_font, fill=(219, 234, 254))
    d.text((80, 335), APP_TAGLINE_LINE2, font=tag_font, fill=(219, 234, 254))
    d.text((80, 540), APP_DOMAIN_DISPLAY, font=get_font(26), fill=(191, 219, 254))

    og.save("assets/og-image.png")
    print("wrote og-image.png", og.size)

if __name__ == "__main__":
    main()
