"""
Generates a beautiful app icon for Agent Helper.
Outputs: images/icon.ico (multi-size: 16,32,48,64,128,256)
Design: Deep green rounded square, white headset, soft glow ring.
"""

import math
from PIL import Image, ImageDraw, ImageFilter

# ── Palette ───────────────────────────────────────────────────────
BG_OUTER   = (0,  0,  0, 0)          # transparent
GREEN_DARK  = (0, 140, 70)            # #008C46
GREEN_MID   = (0, 166, 80)            # #00A650  Safaricom green
GREEN_LIGHT = (30, 200, 110)          # highlight
WHITE       = (255, 255, 255, 255)
GLOW        = (180, 255, 210, 60)     # subtle inner glow tint


def draw_icon(size: int) -> Image.Image:
    S = size
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = int(S * 0.04)
    r   = int(S * 0.22)   # corner radius

    # ── Background: gradient rounded square ──────────────────────
    # Simulate gradient by drawing concentric filled rounded rects
    steps = 40
    for i in range(steps, -1, -1):
        t  = i / steps
        c  = tuple(int(GREEN_DARK[k] + (GREEN_MID[k] - GREEN_DARK[k]) * t) for k in range(3)) + (255,)
        inset = pad + int((steps - i) * S * 0.003)
        draw.rounded_rectangle([inset, inset, S - inset, S - inset],
                                radius=max(4, r - i // 3), fill=c)

    # ── Inner glow ring ───────────────────────────────────────────
    glow_pad = int(S * 0.08)
    draw.rounded_rectangle(
        [glow_pad, glow_pad, S - glow_pad, S - glow_pad],
        radius=int(r * 0.8), outline=GLOW, width=max(1, int(S * 0.025))
    )

    # ── Headset drawing ───────────────────────────────────────────
    lw      = max(2, int(S * 0.055))   # line width
    cx      = S / 2
    top_y   = S * 0.18
    mid_y   = S * 0.52
    ear_r   = S * 0.115
    ear_w   = max(2, int(S * 0.075))

    # Headband arc (top semicircle)
    band_l = cx - S * 0.285
    band_r = cx + S * 0.285
    band_t = top_y
    band_b = mid_y + S * 0.02
    draw.arc([band_l, band_t, band_r, band_b], start=200, end=340, fill=WHITE, width=lw)

    # Left ear cup — filled rounded pill shape
    lx = band_l + S * 0.01
    lew = ear_r * 0.75
    leh = ear_r * 1.5
    draw.rounded_rectangle(
        [lx - lew, mid_y - leh / 2, lx + lew, mid_y + leh / 2],
        radius=int(lew * 0.9), fill=WHITE
    )

    # Right ear cup — filled rounded pill shape
    rx = band_r - S * 0.01
    draw.rounded_rectangle(
        [rx - lew, mid_y - leh / 2, rx + lew, mid_y + leh / 2],
        radius=int(lew * 0.9), fill=WHITE
    )

    # Mic arm — curved down-right from right ear cup
    mic_start_x = int(rx)
    mic_start_y = int(mid_y + ear_r * 0.8)
    mic_end_x   = int(cx + S * 0.14)
    mic_end_y   = int(S * 0.80)

    # Draw mic arm as polyline (approximate curve)
    pts = []
    for t in [i / 12 for i in range(13)]:
        # Quadratic bezier: P0 → control → P1
        ctrl_x = mic_start_x - S * 0.04
        ctrl_y = mic_start_y + (mic_end_y - mic_start_y) * 0.6
        bx = (1-t)**2 * mic_start_x + 2*(1-t)*t * ctrl_x + t**2 * mic_end_x
        by = (1-t)**2 * mic_start_y + 2*(1-t)*t * ctrl_y + t**2 * mic_end_y
        pts.append((bx, by))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i+1]], fill=WHITE, width=lw)

    # Mic capsule (rounded rect at end of arm)
    mw = S * 0.07
    mh = S * 0.11
    mx = mic_end_x - mw / 2
    my = mic_end_y - mh / 2
    draw.rounded_rectangle([mx, my, mx + mw, my + mh],
                            radius=int(mw * 0.5), fill=WHITE)

    # ── Subtle top-left shine glint ───────────────────────────────
    shine_r = int(S * 0.12)
    shine_img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shine_img)
    sdraw.ellipse([int(S*0.12), int(S*0.10),
                   int(S*0.12) + shine_r, int(S*0.10) + shine_r],
                  fill=(255, 255, 255, 38))
    shine_img = shine_img.filter(ImageFilter.GaussianBlur(shine_r // 2))
    img = Image.alpha_composite(img, shine_img)

    return img


def main():
    import pathlib
    out_dir = pathlib.Path("images")
    out_dir.mkdir(exist_ok=True)

    sizes = [256, 128, 64, 48, 32, 16]
    frames = []
    for s in sizes:
        frame = draw_icon(s).convert("RGBA")
        frames.append(frame)
        frame.save(out_dir / f"icon_{s}.png")
        print(f"  Generated {s}x{s}")

    # Save multi-resolution .ico
    ico_path = out_dir / "icon.ico"
    frames[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=frames[1:],
    )
    print(f"\nIcon saved: {ico_path}")
    print("Preview PNGs saved in images/")


if __name__ == "__main__":
    main()
