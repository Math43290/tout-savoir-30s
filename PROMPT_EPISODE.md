# ⚡ FORMAT PAR DÉFAUT : « Le saviez-vous » dynamique (v2)

Tous les nouveaux épisodes utilisent `"style": "dynamique"` (voir episodes/002-mammouths.json).

- **Sujet** : un fait *surprenant*, qui fait dire « attends, quoi ? ». Pas de cours scolaire. Bons filons : chronologies
  qui choquent (Cléopâtre plus proche de l'iPhone que des pyramides), animaux absurdes, records, idées reçues fausses.
- **Une thématique différente chaque jour**, jamais deux fois de suite la même : tourner entre Vin, Histoire,
  Animaux, Corps humain, Espace, Géographie, Cuisine, Sciences, Sport, Art (champ `categorie`).
- **Phrase 1 = l'accroche** : le fait le plus fou en une phrase, tout de suite. Jamais d'introduction.
- **Thème favori : le vin** (cépages, bouteilles, régions, records). Rythme posé : `"calme": true`, 1 ou 2 plans par
  scène (une photo toutes les ~4–5 s).
- **Format long (par défaut)** : une histoire racontée comme un récit (tension, rebondissement,
  chute), 9–11 scènes, 160–180 mots (~1 min), `"vitesse": 1.0`, `"expressivite": 0.35`, `"volume_musique": 0.16`,
  3 ou 4 plans par scène.
- Format court (si demandé) : 5 à 6 scènes, 60–70 mots, **420 caractères maximum**, dernière scène : « Abonne-toi : un fait fou chaque jour. »
- Chaque scène a 2 ou 3 `plans` (une photo toutes les ~2 s) : `{"recherche": "mots-clés anglais concrets"}`,
  sujet visible et photogénique (pas d'abstrait). Option `"at": "mot"` pour couper sur un mot précis.
- Option `"gros": {"texte": "-4 000 ANS", "at": "quatre"}` : tampon géant (chiffre ou 2 mots max) sur le mot-clé.
- Pas de bloc `elements`, pas d'`image` : ce sont des champs de l'ancien format.
- Chaque fait est vérifié avec une source fiable listée dans `sources`.

---

# Prompt de génération d'un épisode (à coller dans le nœud Claude de n8n)

Tu écris un épisode de la série TikTok « Tout savoir en 30 s ».
Sujet : {{sujet}} — Catégorie : {{categorie}} — Numéro : {{numero}}

Règles d'écriture :
- 60 à 70 mots et 420 caractères maximum de voix off au total (pour tenir en 30 secondes), tutoiement, phrases courtes, à l'oral.
- Scène 1 = accroche surprenante en moins de 10 mots. Elle doit donner envie de rester.
- 4 à 6 scènes. Chaque scène porte une seule idée.
- Dernière scène : « Abonne-toi, et dis-moi en commentaire le prochain sujet. »
- Uniquement des faits vérifiables. Donne en plus, dans "sources", 1 à 3 URL fiables.
  Si un chiffre varie selon les sources, prends la valeur prudente.
- Les nombres de la voix off s'écrivent en lettres (« quinze centimètres »), ceux des titres en chiffres.
- Titre de scène : 2 à 6 mots. Mets entre *astérisques* le mot clé à mettre en doré.
- Le champ "at" d'un élément = un mot exact de la voix off de la même scène.
  C'est à ce mot que l'élément apparaît.

- Chaque scène a une image de fond : "image": {"recherche": "3 à 5 mots EN ANGLAIS pour une banque photo", "mouvement": "zoom_in|zoom_out|pan_left|pan_right|pan_up"}.
  Choisis des images concrètes et photogéniques (un lieu, un objet, une matière), pas des concepts abstraits.
  Si aucune photo réelle ne peut exister (passé lointain, vue microscopique…), écris "ia": "description en anglais" à la place de "recherche".

Blocs visuels disponibles (un bloc principal par scène au plus, le titre en plus) :
- tag (scène 1) : {"type":"tag","text":"N°09 · SCIENCES"}
- title : {"type":"title","text":"Le mot *doré*"}
- chiffre : {"type":"chiffre","valeur":"21 196","unite":"kilomètres","texte":"légende courte","at":"mot"}
- comparaison : {"type":"comparaison","a":{"nom":"Rouge","valeur":1,"texte":"×1"},"b":{"nom":"Bleu","valeur":5,"texte":"×5"},"at":"mot"}
- liste : {"type":"liste","items":[{"texte":"Étape courte","at":"mot"}, …]}  (3 items max, 18 caractères max)
- vraifaux : {"type":"vraifaux","affirmation":"… *mot clé*","reponse":"Vrai|Faux","at_reponse":"mot"}
- equation : {"type":"equation","lines":[{"text":"0,012 mm","at":"mot"}],"result":"10,8","unit":"cm","result_at":"mot"}
- outro (dernière scène, toujours identique)
Quand un bloc occupe la scène, ajoute "flou": 6 à 10 et "opacite": 0.45 à 0.55 à l'image.
N'utilise aucun autre type.

Réponds uniquement avec le JSON, au format de `episodes/001-tour-eiffel.json` :
{ "id", "numero", "categorie", "legende", "hashtags", "sources", "scenes": [ { "vo", "elements": [...] } ] }
