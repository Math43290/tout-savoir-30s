#!/usr/bin/env python3
"""Avance une publication déjà programmée : supprime le post Buffer en attente de l'épisode, puis le republie tout de suite.

    python3 buffer_maintenant.py episodes/009-xxx.json --url https://.../009-xxx.mp4
"""
import argparse, json, subprocess, sys, datetime as dt
from publish_buffer import gql, channels
from voice import load_env


def mutations():
    t = gql('query { __schema { mutationType { fields { name args { name type { name ofType { name } } } } } } }')
    return {f["name"]: f for f in t["__schema"]["mutationType"]["fields"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode"); ap.add_argument("--url", required=True)
    a = ap.parse_args()
    load_env()
    ep = json.load(open(a.episode, encoding="utf-8"))
    debut = ep["legende"].strip()[:40]
    muts = mutations()
    print("Mutations post :", [m for m in muts if "ost" in m])
    orgs = gql("query { account { organizations { id } } }")["account"]["organizations"]
    tiktok = [c["id"] for c in channels() if c["service"] == "tiktok"]
    supprimes = 0
    for o in orgs:
        q = '''query($o: OrganizationId!, $c: [ChannelId!]) { posts(input: {organizationId: $o,
               filter: {status: [scheduled], channelIds: $c}}) { edges { node { id text dueAt } } } }'''
        try:
            edges = gql(q, {"o": o["id"], "c": tiktok})["posts"]["edges"]
        except RuntimeError as e:
            print("Liste des posts impossible :", e); sys.exit(1)
        for e in edges:
            n = e["node"]
            print("Programmé :", n["id"], n["dueAt"], n["text"][:50].replace("\n", " "))
            if n["text"].strip().startswith(debut):
                arg = muts["deletePost"]["args"][0]
                r = gql('mutation($i: %s!) { deletePost(%s: $i) { __typename } }' %
                        (arg["type"]["name"] or arg["type"]["ofType"]["name"], arg["name"]),
                        {"i": {"id": n["id"]} if arg["name"] == "input" else n["id"]})
                print("Supprimé :", n["id"], r); supprimes += 1
    if not supprimes:
        print("Aucun post programmé trouvé pour cet épisode : rien n'est republié."); sys.exit(1)
    quand = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    subprocess.run([sys.executable, "publish_buffer.py", a.episode, "--url", a.url, "--le", quand], check=True)


if __name__ == "__main__":
    main()
