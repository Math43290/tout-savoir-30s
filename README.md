# Tout savoir en 30 s

Une vidéo TikTok + Instagram par jour, fabriquée et publiée automatiquement. Coût : 0 €.

## Le circuit
1. **Chaque semaine**, Claude écrit et vérifie 7 épisodes, puis les dépose dans `episodes/`.
2. **Chaque matin vers 6 h**, GitHub fabrique la vidéo du jour (workflow « Fabrication ») :
   photos Pixabay → voix ElevenLabs → montage → mise en ligne sur GitHub Pages.
3. **Vous recevez une notification GitHub** (ticket « À valider ») avec la vidéo.
   Répondez `/valider` ou `/refaire`, depuis l'app GitHub sur votre téléphone par exemple.
4. **`/valider`** : Buffer la programme sur TikTok + Instagram à 18 h 30.

## Réglages (une seule fois, dans Settings du dépôt)
- **Secrets** (Settings → Secrets and variables → Actions → *Secrets*) :
  `PIXABAY_API_KEY`, `ELEVENLABS_API_KEY`, `BUFFER_API_KEY`
- **Variable** (facultative) : `ELEVENLABS_VOICE_ID`. Sans elle, la voix « Hugo - Serious and Professional » est retrouvée automatiquement
- **Pages** (Settings → Pages) : *Deploy from a branch* → `videos` / `(root)`

## Les fichiers
| Fichier | Rôle |
|---|---|
| `episodes/*.json` | Un épisode = voix off par scène, image de fond, blocs visuels, légende, sources, statut |
| `fetch_images.py` | Photos de fond (Pixabay, sinon Openverse sans clé) |
| `voice.py` | Voix ElevenLabs + instant de chaque mot |
| `align_audio.py` | Cale un MP3 téléchargé à la main depuis le site ElevenLabs |
| `render.py` | Montage 1080×1920 (titres, sous-titres, blocs animés, compte à rebours) |
| `publish_buffer.py` | Programmation TikTok + Instagram via l'API gratuite de Buffer |
| `pipeline.py` | File d'attente : `python3 pipeline.py etat` |
| `PROMPT_EPISODE.md` | Règles d'écriture et catalogue des blocs visuels |
