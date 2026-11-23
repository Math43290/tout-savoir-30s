#!/usr/bin/env python3
"""Génère la voix off d'un épisode avec ElevenLabs + les timings mot à mot.

Usage :
    # clés dans le fichier .env (voir .env.exemple), jamais dans le code
    python3 voice.py --voix                              # liste vos voix et leurs identifiants
    python3 voice.py episodes/001-tour-eiffel.json

Produit voice/<id>/audio.mp3 et voice/<id>/timings.json,
puis : python3 render.py episodes/<id>.json --voice voice/<id>

Une seule requête pour tout l'épisode (intonation continue) ; les mots sont
ensuite répartis par scène grâce à l'alignement caractère par caractère.
Uniquement la bibliothèque standard Python : tourne aussi dans n8n (Execute Command).
"""
import base64, json, os, sys, urllib.request

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128"


def words_from_alignment(text, al):
    chars, st, en = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    words, cur, ws, we = [], "", None, None
    for ch, s, e in zip(chars, st, en):
        if ch.isspace():
            if cur:
                words.append({"word": cur, "start": ws, "end": we})
            cur, ws = "", None
            continue
        if ws is None:
            ws = s
        cur += ch
        we = e
    if cur:
        words.append({"word": cur, "start": ws, "end": we})
    return words


def load_env(path=".env"):
    """Lit les clés depuis un fichier .env (KEY=valeur) pour ne jamais les écrire dans le code."""
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def list_voices():
    req = urllib.request.Request("https://api.elevenlabs.io/v1/voices",
                                 headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as r:
        for v in json.load(r)["voices"]:
            lab = v.get("labels") or {}
            print(f'{v["voice_id"]}  {v["name"]:<28} {lab.get("gender", "")} {lab.get("accent", "")} {lab.get("language", "")}')


def main():
    load_env()
    if sys.argv[1] == "--voix":
        return list_voices()
    ep_path = sys.argv[1]
    ep = json.load(open(ep_path, encoding="utf-8"))
    key = os.environ["ELEVENLABS_API_KEY"]
    voice = os.environ.get("ELEVENLABS_VOICE_ID") or ep.get("voice_id")
    if not voice:
        sys.exit("Renseigner ELEVENLABS_VOICE_ID")
    vos = [s["vo"].strip() for s in ep["scenes"]]
    text = " ".join(vos)
    body = json.dumps({
        "text": text,
        "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "speed": 1.05},
    }).encode()
    req = urllib.request.Request(API.format(voice=voice), data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)

    out = os.path.join("voice", ep["id"])
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, "audio.mp3"), "wb").write(base64.b64decode(data["audio_base64"]))

    words = words_from_alignment(text, data["alignment"])
    counts = [len(v.split()) for v in vos]
    if sum(counts) != len(words):
        print(f"Attention : {len(words)} mots alignés pour {sum(counts)} attendus", file=sys.stderr)
    audio_end = words[-1]["end"] + 0.3
    scenes, i = [], 0
    starts = []
    for n in counts:
        starts.append(max(0.0, words[i]["start"] - 0.12))
        i += n
    i = 0
    for k, n in enumerate(counts):
        s0 = 0.0 if k == 0 else starts[k]
        s1 = starts[k + 1] if k + 1 < len(counts) else audio_end
        ws = [{"word": w["word"], "start": round(w["start"] - s0, 3), "end": round(w["end"] - s0, 3)}
              for w in words[i:i + n]]
        scenes.append({"duration": round(s1 - s0, 3), "words": ws})
        i += n
    json.dump({"scenes": scenes}, open(os.path.join(out, "timings.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(out)


if __name__ == "__main__":
    main()
