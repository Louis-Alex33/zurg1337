# Prospect Machine

Prospect Machine est un toolkit Python simple pour la prospection SEO.

Son objectif est de t'aider a:

- trouver des domaines pertinents
- qualifier rapidement les meilleurs candidats
- sortir un mini audit exploitable en prospection
- analyser des exports Google Search Console
- piloter tout ca soit en CLI, soit via une UI web locale

Le projet reste volontairement leger:

- une seule entree CLI: `python3 prospect_machine.py ...`
- pas de framework lourd
- sorties locales en `CSV` et `JSON`
- architecture lisible et testable
- wording prudent, pense pour une offre commerciale de type "SEO Refresh & Repair"

## Commandes de base

Si tu veux juste demarrer un serveur, utilise ces commandes:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 prospect_machine.py ui
```

Puis ouvre l'UI dans ton navigateur:

```text
http://127.0.0.1:8787
```

Important:

- si tu modifies le code Python, les providers ou l'UI, redemarre le serveur avec `Ctrl+C` puis `python3 prospect_machine.py ui`
- sinon ton navigateur peut continuer a parler a une ancienne version chargee en memoire

Pour arreter le serveur UI:

- retourne dans le terminal ou il tourne
- fais `Ctrl+C`

Pour sortir de l'environnement virtuel:

```bash
deactivate
```

## Ce que fait chaque module

### `discover`

Cherche des domaines a partir de niches ou importe une liste manuelle.

Usage typique:

- "je veux une liste brute de sites a analyser"
- "j'ai deja une liste de domaines, je veux la faire entrer dans le pipeline"

Sortie principale:

- `data/domains_raw.csv`

### `qualify`

Visite les homepages, collecte quelques signaux simples, puis attribue un score de priorisation.

La V2 cherche mieux les sites qui ressemblent a:

- des sites editoriaux / medias / blogs / affiliates

et sous-note fortement les profils:

- app-like
- docs-heavy
- marketplace-heavy

Sorties principales:

- `data/domains_scored.csv`
- `data/domains_scored.json`

### `audit`

Lance un crawl BFS simple sur les meilleurs domaines et produit un rapport d'audit prudent, utile pour la prospection.

Le rapport insiste davantage sur les signaux business:

- thin content
- duplicate titles
- duplicate meta descriptions
- contenu date
- maillage interne faible
- pages profondes
- overlap de contenu possible

Sorties principales:

- `reports/audits/<domain>.json`
- `reports/audits/audit_summary.csv`

### `gsc`

Analyse des exports GSC pages + queries.

Le module reste prudent dans son wording:

- pas de promesse agressive
- pas de "cannibalisation certaine"
- priorisation exploitable commercialement

Sorties possibles:

- `reports/gsc_report.csv`
- `reports/gsc_report.json`
- `reports/gsc_report.html`

### `ui`

Lance une interface web locale pour piloter les jobs sans tout faire au terminal.

Important:

- l'UI locale ne se recharge pas toute seule quand le code change
- apres une modification du projet, relance toujours `python3 prospect_machine.py ui`

## Structure du projet

```text
.
|- prospect_machine.py
|- discover.py
|- qualify.py
|- audit.py
|- gsc.py
|- scoring.py
|- web_ui.py
|- web_ui/
|  |- __init__.py
|  |- server.py
|  |- jobs.py
|  |- fs_ops.py
|  |- rendering.py
|  `- styles.py
|- utils.py
|- io_helpers.py
|- models.py
|- config.py
|- data/
|- reports/
`- tests/
```

## Prerequis

- Python 3.11+

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependances:

- `requests`
- `beautifulsoup4`

## Demarrage rapide

Si tu veux tester tout le pipeline rapidement:

```bash
python3 prospect_machine.py discover --niches "padel,yoga,velo" --limit 50
python3 prospect_machine.py qualify data/domains_raw.csv
python3 prospect_machine.py audit data/domains_scored.csv --min-score 50 --top 3 --max-pages 30
```

Tu recupereras ensuite:

- `data/domains_raw.csv`
- `data/domains_scored.csv`
- `data/domains_scored.json`
- `reports/audits/audit_summary.csv`
- un JSON d'audit par domaine dans `reports/audits/`

## Workflow recommande

### 1. Trouver des domaines

Recherche a partir de niches:

```bash
python3 prospect_machine.py discover \
  --niches "padel,yoga,velo" \
  --limit 100 \
  --output data/domains_raw.csv
```

Pour une requete avancee de type moteur de recherche, garde-la telle quelle avec `--query-mode exact`:

```bash
python3 prospect_machine.py discover \
  --niches 'site:.fr "CPF" "blog" "guides" intitle:CPF inbody:CPF' \
  --query-mode exact \
  --limit 50 \
  --output data/domains_raw.csv
```

Si tu testes ce genre de changement depuis l'UI:

- pense a redemarrer le serveur UI apres une mise a jour du code
- puis recharge la page avant de relancer le job

Import depuis un fichier texte:

```bash
python3 prospect_machine.py discover \
  --domains-file data/mes_sites.txt \
  --output data/domains_raw.csv
```

Le fichier d'entree `data/mes_sites.txt` peut contenir:

- un domaine par ligne
- ou une URL par ligne

### 2. Qualifier les domaines

Mode frugal par defaut:

```bash
python3 prospect_machine.py qualify \
  data/domains_raw.csv \
  --output data/domains_scored.csv \
  --json data/domains_scored.json
```

Mode plus complet:

```bash
python3 prospect_machine.py qualify data/domains_raw.csv --mode qualify_full
```

Important:

- `qualify_fast` est le mode par defaut
- homepage only ou presque, avec budgets machine serres
- sitemap limite ou desactive selon le mode
- l'objectif est de rester rapide et previsible sur laptop

Le scoring de qualification tient compte notamment de:

- taille estimee du site
- presence de blog / guides / articles
- CMS detecte
- contenu date
- contact / signaux sociaux
- type de site detecte

Champs utiles dans les sorties V2:

- `score`
- `is_editorial_candidate`
- `is_app_like`
- `is_docs_like`
- `is_marketplace_like`
- `refresh_repair_fit`
- `site_type_note`
- `nav_link_ratio`
- `content_link_ratio`
- `editorial_word_count`

Lecture rapide:

- `good_fit`: bon candidat probable pour une offre Refresh & Repair
- `mixed_fit`: candidature a verifier
- `review_fit`: signaux mitiges
- `low_fit`: mauvais candidat probable pour cette offre

### 3. Auditer les meilleurs domaines

Audit leger par defaut:

```bash
python3 prospect_machine.py audit \
  data/domains_scored.csv \
  --top 20 \
  --output-dir reports/audits
```

Audit filtre par score:

```bash
python3 prospect_machine.py audit \
  data/domains_scored.csv \
  --min-score 60 \
  --output-dir reports/audits
```

Triage rapide pour la prospection:

```bash
python3 prospect_machine.py audit \
  data/domains_scored.csv \
  --min-score 50 \
  --top 3 \
  --max-pages 30 \
  --delay 0.2 \
  --output-dir reports/audits
```

Audit plus complet sur peu de domaines:

```bash
python3 prospect_machine.py audit \
  data/domains_scored.csv \
  --mode audit_full \
  --top 2 \
  --output-dir reports/audits
```

Audit direct d'un seul site:

```bash
python3 prospect_machine.py audit --site example.com --max-pages 80
```

Audit direct avec crawl mixte home + sitemap et rapport HTML autonome:

```bash
python3 prospect_machine.py audit \
  --site example.com \
  --crawl-source mixed \
  --max-pages 80 \
  --html reports/audits/example.html
```

Comparer deux audits d'un meme site:

```bash
python3 prospect_machine.py compare-audits \
  reports/audits/example.com/2026-04-20T10-00-00.json \
  reports/audits/example.com/2026-04-26T10-00-00.json \
  --output reports/audits/example_delta.csv
```

Ce que l'audit produit dans la V2:

- un `observed_health_score` borne entre `0` et `100`
- un `page_health_score` pour chaque page analysee
- un `page_type` indicatif: homepage, article, product, service, taxonomy, legal, etc.
- des `critical_findings` prudents
- des `business_priority_signals`
- des `technical_checks`: noindex, canonical, robots.txt, redirections, ancres generiques
- des `internal_linking_opportunities`
- une liste `top_pages_to_rework`
- des `confidence_notes`
- une copie datee dans `reports/audits/<domain>/<timestamp>.json`
- un index local SQLite dans `reports/audits/audit_index.sqlite`

Important:

- le crawl reste volontairement simple
- `audit_light` est le mode par defaut
- `--crawl-source mixed` est le defaut: il part de la homepage et du sitemap quand il existe
- `--crawl-source home` part seulement de la homepage, `sitemap` part seulement des URLs sitemap
- `robots.txt` est verifie par defaut; utilise `--skip-robots` seulement pour un test local ponctuel
- `--cache` active un cache HTTP local utile quand tu relances souvent le meme audit
- le systeme prefere un audit incomplet mais rapide a un crawl trop couteux
- le crawl applique des budgets de pages, profondeur, requetes, liens et temps par domaine
- les pages HTML trop lourdes sont ignorees plutot que parsees integralement
- le rapport est base sur le crawl observe uniquement
- les pages "orphelines" sont estimees a partir du maillage observe
- l'overlap de contenu est borne et peut etre coupe en mode light
- les signaux d'UI repetitifs sont davantage ignores

### 4. Analyser des exports GSC

Exemple complet:

```bash
python3 prospect_machine.py gsc \
  exports/pages_recent.csv \
  exports/pages_old.csv \
  -q exports/queries.csv \
  --html reports/client.html \
  --output reports/client.csv \
  --json reports/client.json \
  --site "Client Example"
```

Exemple avec stopwords de niche explicites:

```bash
python3 prospect_machine.py gsc \
  exports/pages_recent.csv \
  exports/pages_old.csv \
  -q exports/queries.csv \
  --niche-stopwords "padel,tennis" \
  --output reports/gsc_report.csv
```

Exemple avec détection automatique des stopwords de niche:

```bash
python3 prospect_machine.py gsc \
  exports/pages_recent.csv \
  exports/pages_old.csv \
  -q exports/queries.csv \
  --auto-niche-stopwords \
  --output reports/gsc_report.csv
```

Le module GSC est utile quand tu veux:

- prioriser des pages qui declinent
- identifier des opportunites de refresh
- preparer un support de restitution simple

### 5. Utiliser l'UI locale

Lancement:

```bash
python3 prospect_machine.py ui
```

Puis ouvrir:

```text
http://127.0.0.1:8787
```

L'UI permet de:

- lancer `discover`, `qualify`, `audit`, `gsc`
- suivre les jobs
- voir les logs
- ouvrir les fichiers generes
- previsualiser les derniers `CSV` et `JSON`
- reset les sorties de pipeline generees localement

## Guide de l'UI locale

L'interface web est organisee en 4 cards principales: `Discover`, `Qualify`, `Audit` et `GSC`.

Chaque card correspond a une commande CLI du projet.

### Card `Discover`

Cette card sert a produire un fichier `domains_raw.csv`, soit depuis des niches, soit depuis un fichier de domaines deja prepare.

Chaque case de la card `Discover`:

- `Niches`
  Role: dire au module sur quels sujets il doit chercher des sites.
  Quoi mettre: une ou plusieurs niches separees par des virgules.
  Exemple: `padel,yoga,velo`.
  Bon a savoir: si tu remplis `Domains file`, ce champ devient moins utile, car tu fournis deja une liste manuelle.

- `Domains file`
  Role: importer une liste de domaines ou d'URL deja preparee.
  Quoi mettre: un chemin de fichier texte local.
  Exemple: `data/mes_sites.txt`.
  Format attendu du fichier: une ligne = un domaine ou une URL.
  Exemple de contenu:
  `example.com`
  `https://media-site.fr`
  `blog-affiliation.net`

- `Limit`
  Role: fixer le nombre maximum de domaines uniques a sortir.
  Quoi mettre: un nombre entier.
  Exemple: `30`, `50`, `100`.
  Comment le lire: si tu mets `30`, `discover` s'arrete une fois qu'il a trouve 30 domaines exploitables.

- `Delay`
  Role: ajouter un delai entre les recherches.
  Quoi mettre: un nombre en secondes, y compris decimal.
  Exemple: `0.5`, `1`, `1.5`.
  Comment le choisir: plus c'est bas, plus c'est rapide. Plus c'est haut, plus c'est prudent.

- `Provider`
  Role: choisir le provider de recherche utilise par le module.
  Quoi mettre: le nom du provider.
  Exemple: `auto`.
  Bon a savoir: dans l'etat actuel du projet, la valeur par defaut est celle qu'il faut garder dans la plupart des cas.

- `Output`
  Role: definir ou ecrire le resultat du module `discover`.
  Quoi mettre: un chemin de fichier CSV.
  Exemple: `data/domains_raw.csv`.
  Resultat: ce fichier devient ensuite l'entree naturelle de la card `Qualify`.

Quand utiliser quoi:

- remplis `Niches` si tu veux trouver de nouveaux prospects
- remplis `Domains file` si tu as deja une liste manuelle
- n'utilise pas forcement les deux en meme temps

Sortie attendue:

- `data/domains_raw.csv`

### Card `Qualify`

Cette card lit le CSV produit par `discover`, visite les homepages et calcule un score de priorisation.

Chaque case de la card `Qualify`:

- `Input CSV`
  Role: indiquer quel fichier de domaines doit etre lu.
  Quoi mettre: le CSV produit par `discover`.
  Exemple: `data/domains_raw.csv`.
  Contenu attendu: des lignes avec au minimum un domaine a visiter.

- `Output CSV`
  Role: definir ou enregistrer la sortie principale de `qualify`.
  Quoi mettre: un chemin de fichier CSV.
  Exemple: `data/domains_scored.csv`.
  Resultat: ce fichier contiendra les scores, flags et notes de qualification.

- `Output JSON`
  Role: enregistrer la meme sortie sous format JSON.
  Quoi mettre: un chemin de fichier JSON.
  Exemple: `data/domains_scored.json`.
  Pourquoi c'est utile: plus pratique pour relire les champs longs ou reutiliser les resultats dans un autre script.

- `Delay`
  Role: ajouter un delai entre deux homepages visitees.
  Quoi mettre: un nombre en secondes.
  Exemple: `0.2`.
  Comment le choisir: si tu qualifies beaucoup de sites, un petit delai evite un comportement trop agressif.

- `Mode`
  Role: choisir a quel point `qualify` doit rester leger ou creuser davantage.
  Quoi mettre: `qualify_fast` ou `qualify_full`.
  Bon a savoir: `qualify_fast` est le mode par defaut pour la prospection en lot. `qualify_full` inspecte un peu plus le domaine et son sitemap.

Ce que tu mets en pratique:

- `Input CSV` = ce qui entre dans le module
- `Output CSV` / `Output JSON` = ce que le module va produire

Sorties attendues:

- `data/domains_scored.csv`
- `data/domains_scored.json`

### Card `Audit`

Cette card prend les domaines qualifies et lance un crawl plus profond pour produire un rapport de prospection exploitable.

Chaque case de la card `Audit`:

- `Input CSV`
  Role: dire au module quelle liste de domaines scores il doit auditer.
  Quoi mettre: le CSV produit par `qualify`.
  Exemple: `data/domains_scored.csv`.
  Bon a savoir: l'audit s'appuie sur les scores deja calcules pour choisir les meilleurs candidats.

- `Top`
  Role: limiter le nombre de domaines a auditer.
  Quoi mettre: un entier.
  Exemple: `3`, `10`, `20`.
  Comment le lire: si tu mets `3`, seuls les 3 meilleurs domaines apres tri seront audites.

- `Mode`
  Role: choisir entre un audit tres leger et un audit plus complet.
  Quoi mettre: `audit_light` ou `audit_full`.
  Bon a savoir: `audit_light` est le mode par defaut. `audit_full` doit rester reserve a quelques domaines seulement.

- `Crawl source`
  Role: choisir les URLs de depart du crawl.
  Quoi mettre: `mixed`, `home` ou `sitemap`.
  Bon a savoir: `mixed` est le defaut conseille pour les sites WordPress, car la homepage ne lie pas toujours toutes les pages utiles.

- `Min score`
  Role: ignorer les domaines trop faibles.
  Quoi mettre: un score minimum entre `0` et `100`.
  Exemple: `50`, `60`, `70`.
  Comment le lire: si tu mets `50`, tout domaine avec un score inferieur a 50 sera exclu.

- `Max pages`
  Role: limiter la profondeur pratique de l'audit.
  Quoi mettre: un nombre entier.
  Exemple: `30`, `80`, `100`.
  Comment le choisir: l'UI propose `100` par defaut pour couvrir les petits sitemaps. `30` est seulement un triage rapide.

- `Temps max / site`
  Role: fixer le budget temps par domaine dans l'UI.
  Quoi mettre: un nombre de secondes.
  Exemple: `90`, `180`, `300`.
  Bon a savoir: si le sitemap contient beaucoup d'URLs mais que peu de pages sont analysees, ce budget est souvent le premier frein.

- `Delay`
  Role: ajouter un delai entre les pages crawlées.
  Quoi mettre: un nombre en secondes.
  Exemple: `0.2`, `0.5`, `1`.
  Effet: plus le delai est bas, plus le crawl avance vite.

- `Output dir`
  Role: definir le dossier dans lequel ecrire les rapports d'audit.
  Quoi mettre: un chemin de dossier.
  Exemple: `reports/audits`.
  Resultat: le module y ecrira un `audit_summary.csv` et un JSON par domaine.

Comment lire les filtres:

- `Top` sert a limiter le volume
- `Min score` sert a eviter de perdre du temps sur les faibles candidats
- tu peux utiliser les deux ensemble

Sorties attendues:

- `reports/audits/audit_summary.csv`
- `reports/audits/<domain>.json`

### Card `GSC`

Cette card analyse des exports Google Search Console.

Chaque case de la card `GSC`:

- `Current CSV`
  Role: fournir l'export GSC principal, sur la periode recente.
  Quoi mettre: le chemin du CSV exporte depuis Google Search Console.
  Exemple: `exports/pages_recent.csv`.
  C'est le fichier minimum pour faire tourner le module.

- `Previous CSV`
  Role: comparer la periode recente a une periode plus ancienne.
  Quoi mettre: le chemin d'un second export GSC.
  Exemple: `exports/pages_old.csv`.
  Si tu le laisses vide: l'analyse marche quand meme, mais avec moins de recul sur les baisses.

- `Queries CSV`
  Role: enrichir l'analyse avec les requetes associees aux pages.
  Quoi mettre: le chemin d'un export GSC des requetes.
  Exemple: `exports/queries.csv`.
  Si tu le laisses vide: le module reste utile, mais certaines analyses seront moins riches.

- `Site label`
  Role: afficher un nom lisible du site ou du client dans les sorties.
  Quoi mettre: un texte libre.
  Exemple: `Client Example` ou `Magazine Yoga FR`.
  Ce champ sert surtout pour rendre les rapports plus propres a partager.

- `Niche stopwords`
  Role: ignorer explicitement des mots de niche dans la detection de chevauchement page / requete.
  Quoi mettre: une liste separee par des virgules.
  Exemple: `padel,tennis,mutuelle`.
  Bon a savoir: ces mots s'ajoutent au set generique deja integre dans le module.

- `Auto niche stopwords`
  Role: detecter automatiquement les mots trop frequents dans le corpus d'URLs analyse.
  Quoi mettre: coche la case si tu veux activer ce mode.
  Effet: les tokens presents dans au moins 60% des URLs sont ignores pour la detection de chevauchement.

- `Output CSV`
  Role: definir ou ecrire le rapport tabulaire genere par le module GSC.
  Quoi mettre: un chemin de fichier CSV.
  Exemple: `reports/gsc_report.csv`.

- `Output JSON`
  Role: ecrire la meme analyse au format JSON.
  Quoi mettre: un chemin de fichier JSON.
  Exemple: `reports/gsc_report.json`.

- `Output HTML`
  Role: generer une version HTML plus confortable a lire ou partager localement.
  Quoi mettre: un chemin de fichier HTML.
  Exemple: `reports/gsc_report.html`.

Cas courant:

- si tu n'as que l'export recent, tu peux deja lancer l'analyse
- si tu as aussi `Previous CSV`, l'analyse des baisses sera meilleure
- si tu as `Queries CSV`, le rapport sera plus riche

Sorties attendues:

- `reports/gsc_report.csv`
- `reports/gsc_report.json`
- `reports/gsc_report.html`

### Resume simple des termes `Input`, `Output` et `dir`

- `Input CSV`: fichier d'entree lu par le module
- `Output CSV`: fichier CSV cree par le module
- `Output JSON`: fichier JSON cree par le module
- `Output HTML`: fichier HTML cree par le module
- `Output dir`: dossier de sortie dans lequel plusieurs fichiers peuvent etre generes
- `Delay`: temps d'attente volontaire entre deux requetes ou deux pages
- `Top`: nombre maximum d'elements a traiter
- `Min score`: score minimal a respecter pour etre traite

## Fichiers generes

Les sorties generees localement les plus frequentes sont:

```text
data/domains_raw.csv
data/domains_scored.csv
data/domains_scored.json
reports/audits/audit_summary.csv
reports/audits/<domain>.json
reports/audits/<domain>/<timestamp>.json
reports/audits/audit_index.sqlite
reports/audits/<domain>.html
reports/gsc_report.csv
reports/gsc_report.json
reports/gsc_report.html
```

Le `.gitignore` est configure pour eviter de versionner ces artefacts de travail.

## Commandes utiles

Afficher l'aide generale:

```bash
python3 prospect_machine.py --help
```

Afficher l'aide d'un sous-module:

```bash
python3 prospect_machine.py discover --help
python3 prospect_machine.py qualify --help
python3 prospect_machine.py audit --help
python3 prospect_machine.py compare-audits --help
python3 prospect_machine.py gsc --help
python3 prospect_machine.py doctor --help
python3 prospect_machine.py ui --help
```

Verifier l'installation locale:

```bash
python3 prospect_machine.py doctor
```

Lancer les tests:

```bash
python3 -m unittest discover -s tests -v
```

## Philosophie du scoring

Le projet ne cherche pas a produire une "verite SEO".

Il cherche a produire une priorisation raisonnable pour la prospection:

- bonus leger pour les profils editoriaux exploitables
- forte penalite pour les sites app/docs-heavy
- penalite plus moderee pour les marketplaces
- audit centre sur les points qui parlent trafic, refresh et retravail de contenu
- wording prudent pour rester credible commercialement

## Notes d'architecture

- `prospect_machine.py` est le point d'entree unique
- `config.py` centralise les constantes et exclusions
- `models.py` contient les dataclasses partagees
- `io_helpers.py` gere les lectures/ecritures `CSV` et `JSON`
- `qualify.py` separe collecte des signaux et qualification
- `scoring.py` centralise les ponderations
- `audit.py` gere crawl, heuristiques et rapport
- `audit_store.py` persiste un index SQLite local des audits
- `compare_audits.py` compare deux rapports JSON d'audit
- `doctor.py` verifie l'installation locale
- `web_ui.py` reste un shim de compatibilite vers le package `web_ui/`
- `web_ui/` fournit une UI locale tres legere, decoupee en sous-modules (`server`, `jobs`, `fs_ops`, `rendering`)

## Compatibilite legacy

Le fichier `site_audit.py` reste disponible comme wrapper de compatibilite historique:

```bash
python3 site_audit.py https://example.com -n 100 -o audit.json
```
