#!/usr/bin/env python3
"""Va chercher l'image de chaque scène et l'enregistre dans images/<id>/.

Dans l'épisode JSON, chaque scène peut avoir :
    "image": {"recherche": "eiffel tower sunset", "mouvement": "zoom_in"}           -> photo Pixabay / Pexels / Openverse
    "image": {"ia": "close-up of riveted iron lattice, warm light", "mouvement": "pan_up"}  -> image générée (OpenAI)
    "image": {"fichier": "images/001/ma-photo.jpg"}                                  -> votre propre image
Le script remplit "fichier" et note les crédits photo dans images/<id>/credits.txt.

    python3 fetch_images.py episodes/001-tour-eiffel.json
Clés dans .env, toutes optionnelles : PIXABAY_API_KEY (gratuite, affichée sur pixabay.com/api/docs une fois
connecté), PEXELS_API_KEY, OPENAI_API_KEY. Sans aucune clé, le script utilise Openverse (images libres de droits).
Uniquement la bibliothèque standard Python.
"""
import base64, json, os, sys, urllib.parse, urllib.request

from voice import load_env

STYLE_IA = ("vertical 9:16 photograph, cinematic, moody low-key lighting, deep navy shadows and warm golden "
            "highlights, shallow depth of field, rich texture, no text, no logo, no watermark. Subject: ")


def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "tout-savoir-30s", **(headers or {})})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def pexels(query, used):
    url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode(
        {"query": query, "orientation": "portrait", "size": "large", "per_page": 15})
    res = json.loads(get(url, {"Authorization": os.environ["PEXELS_API_KEY"]}))
    for ph in res.get("photos", []):
        if ph["id"] not in used:
            used.add(ph["id"])
            return get(ph["src"]["large2x"]), f'Photo : {ph["photographer"]} / Pexels ({ph["url"]})'
    raise RuntimeError(f"Aucune photo Pexels pour « {query} »")


def pixabay(query, used):
    url = "https://pixabay.com/api/?" + urllib.parse.urlencode(
        {"key": os.environ["PIXABAY_API_KEY"], "q": query, "image_type": "photo", "orientation": "vertical",
         "per_page": 20, "safesearch": "true", "min_height": 1600})
    res = json.loads(get(url))
    for h in res.get("hits", []):
        if h["id"] not in used:
            used.add(h["id"])
            return get(h["largeImageURL"]), f'Image : {h["user"]} / Pixabay ({h["pageURL"]})'
    raise RuntimeError(f"Aucune photo Pixabay pour « {query} »")


def openverse(query, used):
    """Sans clé. Images sous licence libre autorisant usage commercial + modification (on les recolore)."""
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(
        {"q": query, "aspect_ratio": "tall", "license_type": "commercial,modification", "size": "large"})
    res = json.loads(get(url))
    for r in res.get("results", []):
        if r["id"] in used or not r.get("url"):
            continue
        used.add(r["id"])
        try:
            data = get(r["url"])
        except Exception:
            continue
        lic = f'CC {r.get("license", "").upper()} {r.get("license_version") or ""}'.strip()
        return data, f'« {r.get("title") or "sans titre"} », {r.get("creator") or "auteur inconnu"}, {lic} ({r.get("foreign_landing_url")})'
    raise RuntimeError(f"Aucune image Openverse pour « {query} »")


def openai_image(prompt):
    body = json.dumps({"model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"),
                       "prompt": STYLE_IA + prompt, "size": "1024x1536"}).encode()
    req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return base64.b64decode(json.load(r)["data"][0]["b64_json"]), "Image générée par IA"


def main():
    load_env()
    path = sys.argv[1]
    ep = json.load(open(path, encoding="utf-8"))
    out = os.path.join("images", ep["id"])
    os.makedirs(out, exist_ok=True)
    credits, used = [], set()
    for i, sc in enumerate(ep["scenes"]):
        im = sc.get("image")
        if not im or (im.get("fichier") and os.path.exists(im["fichier"])):
            continue
        try:
            data = None
            if im.get("ia") and os.environ.get("OPENAI_API_KEY"):
                data, credit = openai_image(im["ia"])
            q = im.get("recherche") or im.get("ia")
            # ordre : Pixabay (clé gratuite) -> Pexels (si vous avez une clé) -> Openverse (sans clé)
            for name, fn, key in (("Pixabay", pixabay, "PIXABAY_API_KEY"), ("Pexels", pexels, "PEXELS_API_KEY"),
                                  ("Openverse", openverse, None)):
                if data or not q or (key and not os.environ.get(key)):
                    continue
                try:
                    data, credit = fn(q, used)
                except Exception as e:
                    print(f"Scène {i + 1} : {name} : {e}", file=sys.stderr)
            if not data:
                print(f"Scène {i + 1} : aucune image trouvée", file=sys.stderr)
                continue
        except Exception as e:                       # une image manquante ne bloque pas la vidéo
            print(f"Scène {i + 1} : {e}", file=sys.stderr)
            continue
        f = os.path.join(out, f"scene{i + 1:02d}.jpg")
        open(f, "wb").write(data)
        im["fichier"] = f
        credits.append(f"Scène {i + 1} : {credit}")
        print(f, "-", credit)
    open(os.path.join(out, "credits.txt"), "w", encoding="utf-8").write("\n".join(credits) + "\n")
    json.dump(ep, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
