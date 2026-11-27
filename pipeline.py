#!/usr/bin/env python3
"""Petit registre des épisodes (champ "statut" dans chaque episodes/*.json).

    python3 pipeline.py suivant                 -> chemin du prochain épisode à fabriquer (vide si rien)
    python3 pipeline.py statut <id> <statut> [clé=valeur ...]
    python3 pipeline.py prochain-creneau [maintenant] -> prochaine publication à 21 h (heure de Paris), en UTC ISO
    python3 pipeline.py etat                    -> tableau récapitulatif

Statuts : à faire -> à valider -> validé/publié ; « à refaire » repasse en tête de file.
"""
import datetime as dt, glob, json, os, sys
from zoneinfo import ZoneInfo

MAX_EN_ATTENTE = 5          # pas plus de 3 vidéos en attente de validation
HEURE_PUBLICATION = (21, 0)     # tous les soirs à 21 h (heure de Paris)


def episodes():
    for p in sorted(glob.glob("episodes/*.json")):
        ep = json.load(open(p, encoding="utf-8"))
        yield p, ep


def save(p, ep):
    json.dump(ep, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(p, "a").write("\n")


def suivant():
    eps = list(episodes())
    for p, e in eps:                    # une vidéo à refaire (demandée à la main) passe toujours
        if e.get("statut") == "à refaire":
            return p
    if sum(1 for _, e in eps if e.get("statut") == "à valider") >= MAX_EN_ATTENTE:
        return ""
    for wanted in ("à refaire", "à faire"):
        for p, e in eps:
            if e.get("statut", "à faire") == wanted:
                return p
    return ""


def prochain_creneau(maintenant=False):
    paris = ZoneInfo("Europe/Paris")
    now = dt.datetime.now(paris)
    if maintenant:                      # « /valider maintenant » : dans 3 minutes
        return (now + dt.timedelta(minutes=3)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    t = now.replace(hour=HEURE_PUBLICATION[0], minute=HEURE_PUBLICATION[1], second=0, microsecond=0)
    if t < now + dt.timedelta(minutes=20):
        t += dt.timedelta(days=1)
    # une seule vidéo par soir : on saute les soirs déjà programmés
    pris = {e.get("programme_le", "")[:10] for _, e in episodes() if e.get("programme_le")}
    while t.astimezone(dt.timezone.utc).strftime("%Y-%m-%d") in pris:
        t += dt.timedelta(days=1)
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def main():
    cmd = sys.argv[1]
    if cmd == "suivant":
        print(suivant())
    elif cmd == "prochain-creneau":
        print(prochain_creneau(len(sys.argv) > 2 and sys.argv[2] == "maintenant"))
    elif cmd == "statut":
        ident, statut = sys.argv[2], sys.argv[3]
        p = f"episodes/{ident}.json"
        ep = json.load(open(p, encoding="utf-8"))
        ep["statut"] = statut
        for kv in sys.argv[4:]:
            k, v = kv.split("=", 1)
            ep[k] = v
        save(p, ep)
    elif cmd == "etat":
        for p, e in episodes():
            print(f'{e["id"]:<32} {e.get("statut", "à faire"):<10} {e.get("titre", "")}')


if __name__ == "__main__":
    main()
