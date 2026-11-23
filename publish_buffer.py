#!/usr/bin/env python3
"""Programme un épisode sur TikTok (et Instagram si RESEAUX=tiktok,instagram) via l'API gratuite de Buffer.

    python3 publish_buffer.py episodes/002-xxx.json --url https://.../002-xxx.mp4 [--le 2026-11-25T17:30:00Z] [--test]

La vidéo doit être à une URL publique directe (GitHub Pages convient).
Clé lue dans .env ou l'environnement : BUFFER_API_KEY (publish.buffer.com/settings/api).
Uniquement la bibliothèque standard Python.
"""
import argparse, json, os, sys, urllib.error, urllib.request

from voice import load_env

API = "https://api.buffer.com"
MUTATION = """mutation($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}"""


def gql(query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    key = os.environ["BUFFER_API_KEY"].strip()          # un copier-coller ajoute parfois un saut de ligne
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {key}", "User-Agent": "tout-savoir-30s"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Buffer a répondu {e.code} : {e.read().decode(errors='replace')[:500]}")
    if res.get("errors"):
        raise RuntimeError(json.dumps(res["errors"], ensure_ascii=False))
    return res["data"]


def channels():
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    out = []
    for o in orgs:
        q = 'query($o: OrganizationId!) { channels(input: {organizationId: $o}) { id name service isQueuePaused } }'
        out += gql(q, {"o": o["id"]})["channels"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--url", required=True, help="URL publique directe de la vidéo")
    ap.add_argument("--le", help="date UTC ISO (ex. 2026-11-25T17:30:00Z) ; sinon prochain créneau de la file Buffer")
    ap.add_argument("--reseaux", default=os.environ.get("RESEAUX", "tiktok"))
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()
    load_env()
    ep = json.load(open(a.episode, encoding="utf-8"))
    caption = ep["legende"].strip() + "\n\n" + " ".join(ep.get("hashtags", []))
    wanted = [s.strip() for s in a.reseaux.split(",")]

    chans = [c for c in channels() if c["service"] in wanted] if not a.test else \
        [{"id": "TEST_" + s, "service": s, "name": s} for s in wanted]
    if not chans:
        sys.exit(f"Aucun compte {a.reseaux} trouvé dans Buffer : connectez-le sur publish.buffer.com")
    ok = True
    for c in chans:
        meta = {"instagram": {"type": "reel", "shouldShareToFeed": True, "isAiGenerated": True}} \
            if c["service"] == "instagram" else {"tiktok": {"isAiGenerated": True}}
        inp = {"channelId": c["id"], "text": caption, "schedulingType": "automatic",
               "mode": "customScheduled" if a.le else "addToQueue", "needsApproval": False,
               "assets": [{"video": {"url": a.url, "metadata": {"thumbnailOffset": 1500}}}],
               "metadata": meta, "source": "tout-savoir-30s"}
        if a.le:
            inp["dueAt"] = a.le
        if a.test:
            print(json.dumps(inp, ensure_ascii=False, indent=1))
            continue
        res = gql(MUTATION, {"input": inp})["createPost"]
        print(json.dumps(res, ensure_ascii=False), file=sys.stderr)
        if "message" in res:
            ok = False
            print(f"{c['service']} : ÉCHEC — {res['message']}", file=sys.stderr)
        else:
            print(f"{c['service']} : programmé ({res['post']['dueAt']})")
    if not chans or not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
