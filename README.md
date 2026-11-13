# Veille offres startup — Founder Associate / Chief of Staff / BizOps

Scanne deux fois par jour les offres en startup qui collent à mon profil, **en freelance ~3,5 j/sem ou en stage alterné, janvier → juin 2027**, à Paris/IDF ou en full remote, les note de 0 à 100 et les affiche sur un dashboard.

## Sources
| Source | Méthode | Ce qu'elle couvre |
|---|---|---|
| Welcome to the Jungle | index Algolia public du site | l'essentiel des startups FR (stages, freelance, alternance) |
| LinkedIn | API "guest" publique (sans compte) | filtres stage / temps partiel / contrat / temporaire, Paris + remote France |
| Lever / Greenhouse / Ashby | API publiques des pages carrières | startups ciblées listées dans `config.yaml` |
| RSS | n'importe quel flux | ex. alertes Google en mode « Flux RSS » |

## Scoring (tout se règle dans `config.yaml`)
- **+40** intitulé cible (founder/CEO associate, CEO office, chief of staff, bras droit, BizOps, strategy & ops…), **+20** intitulé proche (stratégie, ops, chargé de mission, corp dev…)
- **+15 à +20** format compatible : stage, freelance, temps partiel / « 3 jours par semaine » (+5 alternance)
- **+10** démarrage janvier 2027 / début 2027 / ASAP · **−10** démarrage été/automne 2027
- **+5 par mot-clé profil** (veille, études de marché, automatisation, IA, levée de fonds, conseil…), plafonné à +20
- **−60** hors cible (dev, sales SDR, design, compta…) · **−40** poste senior · **−25** CDI temps plein uniquement
- Seules les offres ≥ `min_score` (25) sont gardées ; le dashboard filtre par défaut à 35.

## Mise en place (5 min)
1. Crée un repo GitHub **privé** (ex. `startup-offers-monitor`) et pousse ce dossier :
   ```bash
   cd startup-offers-monitor
   git init && git add . && git commit -m "init veille startup"
   git branch -M main
   git remote add origin https://github.com/<toi>/startup-offers-monitor.git
   git push -u origin main
   ```
2. **Settings → Actions → General → Workflow permissions** : coche *Read and write permissions*.
3. **Actions → Veille offres startup → Run workflow** pour lancer un premier passage.
4. Dashboard :
   - en local : `git pull` puis ouvre `docs/index.html` ;
   - ou en ligne : **Settings → Pages → Deploy from branch → `main` / `docs`** (sur un repo privé, Pages demande un compte GitHub Pro — sinon reste en local).
5. *(Optionnel)* notifs Telegram pour les offres ≥ 55 : ajoute les secrets `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID` (le même bot que ton ancien tracker marche).

## Utiliser le dashboard
- Filtres : texte, source, format (stage / freelance / temps partiel), score mini, nouvelles des 3 derniers jours.
- Statut par offre (À voir / Intéressant / Postulé / Écarté) : sauvegardé dans ton navigateur. **Exporter statuts** pour le garder ou le passer d'un appareil à l'autre.
- Une offre plus vue depuis 14 jours est marquée « probablement expirée » et masquée par défaut.

## Ajuster
- Ajouter une startup : `ats.lever` / `ats.greenhouse` / `ats.ashby` dans `config.yaml` (le slug est dans l'URL de sa page carrières). Si le slug est faux, le log le signale, rien ne casse.
- Ajouter une requête : liste `queries`.
- Tester sans réseau : `python -m monitor.run --fixtures tests/fixtures`.
- Lancer une seule source : `python -m monitor.run --sources wttj`.

## Limites
- LinkedIn bride parfois les runners GitHub (codes 429/999) : le log l'indique et le passage suivant rattrape.
- LinkedIn ne donne que l'intitulé (pas la description) → score plus prudent que pour WTTJ.
- JobTeaser (ESSEC) et Indeed demandent une connexion ou bloquent les robots : non couverts.
