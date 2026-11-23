#!/usr/bin/env python3
"""Tout savoir en 30 s — moteur de rendu vidéo 9:16.

Usage :
    python3 render.py episodes/001-tour-eiffel.json [--voice voice/001-tour-eiffel] [--frames 2.5,9,14]

- Sans --voice : le rythme des mots est estimé (prototype muet, sous-titres calés).
- Avec --voice DOSSIER : lit DOSSIER/audio.mp3 + DOSSIER/timings.json (produits par voice.py)
  et synchronise animations + sous-titres sur la vraie voix.
"""
import argparse, json, math, os, re, subprocess, sys
from multiprocessing import Pool

import numpy as np
import skia

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")

# ---------- Identité visuelle ----------
INK = 0xFF0D151C
INK2 = 0xFF17232D
CREAM = (242, 233, 214)
OCHRE = (227, 169, 72)
FROST = (150, 182, 204)
MUTED = (120, 136, 148)


def col(rgb, a=1.0):
    return skia.Color(rgb[0], rgb[1], rgb[2], int(max(0, min(1, a)) * 255))


def tf(name):
    return skia.Typeface.MakeFromFile(os.path.join(FONTS, name))


SERIF = tf("cormorant-garamond-latin-500-normal.woff")
SERIF_IT = tf("cormorant-garamond-latin-600-italic.woff")
SANS_B = tf("archivo-latin-800-normal.woff")
SANS = tf("archivo-latin-500-normal.woff")

# ---------- Easing ----------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x


def prog(t, start, dur):
    return clamp((t - start) / dur) if dur > 0 else float(t >= start)


# ---------- Timing des mots ----------
def estimate_words(text):
    """Durées estimées (~2,7 mots/s) quand on n'a pas encore la voix."""
    out, t = [], 0.15
    for w in text.split():
        core = re.sub(r"[^\wÀ-ÿ']", "", w)
        d = 0.09 + 0.047 * len(core)
        out.append({"word": w, "start": t, "end": t + d})
        t += d
        if w.endswith((",", ":")):
            t += 0.14
        elif w.endswith((".", "!", "?")):
            t += 0.28
    return out, t + 0.25


def norm(s):
    return re.sub(r"[^\wÀ-ÿ']", "", s).lower()


def word_time(words, key, default=0.0, last=False):
    if isinstance(key, (int, float)):
        return float(key)
    if key is None:
        return default
    k = norm(key)
    for w in (reversed(words) if last else words):
        if norm(w["word"]).startswith(k):
            return w["start"]
    print(f"  ! mot-repère introuvable : {key}", file=sys.stderr)
    return default


# ---------- Texte ----------
def parse_rich(text):
    """'La tour *grandit* en été' -> [(mot, accent?)]"""
    out, accent = [], False
    for part in re.split(r"(\*)", text):
        if part == "*":
            accent = not accent
            continue
        for w in part.split():
            out.append((w, accent))
    return out


def layout_words(words, size, max_w):
    fonts = {False: skia.Font(SERIF, size), True: skia.Font(SERIF_IT, size * 1.04)}
    space = fonts[False].measureText(" ")
    lines, cur, cw = [], [], 0
    for w, acc in words:
        ww = fonts[acc].measureText(w)
        if cur and cw + space + ww > max_w:
            lines.append((cur, cw))
            cur, cw = [], 0
        cw += (space if cur else 0) + ww
        cur.append((w, acc, ww))
    if cur:
        lines.append((cur, cw))
    return lines, fonts, space


def draw_rich_title(c, text, cy, size, t, start, alpha=1.0, max_w=880):
    lines, fonts, space = layout_words(parse_rich(text), size, max_w)
    lh = size * 1.08
    y0 = cy - (len(lines) - 1) * lh / 2
    i = 0
    for li, (ws, lw) in enumerate(lines):
        x = (W - lw) / 2
        y = y0 + li * lh
        for w, acc, ww in ws:
            p = ease_out(prog(t, start + i * 0.07, 0.45))
            paint = skia.Paint(AntiAlias=True, Color=col(OCHRE if acc else CREAM, p * alpha))
            c.drawString(w, x, y + (1 - p) * 26, fonts[acc], paint)
            x += ww + space
            i += 1


def draw_text_centered(c, s, x, y, font, rgb, a=1.0, spacing=0.0):
    if spacing:
        widths = [font.measureText(ch) + spacing for ch in s]
        tw = sum(widths) - spacing
        cx = x - tw / 2
        p = skia.Paint(AntiAlias=True, Color=col(rgb, a))
        for ch, wd in zip(s, widths):
            c.drawString(ch, cx, y, font, p)
            cx += wd
    else:
        tw = font.measureText(s)
        c.drawString(s, x - tw / 2, y, font, skia.Paint(AntiAlias=True, Color=col(rgb, a)))


def draw_spaced(c, s, x, y, font, rgb, a=1.0, spacing=3.0):
    p = skia.Paint(AntiAlias=True, Color=col(rgb, a))
    for ch in s:
        c.drawString(ch, x, y, font, p)
        x += font.measureText(ch) + spacing
    return x


# ---------- Images (photos, cartes, illustrations) ----------
_IMG_CACHE = {}


def load_treated(path, mode="duotone", blur=0):
    """Charge une image et la passe aux couleurs du compte (une seule fois, mise en cache)."""
    key = (path, mode, blur)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    # recadrage 9:16 centré, en gardant de la marge pour le mouvement
    tw, th = int(W * 1.18), int(H * 1.18)
    sc = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, int(im.width * sc)), max(th, int(im.height * sc))), Image.LANCZOS)
    l, t = (im.width - tw) // 2, (im.height - th) // 2
    im = im.crop((l, t, l + tw, t + th))
    if blur:
        from PIL import ImageFilter
        im = im.filter(ImageFilter.GaussianBlur(blur))
    a = np.asarray(im).astype(np.float32) / 255
    if mode == "duotone":
        lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
        lum = np.clip((lum - 0.08) / 0.84, 0, 1) ** 1.1
        stops = np.array([[0.0, 13, 21, 28], [0.45, 58, 70, 76], [0.78, 196, 146, 70], [1.0, 242, 226, 196]], np.float32)
        out = np.stack([np.interp(lum, stops[:, 0], stops[:, c + 1]) for c in range(3)], -1)
        out = out * 0.85 + a * 255 * 0.15          # garde une pointe de la couleur d'origine
    else:  # "naturel" : couleurs d'origine, assombries et réchauffées
        out = a * 255 * np.array([1.0, 0.94, 0.86], np.float32) * 0.82
    rgba = np.dstack([np.clip(out, 0, 255).astype(np.uint8), np.full(out.shape[:2], 255, np.uint8)])
    img = skia.Image.fromarray(np.ascontiguousarray(rgba), colorType=skia.kRGBA_8888_ColorType)
    _IMG_CACHE[key] = img
    return img


def draw_image_layer(c, spec, t, dur, base_dir):
    if not spec.get("fichier"):          # image non trouvée : la scène garde le fond de marque
        return
    path = spec["fichier"] if os.path.isabs(spec["fichier"]) else os.path.join(base_dir, spec["fichier"])
    if not os.path.exists(path):
        print(f"  ! image introuvable : {path}", file=sys.stderr)
        return
    img = load_treated(path, spec.get("traitement", "duotone"), spec.get("flou", 0))
    k = ease_io(clamp(t / max(dur, 0.1)))
    mv = spec.get("mouvement", "zoom_in")
    iw, ih = img.width(), img.height()
    z = {"zoom_in": 1.0 + 0.10 * k, "zoom_out": 1.10 - 0.10 * k}.get(mv, 1.04)
    dx = {"pan_left": 1 - 2 * k, "pan_right": -1 + 2 * k}.get(mv, 0.0)
    dy = {"pan_up": 1 - 2 * k, "pan_down": -1 + 2 * k}.get(mv, 0.0)
    w, h = W * 1.0 * z, H * 1.0 * z
    cx = W / 2 + dx * (iw * W / (W * 1.18) - W) / 2 * 0.9
    cy = H / 2 + dy * (ih * H / (H * 1.18) - H) / 2 * 0.9
    fade = ease_out(prog(t, 0, 0.35)) if spec.get("fondu", True) else 1.0
    p = skia.Paint(AntiAlias=True, Alphaf=spec.get("opacite", 0.85) * fade)
    c.drawImageRect(img, skia.Rect(cx - w / 2 * 1.18, cy - h / 2 * 1.18, cx + w / 2 * 1.18, cy + h / 2 * 1.18),
                    skia.SamplingOptions(skia.FilterMode.kLinear), p)
    # dégradés de lisibilité : haut (titre) et bas (sous-titres)
    for y0, y1, ca, cb in ((0, 760, 0.92, 0.0), (1180, H, 0.0, 0.95)):
        sh = skia.GradientShader.MakeLinear([(0, y0), (0, y1)],
                                            [skia.Color(13, 21, 28, int(255 * ca)), skia.Color(13, 21, 28, int(255 * cb))])
        c.drawRect(skia.Rect(0, y0, W, y1), skia.Paint(Shader=sh))
    # vignette
    vg = skia.GradientShader.MakeRadial((W / 2, H / 2), H * 0.62,
                                        [skia.Color(13, 21, 28, 0), skia.Color(13, 21, 28, 170)], [0.55, 1.0])
    c.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Shader=vg))


# ---------- Fond + grain ----------
_rng = np.random.default_rng(7)
GRAIN = [(_rng.normal(0, 5, (H, W, 1))).astype(np.int16) for _ in range(1)]


def draw_background(c, T):
    c.clear(INK)
    shader = skia.GradientShader.MakeRadial(
        (W * 0.5, H * 0.38), H * 0.75, [INK2, INK], [0.0, 1.0])
    c.drawRect(skia.Rect(0, 0, W, H), skia.Paint(Shader=shader))
    # quadrillage de cahier, très discret, qui dérive lentement
    off = (T * 14) % 72
    p = skia.Paint(AntiAlias=True, Color=col(CREAM, 0.045))
    y = -72 + off
    while y < H:
        x = 36
        while x < W:
            c.drawCircle(x, y, 2.0, p)
            x += 72
        y += 72


def draw_brand(c, T, total):
    f = skia.Font(SANS_B, 26)
    draw_spaced(c, "TOUT SAVOIR EN 30 S", 90, 236, f, CREAM, 0.85, 3.2)
    remain = max(0, total - T)
    s = f"0:{int(math.ceil(remain)):02d}"
    tw = skia.Font(SANS_B, 26).measureText(s)
    c.drawString(s, W - 90 - tw - 8, 236, f, skia.Paint(AntiAlias=True, Color=col(OCHRE)))
    # barre de progression
    c.drawRect(skia.Rect(90, 258, W - 90, 261), skia.Paint(Color=col(CREAM, 0.14)))
    c.drawRect(skia.Rect(90, 258, 90 + (W - 180) * clamp(T / total), 261), skia.Paint(Color=col(OCHRE)))


# ---------- Sous-titres ----------
def chunk_words(words, max_words=3, max_chars=20):
    # « mer ? » : la ponctuation isolée (espace française) se colle au mot précédent
    merged = []
    for w in words:
        if merged and re.fullmatch(r"[?!:;»…]+", w["word"]):
            merged[-1] = dict(merged[-1], word=merged[-1]["word"] + "\u00a0" + w["word"], end=w["end"])
        else:
            merged.append(w)
    words = merged
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or len(" ".join(x["word"] for x in cur + [w])) > max_chars):
            chunks.append(cur)
            cur = []
        cur.append(w)
        if w["word"].endswith((".", ",", "!", "?", ":")):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    return chunks


def draw_captions(c, words, t):
    chunks = chunk_words(words)
    for i, ch in enumerate(chunks):
        s, e = ch[0]["start"], ch[-1]["end"]
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else e + 0.4
        if not (s <= t < max(e, nxt)):
            continue
        f = skia.Font(SANS_B, 58)
        txt = [w["word"].rstrip(",.:") for w in ch]
        sp = f.measureText(" ")
        widths = [f.measureText(x) for x in txt]
        tw = sum(widths) + sp * (len(txt) - 1)
        pop = ease_out(prog(t, s, 0.14))
        sc = 0.9 + 0.1 * pop
        c.save()
        c.translate(W / 2, 1530)
        c.scale(sc, sc)
        x = -tw / 2
        for w, wd, word in zip(ch, widths, txt):
            on = w["start"] <= t
            rgb = OCHRE if (w["start"] <= t < w["end"] + 0.05) else CREAM
            shadow = skia.Paint(AntiAlias=True, Color=skia.Color(0, 0, 0, int(150 * pop)),
                                MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 6))
            c.drawString(word, x, 4, f, shadow)
            c.drawString(word, x, 0, f, skia.Paint(AntiAlias=True, Color=col(rgb, pop * (1 if on else 0.55))))
            x += wd + sp
        c.restore()


# ---------- Tour Eiffel (dessin au trait) ----------
TB, TTOP, TCX = 1400, 700, 540          # base, sommet, axe
TH = TB - TTOP


def tower_y(m):  # hauteur en mètres -> y écran (324 m)
    return TB - TH * m / 324.0


def build_tower():
    hw = {0: 245, 57: 150, 115: 88, 200: 46, 276: 20, 300: 9}
    outline = skia.Path()
    for sgn in (-1, 1):
        pts = [(TCX + sgn * hw[m], tower_y(m)) for m in (0, 57, 115, 200, 276, 300)]
        outline.moveTo(*pts[0])
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            mx = (x0 + x1) / 2 + sgn * -6
            outline.quadTo(mx, (y0 + y1) / 2, x1, y1)
    # antenne
    outline.moveTo(TCX - 9, tower_y(300)); outline.lineTo(TCX, tower_y(324)); outline.lineTo(TCX + 9, tower_y(300))
    # arche entre les pieds
    outline.moveTo(TCX - 160, TB)
    outline.cubicTo(TCX - 150, tower_y(40), TCX + 150, tower_y(40), TCX + 160, TB)
    # plateformes
    for m, w in ((57, 175), (115, 104), (276, 30)):
        y = tower_y(m)
        outline.addRect(skia.Rect(TCX - w, y - 9, TCX + w, y))
    # treillis
    lattice = skia.Path()
    levels = [(0, 245), (57, 150), (115, 88), (160, 66), (200, 46), (240, 32), (276, 20)]
    for (m0, w0), (m1, w1) in zip(levels, levels[1:]):
        y0, y1 = tower_y(m0), tower_y(m1)
        for sgn in (-1, 1):
            a0, a1 = TCX + sgn * w0, TCX + sgn * w1
            b0, b1 = TCX + sgn * w0 * 0.55, TCX + sgn * w1 * 0.55
            lattice.moveTo(a0, y0); lattice.lineTo(b1, y1)
            lattice.moveTo(b0, y0); lattice.lineTo(a1, y1)
    return outline, lattice


TOWER_OUT, TOWER_LAT = build_tower()


def stroke(rgb, a, w, trim=None, glow=False):
    p = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=w,
                   Color=col(rgb, a), StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
    if trim is not None and trim < 1:
        p.setPathEffect(skia.TrimPathEffect.Make(0, max(0.0001, trim)))
    if glow:
        p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 10))
    return p


def draw_tower_shape(c, a=1.0, trim=None, rgb=CREAM, lat_a=0.35):
    c.drawPath(TOWER_OUT, stroke(rgb, a, 3.2, trim))
    c.drawPath(TOWER_LAT, stroke(rgb, a * lat_a, 1.6, trim))


def el_tower(c, el, t, ctx):
    mode = el.get("mode", "static")
    at = ctx["at"](el.get("at"), 0.0)
    if mode == "draw":
        tr = ease_io(prog(t, 0.2, 2.2))
        draw_tower_shape(c, 0.9, tr)
        return
    if mode == "grow":
        draw_tower_shape(c, 0.55)
        g = ease_io(prog(t, at, 1.4))
        s = 1 + 0.05 * g  # exagéré pour être visible
        c.save()
        c.translate(TCX, TB); c.scale(1, s); c.translate(-TCX, -TB)
        c.drawPath(TOWER_OUT, stroke(OCHRE, 0.35 * g, 6, glow=True))
        c.drawPath(TOWER_OUT, stroke(OCHRE, 0.95 * g, 3.2))
        c.restore()
        # règle +15 cm
        top0 = tower_y(324)
        top1 = TB - (TB - top0) * s
        x = TCX + 70
        p = stroke(OCHRE, g, 3)
        c.drawLine(x - 14, top0, x + 14, top0, stroke(CREAM, 0.6 * g, 3))
        c.drawLine(x - 14, top1, x + 14, top1, p)
        c.drawLine(x, top0, x, top1, p)
        lp = ease_out(prog(t, at + 0.9, 0.4))
        f = skia.Font(SANS_B, 44)
        c.drawString("+15 cm", x + 30, (top0 + top1) / 2 + 16, f, skia.Paint(AntiAlias=True, Color=col(OCHRE, lp)))
        return
    if mode == "lean":
        k = ease_io(prog(t, at, 2.6))
        ang = math.radians(195 - 210 * k)        # le soleil passe de gauche à droite
        sx, sy = TCX + 400 * math.cos(ang), 1080 - 330 * math.sin(ang)
        fade = ease_out(prog(t, 0, 0.5))
        glowp = skia.Paint(AntiAlias=True, Color=col(OCHRE, 0.45 * fade),
                           MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 40))
        c.drawCircle(sx, sy, 70, glowp)
        c.drawCircle(sx, sy, 42, skia.Paint(AntiAlias=True, Color=col(OCHRE, fade)))
        for i in range(10):
            a = i * math.pi / 5 + t * 0.6
            c.drawLine(sx + 58 * math.cos(a), sy + 58 * math.sin(a), sx + 78 * math.cos(a), sy + 78 * math.sin(a),
                       stroke(OCHRE, 0.8 * fade, 3))
        # la tour se penche à l'opposé du soleil (exagéré)
        lean = math.cos(ang) * 0.085
        draw_tower_shape(c, 0.22)  # position de repos, en fantôme
        c.save()
        c.translate(TCX, TB); c.skew(lean, 0); c.translate(-TCX, -TB)
        draw_tower_shape(c, 0.9 * fade + 0.1)
        c.restore()
        return
    draw_tower_shape(c, 0.9)


def el_temp(c, el, t, ctx):
    at = ctx["at"](el.get("at"), 0.0)
    p = ease_out(prog(t, at, 0.4))
    if p <= 0:
        return
    rgb = FROST if el.get("cold") else OCHRE
    x = 150 if el.get("side") == "left" else W - 150
    y = 1180 + (1 - p) * 30
    draw_text_centered(c, el["text"], x, y, skia.Font(SANS_B, 26), rgb, p * 0.9, spacing=3)
    draw_text_centered(c, el["value"], x, y + 62, skia.Font(SERIF, 64), CREAM, p)
    # mini-thermomètre
    tx, ty = x, y - 150
    c.drawRoundRect(skia.Rect(tx - 9, ty - 70, tx + 9, ty + 20), 9, 9, stroke(CREAM, 0.6 * p, 2.5))
    c.drawCircle(tx, ty + 32, 18, stroke(CREAM, 0.6 * p, 2.5))
    lvl = 0.2 if el.get("cold") else 0.95
    fill = ty + 20 - 85 * lvl * ease_out(prog(t, at + 0.15, 0.7))
    c.drawRoundRect(skia.Rect(tx - 4, fill, tx + 4, ty + 26), 4, 4, skia.Paint(AntiAlias=True, Color=col(rgb, p)))
    c.drawCircle(tx, ty + 32, 12, skia.Paint(AntiAlias=True, Color=col(rgb, p)))


def el_bar(c, el, t, ctx):
    heat_at = ctx["at"](el.get("heat_at"), 1.0)
    lab_at = ctx["at"](el.get("label_at"), 2.0)
    fin = ease_out(prog(t, 0.1, 0.5))
    h = ease_io(prog(t, heat_at, 1.6))
    cy = 1010
    L = 560 * (1 + 0.12 * h)       # allongement très exagéré
    x0 = (W - 560) / 2
    rgb = tuple(int(a + (b - a) * h) for a, b in zip((138, 154, 166), (232, 140, 60)))
    if h > 0:
        c.drawRoundRect(skia.Rect(x0, cy - 34, x0 + L, cy + 34), 14, 14,
                        skia.Paint(AntiAlias=True, Color=col(rgb, 0.5 * h),
                                   MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 26)))
    c.drawRoundRect(skia.Rect(x0, cy - 26, x0 + L, cy + 26), 10, 10, skia.Paint(AntiAlias=True, Color=col(rgb, fin)))
    # reflets
    c.drawLine(x0 + 18, cy - 12, x0 + L - 18, cy - 12, stroke((255, 255, 255), 0.18 * fin, 3))
    # cote 1 m
    f = skia.Font(SANS_B, 26)
    draw_text_centered(c, "1 MÈTRE DE FER", W / 2, cy - 90, f, CREAM, 0.8 * fin, spacing=3)
    c.drawLine(x0, cy - 60, x0 + 560, cy - 60, stroke(CREAM, 0.4 * fin, 2))
    for xx in (x0, x0 + 560):
        c.drawLine(xx, cy - 70, xx, cy - 50, stroke(CREAM, 0.4 * fin, 2))
    # flammes / degrés
    if h > 0:
        draw_text_centered(c, "+1 °C", W / 2, cy + 120, skia.Font(SERIF, 70), OCHRE, h)
    lp = ease_out(prog(t, lab_at, 0.5))
    if lp > 0:
        draw_text_centered(c, "+0,012 mm", W / 2, cy + 230 + (1 - lp) * 20, skia.Font(SERIF_IT, 92), CREAM, lp)
        draw_text_centered(c, "(allongement exagéré à l'écran)", W / 2, cy + 290, skia.Font(SANS, 26), MUTED, lp * 0.8)


def el_equation(c, el, t, ctx):
    y = 760
    f = skia.Font(SERIF, 96)
    for ln in el["lines"]:
        at = ctx["at"](ln.get("at"), 0.0)
        p = ease_out(prog(t, at, 0.45))
        if p > 0:
            draw_text_centered(c, ln["text"], W / 2 + (1 - p) * 40, y, f, CREAM, p)
        y += 130
    rat = ctx["at"](el.get("result_at"), 3.0)
    p = ease_out(prog(t, rat - 0.3, 0.4))
    if p > 0:
        c.drawLine(W / 2 - 260 * p, y - 70, W / 2 + 260 * p, y - 70, stroke(OCHRE, 1, 3))
        target = float(el["result"].replace(",", "."))
        v = target * ease_out(prog(t, rat - 0.2, 1.2))
        s = f"{v:.1f}".replace(".", ",")
        big = skia.Font(SERIF_IT, 190)
        unit = skia.Font(SERIF, 90)
        tw = big.measureText(s) + 24 + unit.measureText(el["unit"])
        x = W / 2 - tw / 2
        glowp = skia.Paint(AntiAlias=True, Color=col(OCHRE, 0.35 * p),
                           MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 30))
        c.drawString(s, x, y + 120, big, glowp)
        c.drawString(s, x, y + 120, big, skia.Paint(AntiAlias=True, Color=col(OCHRE, p)))
        c.drawString(el["unit"], x + big.measureText(s) + 24, y + 120, unit, skia.Paint(AntiAlias=True, Color=col(CREAM, p)))


def el_note(c, el, t, ctx):
    at = ctx["at"](el.get("at"), 0.0)
    p = ease_out(prog(t, at, 0.5))
    draw_text_centered(c, el["text"], W / 2, 1450, skia.Font(SANS, 26), MUTED, 0.8 * p)


def el_tag(c, el, t, ctx):
    p = ease_out(prog(t, 0.05, 0.5))
    f = skia.Font(SANS_B, 26)
    s = el["text"]
    tw = sum(f.measureText(ch) + 3 for ch in s) - 3
    r = skia.Rect(W / 2 - tw / 2 - 22, 312, W / 2 + tw / 2 + 22, 360)
    c.drawRoundRect(r, 24, 24, stroke(OCHRE, 0.8 * p, 2))
    draw_text_centered(c, s, W / 2, 345, f, OCHRE, p, spacing=3)


def el_title(c, el, t, ctx):
    draw_rich_title(c, el["text"], el.get("y", 500), el.get("size", 100), t, 0.0)


def el_outro(c, el, t, ctx):
    draw_rich_title(c, el["title"], 820, 118, t, 0.1)
    p = ease_out(prog(t, 0.6, 0.6))
    # logo-tampon : un cadran 30 s
    cx, cy, r = W / 2, 1110, 92
    c.drawCircle(cx, cy, r, stroke(CREAM, 0.35 * p, 2.5))
    sweep = 360 * ease_io(prog(t, 0.6, 1.6))
    c.drawArc(skia.Rect(cx - r, cy - r, cx + r, cy + r), -90, sweep, False, stroke(OCHRE, p, 7))
    draw_text_centered(c, "30", cx, cy + 26, skia.Font(SERIF_IT, 80), CREAM, p)
    cat = ctx["at"](el.get("cta_at"), 2.0)
    q = ease_out(prog(t, cat - 0.4, 0.5))
    if q > 0:
        f = skia.Font(SANS_B, 34)
        s = el["cta"]
        tw = f.measureText(s)
        rr = skia.Rect(W / 2 - tw / 2 - 34, 1290, W / 2 + tw / 2 + 34, 1372)
        c.drawRoundRect(rr, 41, 41, skia.Paint(AntiAlias=True, Color=col(OCHRE, q)))
        c.drawString(s, W / 2 - tw / 2, 1343, f, skia.Paint(AntiAlias=True, Color=skia.Color(13, 21, 28, int(255 * q))))


# ---------- Blocs génériques (utilisables pour n'importe quel sujet) ----------
def _fmt(v, dec):
    s = f"{v:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def el_chiffre(c, el, t, ctx):
    """Grand chiffre qui compte : {"type":"chiffre","valeur":"8,6","unite":"millions","texte":"d'habitants","at":"mot"}"""
    at = ctx["at"](el.get("at"), 0.2)
    p = ease_out(prog(t, at, 0.4))
    if p <= 0:
        return
    raw = str(el["valeur"]).replace(" ", "").replace(",", ".")
    target = float(raw); dec = len(raw.split(".")[1]) if "." in raw else 0
    v = target * ease_out(prog(t, at, 1.3))
    s = el.get("prefixe", "") + _fmt(v, dec)
    y = el.get("y", 1000)
    big = skia.Font(SANS_B, el.get("taille", 190))
    glowp = skia.Paint(AntiAlias=True, Color=col(OCHRE, 0.35 * p),
                       MaskFilter=skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 34))
    tw = big.measureText(s)
    c.drawString(s, W / 2 - tw / 2, y, big, glowp)
    c.drawString(s, W / 2 - tw / 2, y + (1 - p) * 30, big, skia.Paint(AntiAlias=True, Color=col(OCHRE, p)))
    if el.get("unite"):
        draw_text_centered(c, el["unite"], W / 2, y + 100, skia.Font(SERIF_IT, 72), CREAM, p)
    if el.get("texte"):
        q = ease_out(prog(t, at + 0.5, 0.5))
        draw_text_centered(c, el["texte"].upper(), W / 2, y + 175, skia.Font(SANS_B, 28), CREAM, 0.85 * q, spacing=3)


def el_comparaison(c, el, t, ctx):
    """Deux colonnes A / B avec barres : {"type":"comparaison","a":{"nom":"Paris","valeur":105,"texte":"105 km²"},"b":{...},"at":"mot"}"""
    at = ctx["at"](el.get("at"), 0.2)
    a, b = el["a"], el["b"]
    m = max(float(a["valeur"]), float(b["valeur"])) or 1
    base, hmax = 1330, 520
    for i, (d, x) in enumerate(((a, W / 2 - 200), (b, W / 2 + 200))):
        st = at + i * 0.5 if not el.get("at_b") or i == 0 else ctx["at"](el.get("at_b"), at + 0.5)
        p = ease_out(prog(t, st, 0.45)); g = ease_io(prog(t, st, 1.1))
        if p <= 0:
            continue
        h = hmax * float(d["valeur"]) / m * g
        rgb = OCHRE if float(d["valeur"]) == m else FROST
        c.drawRoundRect(skia.Rect(x - 95, base - h, x + 95, base), 12, 12, skia.Paint(AntiAlias=True, Color=col(rgb, 0.9 * p)))
        draw_text_centered(c, d.get("texte", str(d["valeur"])), x, base - h - 30, skia.Font(SERIF_IT, 64), CREAM, p)
        draw_text_centered(c, d["nom"].upper(), x, base + 60, skia.Font(SANS_B, 30), CREAM, 0.9 * p, spacing=3)
    c.drawLine(W / 2 - 340, base, W / 2 + 340, base, stroke(CREAM, 0.35, 2))


def el_liste(c, el, t, ctx):
    """Étapes numérotées : {"type":"liste","items":[{"texte":"…","at":"mot"}, …]}"""
    y = el.get("y", 820)
    f = skia.Font(SERIF, 64); fn = skia.Font(SERIF_IT, 64)
    for i, it in enumerate(el["items"]):
        at = ctx["at"](it.get("at"), 0.3 + i * 0.8)
        p = ease_out(prog(t, at, 0.45))
        if p > 0:
            x = 130 + (1 - p) * 40
            c.drawCircle(x + 34, y - 22, 40, stroke(OCHRE, p, 3))
            draw_text_centered(c, str(i + 1), x + 34, y, fn, OCHRE, p)
            c.drawString(it["texte"], x + 110, y, f, skia.Paint(AntiAlias=True, Color=col(CREAM, p)))
        y += 150


def el_vraifaux(c, el, t, ctx):
    """Quiz : {"type":"vraifaux","affirmation":"…","reponse":"FAUX","at_reponse":"mot"}"""
    p = ease_out(prog(t, 0.1, 0.5))
    draw_text_centered(c, "VRAI OU FAUX ?", W / 2, 760, skia.Font(SANS_B, 34), OCHRE, p, spacing=5)
    lines, fonts, space = layout_words(parse_rich(el["affirmation"]), 70, 820)
    y = 880
    for ws, lw in lines:
        x = (W - lw) / 2
        for w, acc, ww in ws:
            c.drawString(w, x, y, fonts[acc], skia.Paint(AntiAlias=True, Color=col(OCHRE if acc else CREAM, p)))
            x += ww + space
        y += 80
    ra = ctx["at_last"](el.get("at_reponse"), 2.0)   # « Vrai ou faux ? … Faux ! » : la réponse est la dernière occurrence
    q = ease_out(prog(t, ra, 0.35))
    if q > 0:
        ok = el["reponse"].upper().startswith("V")
        rgb = (120, 200, 140) if ok else (230, 110, 90)
        sc = 0.8 + 0.2 * q
        c.save(); c.translate(W / 2, y + 120); c.scale(sc, sc)
        r = skia.Rect(-210, -75, 210, 45)
        c.drawRoundRect(r, 22, 22, skia.Paint(AntiAlias=True, Color=col(rgb, q)))
        draw_text_centered(c, el["reponse"].upper(), 0, 12, skia.Font(SANS_B, 76), (13, 21, 28), q, spacing=4)
        c.restore()


RENDERERS = {"tower": el_tower, "temp": el_temp, "bar": el_bar, "equation": el_equation,
             "note": el_note, "tag": el_tag, "title": el_title, "outro": el_outro,
             "chiffre": el_chiffre, "comparaison": el_comparaison, "liste": el_liste, "vraifaux": el_vraifaux}
ORDER = ["tower", "temp", "bar", "equation", "chiffre", "comparaison", "liste", "vraifaux",
         "note", "tag", "title", "outro"]


# ---------- Timeline ----------
def build_timeline(ep, voice_dir=None, base_dir="."):
    timings = None
    if voice_dir and os.path.exists(os.path.join(voice_dir, "timings.json")):
        timings = json.load(open(os.path.join(voice_dir, "timings.json")))
    scenes, T = [], 0.0
    for i, sc in enumerate(ep["scenes"]):
        if timings:
            words = timings["scenes"][i]["words"]
            dur = timings["scenes"][i]["duration"]
        else:
            words, dur = estimate_words(sc["vo"])
        if i == len(ep["scenes"]) - 1:
            dur += 1.2  # laisser respirer la fin
        scenes.append({"index": i, "start": T, "dur": dur, "words": words, "elements": sc["elements"],
                       "image": sc.get("image"), "base_dir": base_dir})
        T += dur
    return scenes, T


def render_frame(c, sc, t, total):
    T = sc["start"] + t
    draw_background(c, T)
    if sc.get("image"):
        draw_image_layer(c, sc["image"], t, sc["dur"], sc["base_dir"])
    ctx = {"at": lambda k, d: word_time(sc["words"], k, d),
           "at_last": lambda k, d: word_time(sc["words"], k, d, last=True)}
    # fondu de sortie de scène (les éléments, pas le fond)
    out = 1 - ease_io(prog(t, sc["dur"] - 0.22, 0.22))
    c.saveLayerAlpha(None, int(255 * out))
    for kind in ORDER:
        for el in sc["elements"]:
            if el["type"] == kind:
                RENDERERS[kind](c, el, t, ctx)
    c.restore()
    draw_captions(c, sc["words"], t)
    draw_brand(c, T, total)


def to_rgb(surface, T):
    arr = surface.toarray()[:, :, 2::-1].astype(np.int16)  # BGRA -> RGB
    arr += GRAIN[0]  # grain fixe : texture papier, fichier léger
    np.clip(arr, 0, 255, out=arr)
    return arr.astype(np.uint8)


def render_scene(args):
    sc, total, outdir = args
    n = int(round(sc["dur"] * FPS))
    tmp = os.path.join(outdir, f"scene{sc['index']:02d}.tmp.mp4")
    final = os.path.join(outdir, f"scene{sc['index']:02d}.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                           "-crf", "18", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    surf = skia.Surface(W, H)
    for f in range(n):
        t = f / FPS
        with surf as c:
            render_frame(c, sc, t, total)
        ff.stdin.write(to_rgb(surf, sc["start"] + t).tobytes())
        if f % 60 == 0:
            print(f"  scène {sc['index'] + 1} : image {f}/{n}", flush=True)
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError(f"ffmpeg a échoué pour la scène {sc['index']}")
    os.replace(tmp, final)
    return final


def still(scenes, total, T, path):
    for sc in scenes:
        if sc["start"] <= T < sc["start"] + sc["dur"]:
            surf = skia.Surface(W, H)
            with surf as c:
                render_frame(c, sc, T - sc["start"], total)
            from PIL import Image
            Image.fromarray(to_rgb(surf, T)).save(path)
            return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--voice")
    ap.add_argument("--frames", help="liste de secondes : n'écrit que des images fixes")
    ap.add_argument("--out", default="out")
    a = ap.parse_args()
    ep = json.load(open(a.episode))
    scenes, total = build_timeline(ep, a.voice, os.path.dirname(os.path.abspath(a.episode)) + "/..")
    outdir = os.path.join(a.out, ep["id"])
    os.makedirs(outdir, exist_ok=True)
    print(f"Durée : {total:.1f} s, {len(scenes)} scènes")
    if a.frames:
        for s in a.frames.split(","):
            print(still(scenes, total, float(s), os.path.join(outdir, f"still_{float(s):05.1f}.png")))
        return
    # « spawn » et non « fork » : un fork après chargement de skia/fontconfig peut se figer
    import multiprocessing as mp
    workers = int(os.environ.get("RENDER_WORKERS") or os.cpu_count() or 2)
    print(f"Rendu sur {workers} processus", flush=True)
    with mp.get_context("spawn").Pool(workers) as pool:
        files = pool.map(render_scene, [(sc, total, outdir) for sc in scenes])
    lst = os.path.join(outdir, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(f)}'\n" for f in files))
    silent = os.path.join(outdir, "video_muette.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", "-movflags", "+faststart", silent], check=True)
    final = os.path.join(outdir, f"{ep['id']}.mp4")
    audio = os.path.join(a.voice, "audio.mp3") if a.voice else None
    if audio and os.path.exists(audio):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", audio, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-af", "apad", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", final], check=True)
    else:
        os.replace(silent, final)
    print(final)


if __name__ == "__main__":
    main()
