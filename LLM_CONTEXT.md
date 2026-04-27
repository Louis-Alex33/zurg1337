# Contexte LLM - Prospect Machine

Ce fichier sert à transmettre rapidement le projet à un autre LLM.
À partager avec `README.md` et, si possible, les fichiers Python clés listés plus bas.

## Résumé du projet

Prospect Machine est un outil Python local de prospection SEO.

Objectif métier :

- trouver des domaines intéressants dans une niche ;
- qualifier les meilleurs candidats ;
- crawler les sites retenus ;
- produire un rapport client prudent, lisible et actionnable ;
- analyser éventuellement des exports Google Search Console.

Positionnement commercial :

- offre de type `SEO Refresh & Repair` ;
- audit rapide, prudent, utile en prospection ;
- pas de promesse SEO agressive ;
- priorité aux signaux compréhensibles par un client : contenu léger, pages à reprendre, dates visibles, maillage interne, overlap possible, titres/metas, indexation.

## Stack et contraintes

- Python 3.11+.
- Pas de framework web lourd.
- UI locale rendue côté serveur avec HTML/CSS dans le package `web_ui/`.
- Sorties locales en `CSV`, `JSON`, parfois `HTML`.
- Tests via `unittest`.
- Dépendances principales : `requests`, `beautifulsoup4`.

Commande UI :

```bash
python3 prospect_machine.py ui
```

URL locale par défaut :

```text
http://127.0.0.1:8787
```

Tests :

```bash
python3 -m unittest discover -s tests -v
```

## Architecture utile

Point d’entrée :

- `prospect_machine.py` : CLI unique, route vers les commandes `discover`, `qualify`, `audit`, `gsc`, `compare-audits`, `doctor`, `ui`.

Modules métier :

- `discover.py` : trouve ou importe des domaines.
- `qualify.py` : visite les homepages et score les domaines.
- `audit.py` : crawl, heuristiques SEO, génération des rapports JSON/HTML.
- `gsc.py` : analyse des exports Google Search Console.
- `scoring.py` : pondérations et fonctions de score.
- `models.py` : dataclasses partagées.
- `config.py` : constantes, budgets, modes, exclusions.
- `io_helpers.py` : lecture/écriture CSV/JSON.
- `audit_store.py` : index SQLite local des audits.
- `compare_audits.py` : comparaison de deux audits.

UI locale :

- `web_ui/server.py` : serveur HTTP local.
- `web_ui/jobs.py` : gestion des jobs lancés depuis l’UI.
- `web_ui/fs_ops.py` : opérations sur les fichiers générés.
- `web_ui/rendering.py` : rendu HTML des pages, rapports et vues fichiers.
- `web_ui/styles.py` : CSS global de l’UI.
- `web_ui/_render_helpers.py` : helpers de wording, labels, résumés et formatage.

Tests importants :

- `tests/test_web_ui.py` : rendu UI, jobs, pages de rapport.
- `tests/test_audit.py` et `tests/test_audit_tools.py` : crawl et heuristiques audit.
- `tests/test_qualify.py` : qualification de domaines.
- `tests/test_scoring.py` : scoring.
- `tests/test_gsc.py` : analyse GSC.

## Workflow produit

1. `discover`
   - Entrée : niches ou fichier de domaines.
   - Sortie : `data/domains_raw.csv`.

2. `qualify`
   - Entrée : `data/domains_raw.csv`.
   - Sorties : `data/domains_scored.csv`, `data/domains_scored.json`.

3. `audit`
   - Entrée : CSV scoré ou site direct.
   - Sorties : `reports/audits/<domain>.json`, `reports/audits/audit_summary.csv`.
   - Peut aussi produire une version HTML autonome avec `--html`.

4. `gsc`
   - Entrée : exports GSC pages et éventuellement queries.
   - Sorties : `reports/gsc_report.csv`, `.json`, `.html`.

## Rapport client

Le rapport client principal est généré depuis les JSON d’audit dans `web_ui/rendering.py`.

La page de rapport doit rester :

- claire pour un client non technique ;
- structurée comme un dashboard SEO ;
- prudente dans le wording ;
- orientée décision : quoi corriger, pourquoi, dans quel ordre ;
- exportable en PDF via le bouton d’impression navigateur.

Sections actuelles importantes :

- synthèse client ;
- score observé ;
- répartition des signaux ;
- signal principal ;
- premières pages à regarder ;
- décisions suggérées ;
- ce qui fonctionne déjà ;
- lecture du score ;
- plan d’action 30 / 60 / 90 jours ;
- matrice impact / effort ;
- pages à revoir en priorité ;
- opportunités éditoriales ;
- méthode et limites ;
- annexe technique.

## Règles de contribution pour un autre LLM

Respecter ces règles :

- Ne pas réécrire l’architecture sans raison forte.
- Préférer les patterns existants.
- Garder le projet léger : pas de gros framework.
- Garder le wording français, prudent et commercialement crédible.
- Ne pas transformer les signaux en certitudes SEO absolues.
- Ajouter ou ajuster les tests quand le rendu ou la logique change.
- Ne pas modifier les fichiers générés sauf demande explicite.
- Ne pas partager ou versionner les données client.

Avant une modification :

```bash
git status --short
```

Après une modification :

```bash
python3 -m unittest discover -s tests -v
```

## Fichiers à partager avec un autre LLM

Minimum utile :

```text
README.md
LLM_CONTEXT.md
prospect_machine.py
config.py
models.py
io_helpers.py
scoring.py
discover.py
qualify.py
audit.py
web_ui/
tests/
requirements.txt
```

Si le sujet concerne surtout l’UI du rapport :

```text
README.md
LLM_CONTEXT.md
web_ui/rendering.py
web_ui/styles.py
web_ui/_render_helpers.py
tests/test_web_ui.py
```

Si le sujet concerne le crawl ou les signaux SEO :

```text
README.md
LLM_CONTEXT.md
audit.py
config.py
models.py
tests/test_audit.py
tests/test_audit_tools.py
```

## Fichiers à éviter dans le partage

Ne pas partager si ce sont des données privées ou générées :

```text
.venv/
__pycache__/
.cache/
repo_git/
data/mes_sites.txt
data/domains_raw.csv
data/domains_scored.csv
data/domains_scored.json
reports/
reports/audits/audit_index.sqlite
```

## Prompt prêt à donner

```text
Tu vas analyser un projet Python local appelé Prospect Machine.

But du projet :
Trouver des sites, les qualifier, lancer un audit SEO léger ou complet, puis afficher un rapport client dans une UI locale.

Contexte :
- Python standard library majoritairement.
- Pas de framework web lourd.
- UI HTML/CSS rendue côté serveur dans web_ui/rendering.py.
- Styles dans web_ui/styles.py.
- Tests avec unittest.
- Commande UI : python3 prospect_machine.py ui.
- Tests : python3 -m unittest discover -s tests -v.

Objectif de tes réponses :
- Comprendre l’architecture avant de proposer des changements.
- Respecter les patterns existants.
- Garder un wording français, prudent et crédible.
- Ne pas surpromettre des résultats SEO.
- Prioriser les rapports client lisibles, actionnables et professionnels.
- Si tu modifies du code, indique les fichiers touchés et les tests à lancer.
```

