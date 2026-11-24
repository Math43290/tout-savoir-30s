#!/usr/bin/env python3
"""Fond musical rythmé + bruitages de coupe, générés (aucun droit d'auteur, aucun service payant).

Si un fichier musique/<nom>.mp3 existe et que l'épisode indique "musique": "<nom>", il est utilisé à la place.
"""
import wave

import numpy as np

SR = 44100


def _env(n, attack, decay):
    t = np.arange(n) / SR
    return np.minimum(1, t / max(attack, 1e-4)) * np.exp(-t / decay)


def _add(buf, x, at):
    i = int(at * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]


def kick():
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t / 0.035)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.12) * 0.95


def clap(rng):
    n = int(0.22 * SR)
    x = rng.standard_normal(n)
    x = np.convolve(x, np.ones(3) / 3, "same") - np.convolve(x, np.ones(25) / 25, "same")  # passe-haut grossier
    return x * _env(n, 0.001, 0.06) * 0.35


def hat(rng, open_=False):
    n = int((0.16 if open_ else 0.05) * SR)
    x = rng.standard_normal(n)
    x = x - np.convolve(x, np.ones(6) / 6, "same")
    return x * _env(n, 0.0005, 0.05 if open_ else 0.014) * 0.16


def bass(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(4 * np.pi * freq * t)
    return x * _env(n, 0.005, dur * 0.6) * 0.32


def pluck(freqs, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = sum(np.sign(np.sin(2 * np.pi * f * t)) * 0.3 + np.sin(2 * np.pi * f * t) for f in freqs)
    return x * _env(n, 0.004, 0.16) * 0.05


def whoosh(rng, dur=0.45):
    n = int(dur * SR)
    x = rng.standard_normal(n)
    k = np.linspace(40, 4, n).astype(int)
    out = np.empty(n)
    cs = np.cumsum(np.concatenate([[0], x]))
    for i in range(n):                       # filtre glissant : souffle qui se resserre
        a = max(0, i - k[i])
        out[i] = (cs[i + 1] - cs[a]) / (i + 1 - a)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    return out * env * 0.9


def boom():
    n = int(1.2 * SR)
    t = np.arange(n) / SR
    f = 38 + 60 * np.exp(-t / 0.08)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.003, 0.45) * 0.8


def make(total, cuts, path, bpm=124, seed=3):
    rng = np.random.default_rng(seed)
    n = int((total + 0.5) * SR)
    mus = np.zeros(n)
    fx = np.zeros(n)
    beat = 60 / bpm
    # la mineur : la – fa – do – sol
    roots = [55.0, 43.65, 65.41, 49.0]
    chords = [[220, 261.6, 329.6], [174.6, 220, 261.6], [261.6, 329.6, 392], [196, 246.9, 293.7]]
    K, C, Hc, Ho = kick(), clap(rng), hat(rng), hat(rng, True)
    b = 0
    while b * beat < total + 0.5:
        t = b * beat
        bar = (b // 4) % 4
        _add(mus, K, t)
        if b % 4 in (1, 3):
            _add(mus, C, t)
        _add(mus, Hc, t + beat / 2)
        if b % 8 == 7:
            _add(mus, Ho, t + beat / 2)
        _add(mus, bass(roots[bar], beat * 0.9), t)
        if b % 2 == 0:
            _add(mus, pluck(chords[bar], beat * 0.8), t + beat * 0.5)
        b += 1
    # entrée : 1 temps de musique filtrée puis tout part (le « drop » tombe sur l'accroche)
    W = whoosh(rng)
    for c in cuts:
        _add(fx, W * 0.35, max(0, c - 0.3))
    _add(fx, boom(), 0.0)
    # fin : fondu de 1 s
    f = int(1.0 * SR)
    end = int(total * SR)
    mus[max(0, end - f):end] *= np.linspace(1, 0, min(f, end))
    mus[end:] = 0
    mix = mus / (np.abs(mus).max() + 1e-9) * 0.9 + fx * 0.6
    mix = np.tanh(mix * 1.1) * 0.9
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return path


if __name__ == "__main__":
    import sys
    make(float(sys.argv[1]) if len(sys.argv) > 1 else 28, [2, 4, 6, 8], "out/test_music.wav")
