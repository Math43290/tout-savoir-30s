#!/usr/bin/env python3
"""Cale le texte d'un épisode sur un MP3 téléchargé depuis le site ElevenLabs (sans timestamps).
Repère les pauses (ffmpeg silencedetect), aligne chaque groupe de mots ponctué sur une pause,
puis répartit les mots dans chaque groupe selon leur longueur. Produit timings.json comme voice.py.
    python3 align_audio.py episodes/001-tour-eiffel.json voice/001-tour-eiffel/audio.mp3
"""
import json, os, re, subprocess, sys

def silences(mp3):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", mp3, "-af", "silencedetect=noise=-38dB:d=0.1",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    st = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", err)]
    en = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", err)]
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp3],
                               capture_output=True, text=True).stdout)
    return list(zip(st, en)), dur

def main():
    ep = json.load(open(sys.argv[1], encoding="utf-8")); mp3 = sys.argv[2]
    sil, dur = silences(mp3)
    sil = [(a, b) for a, b in sil if a > 0.05 and b < dur - 0.05]
    # segments de parole
    segs, t = [], 0.0
    for a, b in sil:
        segs.append((t, a)); t = b
    segs.append((t, dur))
    # groupes de mots (coupés à la ponctuation), avec n° de scène
    words = []
    for si, sc in enumerate(ep["scenes"]):
        for w in sc["vo"].split():
            words.append({"word": w, "scene": si})
    # Chaque segment de parole reçoit un bloc de mots contigu. Coût : écart entre la durée du
    # segment et la durée attendue au débit moyen, + pénalité si la pause tombe hors ponctuation.
    N, S = len(words), len(segs)
    wl = [max(1, len(re.findall(r"[aeiouyàâäéèêëîïôöûùü]+", w["word"].lower()))) + 0.4 for w in words]  # ~syllabes
    speech = sum(b - a for a, b in segs); rate = sum(wl) / speech
    punct = [bool(re.search(r"[.,:!?]$", w["word"])) for w in words]
    INF = float("inf")
    f = [[INF] * (N + 1) for _ in range(S + 1)]; back = [[0] * (N + 1) for _ in range(S + 1)]
    f[0][0] = 0
    for j in range(1, S + 1):
        d = segs[j - 1][1] - segs[j - 1][0]
        for i in range(j, N + 1):
            for k in range(j - 1, i):
                if f[j - 1][k] == INF: continue
                c = f[j - 1][k] + (d - sum(wl[k:i]) / rate) ** 2
                if i < N and not punct[i - 1]: c += 0.25          # pause hors ponctuation : possible mais rare
                c += sum(0.6 if re.search(r"[.!?:]$", words[x]["word"]) else 0.03
                         for x in range(k, i - 1) if punct[x])       # fin de phrase sans pause : très improbable
                if c < f[j][i]: f[j][i], back[j][i] = c, k
    blocks, i = [], N
    for j in range(S, 0, -1):
        k = back[j][i]; blocks.append((k, i)); i = k
    blocks.reverse()
    for (k, i), (a, b) in zip(blocks, segs):
        tw = sum(wl[k:i]); t = a
        for x in range(k, i):
            dd = wl[x] / tw * (b - a)
            words[x]["start"], words[x]["end"] = round(t, 3), round(t + dd - 0.02, 3); t += dd
        print(f"{a:6.2f}-{b:6.2f}  {' '.join(w['word'] for w in words[k:i])}")
    # scènes
    n = len(ep["scenes"]); starts = []
    for si in range(n):
        first = next(w for w in words if w["scene"] == si)
        starts.append(0.0 if si == 0 else max(0.0, first["start"] - 0.15))
    scenes = []
    for si in range(n):
        s0 = starts[si]; s1 = starts[si + 1] if si + 1 < n else dur
        scenes.append({"duration": round(s1 - s0, 3), "words": [
            {"word": w["word"], "start": round(w["start"] - s0, 3), "end": round(w["end"] - s0, 3)}
            for w in words if w["scene"] == si]})
    out = os.path.join(os.path.dirname(mp3), "timings.json")
    json.dump({"scenes": scenes}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(out)

if __name__ == "__main__":
    main()
