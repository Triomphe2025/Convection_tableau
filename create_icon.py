"""
Generateur d'icone TriosSeconverter.
Produit icon.ico (256x256 + tailles réduites) via Pillow.

Usage :  python create_icon.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math


# ── Palette ──────────────────────────────────────────────────────────
C_BG_DARK  = (15,  15,  35)   # fond bleu très foncé
C_BG_MID   = (26,  26,  70)   # fond intermédiaire
C_RED      = (233, 69,  96)   # rouge TriosSeconverter
C_VIOLET   = (83,  52,  131)  # violet secondaire
C_WHITE    = (240, 245, 255)  # blanc cassé
C_GOLD     = (255, 195, 50)   # jaune / or (borne)
C_GREY     = (160, 170, 200)  # gris clair


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size

    # ── Fond rond avec dégradé simulé (cercles concentriques) ────────
    for r in range(s // 2, 0, -1):
        ratio = r / (s // 2)
        col = tuple(int(C_BG_DARK[i] + (C_BG_MID[i] - C_BG_DARK[i]) * (1 - ratio))
                    for i in range(3)) + (255,)
        x0, y0 = s // 2 - r, s // 2 - r
        x1, y1 = s // 2 + r, s // 2 + r
        d.ellipse([x0, y0, x1, y1], fill=col)

    # ── Symbole bornier : 3 blocs rectangulaires superposés ──────────
    bw  = int(s * 0.48)          # largeur bloc
    bh  = int(s * 0.13)          # hauteur bloc
    gap = int(s * 0.03)          # espace entre blocs
    total_h = 3 * bh + 2 * gap
    bx  = (s - bw) // 2
    by  = (s - total_h) // 2 - int(s * 0.04)  # légèrement au-dessus du centre

    for i in range(3):
        y = by + i * (bh + gap)
        # Corps du bornier : rectangle arrondi
        r_corner = bh // 4
        # Ombre
        d.rounded_rectangle([bx+2, y+2, bx+bw+2, y+bh+2],
                             radius=r_corner, fill=(10, 10, 25, 180))
        # Corps
        d.rounded_rectangle([bx, y, bx+bw, y+bh],
                             radius=r_corner, fill=C_VIOLET)
        # Encoche dorée (vis de serrage)
        screw_w = int(bh * 0.55)
        screw_h = int(bh * 0.55)
        sx = bx + bw - screw_w - int(s * 0.03)
        sy = y + (bh - screw_h) // 2
        d.ellipse([sx, sy, sx + screw_w, sy + screw_h], fill=C_GOLD)
        # Fil rouge côté gauche
        wire_len = int(bw * 0.22)
        wire_y   = y + bh // 2
        d.rectangle([bx - wire_len, wire_y - 2, bx, wire_y + 2], fill=C_RED)

    # ── Lettres "TS" en superposition ────────────────────────────────
    fs = max(10, int(s * 0.22))
    try:
        font = ImageFont.truetype("arialbd.ttf", fs)
    except Exception:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", fs)
        except Exception:
            font = ImageFont.load_default()

    label = "TS"
    # Ombre
    ty = by + total_h + int(s * 0.04)
    bbox = d.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    tx = (s - tw) // 2
    d.text((tx + 1, ty + 1), label, font=font, fill=(0, 0, 0, 160))
    # Texte principal : T en rouge, S en blanc
    d.text((tx, ty), "T", font=font, fill=C_RED)
    # Mesurer le "T" pour positionner le "S"
    tb = d.textbbox((0, 0), "T", font=font)
    d.text((tx + tb[2] - tb[0], ty), "S", font=font, fill=C_WHITE)

    # ── Cercle de contour lumineux ────────────────────────────────────
    margin = max(2, s // 32)
    d.ellipse([margin, margin, s - margin, s - margin],
              outline=C_RED, width=max(1, s // 64))

    return img


def main():
    sizes = [256, 128, 64, 48, 32, 16]
    images = [draw_icon(sz) for sz in sizes]

    out = Path("icon.ico")
    images[0].save(
        str(out),
        format="ICO",
        sizes=[(sz, sz) for sz in sizes],
        append_images=images[1:],
    )
    print(f"[OK] Icone creee : {out}  ({out.stat().st_size // 1024} Ko)")
    print(f"     Tailles incluses : {sizes}")

    # Apercu PNG optionnel
    images[0].save("icon_preview.png")
    print("[OK] Apercu : icon_preview.png")


if __name__ == "__main__":
    main()
