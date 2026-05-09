# Audit de la couche de normalisation — état actuel

> **Périmètre effectivement lu** : `qualify.py`, `models.py`, `gsc.py` (5 709 lignes), `reports/gsc_report.html` (689 lignes — rendu statique final), `web_ui/rendering.py`, `scoring.py`, `tests/` (comptage uniquement).
>
> **Correction de périmètre** : le prompt référençait `src/prospect_machine/qualify.py`, `src/prospect_machine/web_ui.py` et `src/prospect_machine/gsc_report.html`. Ces chemins n'existent pas. Les fichiers réels sont à la racine du projet (`qualify.py`, `web_ui/rendering.py`, `web_ui/_render_helpers.py`) et le template Jinja2 évoqué est en réalité du HTML généré par f-strings Python dans `gsc.py`. Le fichier `reports/gsc_report.html` est un rendu statique final, pas un template Jinja2.

---

## Q1 — Représentation des opportunités

Il n'existe **pas** de dataclass `PageOpportunity` ou équivalent spécifique aux pages-opportunités GSC.

La représentation utilisée est la dataclass `GSCPageAnalysis`, définie dans [models.py:272](models.py#L272).

**Nom exact** : `GSCPageAnalysis`  
**Fichier** : `models.py`  
**Ligne de définition** : 272

**Champs** (avec types, lignes 272–305) :

| Champ | Type | Valeur par défaut |
|---|---|---|
| `url` | `str` | (obligatoire) |
| `clicks` | `int` | `0` |
| `impressions` | `int` | `0` |
| `ctr` | `float` | `0.0` |
| `position` | `float` | `0.0` |
| `prev_clicks` | `int \| None` | `None` |
| `prev_impressions` | `int \| None` | `None` |
| `prev_position` | `float \| None` | `None` |
| `click_delta` | `int \| None` | `None` |
| `impression_delta` | `int \| None` | `None` |
| `position_delta` | `float \| None` | `None` |
| `score` | `float` | `0.0` |
| `category` | `str` | `""` |
| `actions` | `list[str]` | `field(default_factory=list)` |
| `priority` | `str` | `""` |
| `possible_overlap_queries` | `list[str]` | `field(default_factory=list)` |
| `estimated_recoverable_clicks` | `int \| None` | `None` |
| `impact_label` | `str` | `""` |
| `page_type` | `str` | `""` |
| `business_value` | `str` | `"low"` |
| `business_reason` | `str` | `""` |
| `monetization_possible` | `str` | `"none"` |
| `opportunity_score` | `int` | `0` |
| `priority_label` | `str` | `"Watch"` |
| `action_type` | `str` | `"content refresh"` |
| `main_query` | `str` | `""` |
| `recommendation` | `str` | `""` |
| `cannibalization_group_id` | `str` | `""` |
| `urls_in_group` | `list[str]` | `field(default_factory=list)` |
| `shared_queries` | `list[str]` | `field(default_factory=list)` |
| `cannibalization_confidence` | `str` | `""` |
| `cannibalization_recommendation` | `str` | `""` |

Les instances de `GSCPageAnalysis` sont passées au rendu HTML via un dict intermédiaire produit par `page_to_report_dict()` ([gsc.py:3195](gsc.py#L3195)) — donc ce n'est **pas** la dataclass directement qui est injectée dans le rendu, mais un `dict[str, object]`.

---

## Q2 — Génération des champs texte

### `constat` (la phrase "La page reçoit beaucoup d'impressions…")

- **Source** : template Python, branche conditionnelle (f-strings / chaînes littérales). Pas de LLM.
- **Fichier + ligne** : `gsc.py`, fonction `diagnostic_for_page()`, lignes 3309–3320.
- **Logique exacte** :
  - Si `is_dead_gsc_page(item)` → phrase fixe
  - Sinon si `is_snippet_opportunity(item)` → `"La page reçoit beaucoup d'impressions mais son taux de clic reste faible par rapport à sa visibilité."`
  - Sinon si `4 <= position <= 10` → `"La page est déjà proche des premières positions et peut progresser avec un renforcement ciblé."`
  - Sinon si `10 < position <= 20` → phrase fixe sur la profondeur/soutien interne
  - Sinon si `possible_overlap_queries` → phrase fixe sur le chevauchement
  - Défaut → phrase générique
- **Validation** : aucune (longueur, doublons, ponctuation).
- **Rendu** : injecté dans le HTML à la ligne 5010 de `gsc.py` via `page.get("diagnostic", "")`.

---

### `action_recommandee_specifique` (la phrase d'action par page)

- **Source** : template Python, arbre conditionnel à mots-clés, sans LLM.
- **Fichier + ligne** : `gsc.py`, fonctions `generate_page_recommendation()` (lignes 1581–1642) et `specific_recommendation_for_page()` (lignes 1554–1561).
- **Logique** :
  1. Détection de mots-clés dans l'URL/requête (`"tournoi"`, `"tenir-raquette-padel"`, `"pressurisateur"`, `"chaussures-padel"`, `"raquette-padel"`, `"/test-"`, `"sac-padel"`, `"balles-padel"`) → phrases hardcodées ou construites via `tournament_recommendation()` (lignes 1665–1681).
  2. Si aucun hit → signal dominant via `_dominant_signal()` (lignes 1564–1578) : `"cannibalization"`, `"low_ctr"`, `"low_position"`, `"business_underused"`, ou `"generic"`.
  3. Chaque signal produit une f-string avec interpolation de `query`.
  4. Post-traitement via `vary_repeated_recommendations()` (ligne 1684) : si la même recommandation apparaît > 3 fois dans la liste triée par score, elle est remplacée par une variante issue de `varied_recommendation_for_page()` (lignes 1700–1726).
  5. Post-traitement supplémentaire dans `page_to_report_dict()` (lignes 3200–3207) : si une anomalie SERP est détectée et que "featured snippet" n'est pas déjà dans le texte, la recommandation est suffixée.
- **Validation** : aucune sur longueur, doublons finaux ou ponctuation.
- **Rendu** : `gsc.py`, ligne 4976–4979, champ `recommendation`.

---

### `objectif_mesurable` (le texte "CTR actuel X% → cible Y%–Z%…")

- **Source** : template Python, calcul numérique + f-string. Pas de LLM.
- **Fichier + ligne** : `gsc.py`, fonction `build_target_metric()` (lignes 3165–3192), appelée depuis `page_to_report_dict()` (ligne 3199).
- **Logique** :
  - Appelle `compute_target_metric()` (lignes 3127–3162) qui lit `CTR_BY_POSITION_MEDIAN` et `CTR_BY_POSITION_P75` depuis `ctr_benchmarks.py`.
  - Borne basse = médiane CTR à la position actuelle arrondie (max 20).
  - Borne haute = P75 CTR à la position cible (position - 2 ou position - 1 si ≤ 5).
  - Garantie de fourchette non dégénérée : si `ctr_high < ctr_low * 1.3` → `ctr_high = ctr_low * 1.5`.
  - `ctr_low = max(ctr_low, ctr_actual * 1.1)` (la borne basse ne peut être inférieure au CTR actuel).
  - Si `gain_low == 0` → format "jusqu'à +X clics/mois sous 6-8 semaines".
  - Sinon → format "+X à +Y clics/mois sous 6-8 semaines".
  - Retourne `""` si `impressions < 10` ou `gain_high <= 0`.
- **Validation** : aucune sur le texte produit.
- **Rendu** : `gsc.py`, lignes 4981–4989, champ `target_metric`.

---

### `title` et `meta` (section "Résultats Google à améliorer")

- **Source** : template Python, arbre conditionnel à mots-clés. Pas de LLM.
- **Fichier + ligne** : `gsc.py`, fonction `generate_snippet_recommendation()` (lignes 3383–3450).
- **Logique** :
  1. Détection du niveau tournoi via `detect_tournament_level()` → génère des title/meta spécifiques.
  2. Sinon, conditions successives sur mots-clés dans l'URL/requête : `"par 4"`, `"tenir"+"raquette"`, `"agustin"/"tapia"`, `"pressurisateur"`, `"chaussure"`, `"tournoi"`, termes comparatifs/achat (`"meilleur"`, `"test"`, etc.), forme interrogative (`"comment"`).
  3. Si aucune condition ne matche → retourne `{"title": "", "meta": "", "reason": ""}` (page exclue de la section).
  4. Post-traitement : `trim_to_length(title, 60)` et `trim_to_length(meta, 160)`.
  5. Validation `has_specific_snippet_angle(title, query)` — si échoue → retourne `{"title": "", "meta": "", "reason": ""}`.
  6. Si `len(meta) < 120` → suffixe ajouté : `" Une synthèse pratique pour décider quoi faire ensuite."`.
  7. `sanitize_snippet_text()` (lignes 3469–3486) applique un dictionnaire de remplacements de formules génériques.
- **Validation présente** :
  - Longueur : `trim_to_length` à 60 chars (title) et 160 chars (meta).
  - Filtre de spécificité : `has_specific_snippet_angle()` — si échoue, la page est exclue du rendu.
  - Aucune validation sur doublons ou ponctuation finale.
- **Rendu** : `gsc.py`, fonction `snippet_to_report_dict()` (lignes 3356–3380), champs `title_example` et `meta_example`.

---

## Q3 — Logique métier dans le template Jinja2

**Le fichier `reports/gsc_report.html` est un rendu statique final, pas un template Jinja2.** L'HTML est produit directement par des f-strings Python dans `gsc.py` (fonctions `render_client_page_card`, `render_executive_query_opportunities`, `render_gsc_html_report`, etc.). Il n'y a donc aucun `{% if %}`, aucun `{{ x * 100 }}` ni filtre Jinja2 dans ce fichier — les calculs et conditions sont résolus côté Python avant que l'HTML soit écrit.

Les occurrences de logique conditionnelle et de calculs existent donc dans le générateur Python, pas dans le template rendu. Exemples représentatifs dans `gsc.py` :

| Ligne | Équivalent logique | Code Python |
|---|---|---|
| 3309–3320 | Condition sur `is_dead`, `is_snippet_opportunity`, position | `diagnostic_for_page()` |
| 3093–3098 | Condition `impressions >= 100 and estimated_recoverable_clicks and actions contains ctr/title/méta` | `is_snippet_opportunity()` |
| 4960 | Calcul CSS de priorité | `page_priority_class(str(page.get("priority", "p3")))` |
| 4992 | Condition sur `serp_anomaly == "serp_features_suspected"` | `if serp_anomaly == "serp_features_suspected":` |
| 5037–5041 | Condition sur libellé de métrique (CTR/potentiel) → class CSS | `metric_state_class(label)` |
| 5122–5123 | Condition `target_url` vide → `"à valider"` | `target_label = compact_url_for_display(target_url) if target_url else _("à valider")` |

Les constantes (seuils numériques) hardcodées côté Python et injectées dans le HTML statique incluent : `impressions >= 100` (seuil snippet), `position >= 60` (barre de position), score `>= 60` / `>= 40` (seuils HIGH/MEDIUM).

---

## Q4 — Calcul de la priorité

### Où est calculé `priorite` (HIGH / MEDIUM / LOW)

Calculé dans `gsc.py`, fonction `priority_for_page()`, lignes 1741–1749, appelée depuis `analyze_pages()` (ligne 1384).

### Algorithme exact

```python
def priority_for_page(analysis: GSCPageAnalysis) -> str:
    if is_dead_gsc_page(analysis):
        return "DEAD"
    score = analysis.opportunity_score or int(round(analysis.score))
    if score >= 60:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"
```

Où `is_dead_gsc_page` (défini dans `scoring.py`, lignes 120–124) :

```python
def is_dead_gsc_page(analysis: GSCPageAnalysis) -> bool:
    low_impressions = analysis.impressions < 50
    bad_position = analysis.position > 40 or analysis.position == 0
    no_clicks = analysis.clicks < 5
    return low_impressions and bad_position and no_clicks
```

Et `opportunity_score` est calculé par `seo_opportunity_score()` (`gsc.py`, lignes 1472–1518) :

```python
def seo_opportunity_score(analysis: GSCPageAnalysis, max_impressions: int) -> int:
    if is_dead_gsc_page(analysis):
        return 0
    impressions_score = min(20.0, (analysis.impressions / max(1, max_impressions)) * 20.0)
    expected_ctr = expected_ctr_for_position(analysis.position)
    ctr_gap_score = 0.0
    if expected_ctr:
        ctr_gap_score = max(0.0, min(20.0, ((expected_ctr - analysis.ctr) / expected_ctr) * 20.0))
    if 4 <= analysis.position <= 12:
        position_score = 20.0
    elif 12 < analysis.position <= 15:
        position_score = 14.0
    elif 2 <= analysis.position < 4:
        position_score = 9.0
    elif 15 < analysis.position <= 25:
        position_score = 6.0
    else:
        position_score = 0.0
    business_score = {"high": 25.0, "medium": 10.0, "low": 0.0}.get(analysis.business_value, 0.0)
    query_score = 5.0 if analysis.main_query and analysis.main_query != "la requête principale" else 0.0
    monetization_score = 15.0 if analysis.monetization_possible != "none" else 0.0
    gain_score = 5.0 if analysis.estimated_recoverable_clicks else 0.0
    action_score = 0.0
    if is_snippet_opportunity(analysis):
        action_score += 10.0
    if 4 <= analysis.position <= 15:
        action_score += 10.0
    if analysis.impressions < 50:
        impressions_score = max(0.0, impressions_score - 20.0)
        ctr_gap_score *= 0.4
    if analysis.position > 30 and analysis.business_value != "high":
        position_score = max(0.0, position_score - 20.0)
    low_business_penalty = 15.0 if analysis.business_value == "low" else 0.0
    cannibalization_penalty = 10.0 if analysis.cannibalization_confidence == "high" else 0.0
    score = (
        impressions_score + ctr_gap_score + position_score + business_score
        + query_score + monetization_score + gain_score + action_score
        - low_business_penalty - cannibalization_penalty
    )
    return int(round(max(0.0, min(100.0, score))))
```

### Le champ `position` intervient-il dans le calcul ?

Oui, de trois façons :
1. `position_score` : score de 0 à 20 selon les tranches de position.
2. `expected_ctr_for_position()` : CTR attendu à la position, utilisé pour calculer `ctr_gap_score`.
3. `is_dead_gsc_page()` : `position > 40 or position == 0` conduit à `DEAD` (score = 0).

### Étape post-calcul qui rétrograde ou exclut selon la position

- **Rétrogradation** : si `position > 30 and business_value != "high"` → `position_score` est ramené à 0 (ligne 1502–1503). Cela peut faire passer un score sous les seuils HIGH/MEDIUM.
- **Exclusion (DEAD)** : si `position > 40 or position == 0` ET `impressions < 50` ET `clicks < 5` → `is_dead_gsc_page = True` → `priority = "DEAD"`, `opportunity_score = 0`.
- **Filtrage rendu** : dans `build_priority_page_cards()` (ligne 2598), les pages dont `priority not in {"HIGH", "MEDIUM"} and not estimated_recoverable_clicks` sont exclues de la section "Pages prioritaires".

---

## Q5 — Origine des lignes "URL cible: à valider"

### Localisation de la chaîne littérale

La chaîne `"à valider"` est assignée dans **`gsc.py`, ligne 5123** :

```python
target_label = compact_url_for_display(target_url) if target_url else _("à valider")
```

Dans la fonction `render_executive_query_opportunities()` (lignes 5116–5144).

### À quelle étape et pourquoi

La logique est la suivante :
1. Chaque groupe de requêtes a un `target_url` calculé par `best_target_url_for_query()` (lignes 2011–2036).
2. `best_target_url_for_query()` retourne `""` (chaîne vide) si aucune URL candidate n'a de token en commun avec la requête (`return best[1] if best else ""`).
3. En amont, `aggregate_queries_by_target_url()` (lignes 2787–2817) appelle `best_target_url_for_query()` et stocke le résultat dans `target_url` du dict de groupe (ligne 2816).
4. Au rendu, si `target_url` est une chaîne vide ou falsy → `target_label = _("à valider")`.

La ligne HTML résultante est donc :
```html
<a href='' title=''>à valider</a>
```
(visible en `reports/gsc_report.html`, ligne 436, dernière ligne du tbody du tableau requêtes).

### Est-elle filtrée avant le rendu ?

**Non.** Il n'y a aucune étape de filtrage des groupes dont `target_url == ""` avant le passage à `render_executive_query_opportunities()`. Les groupes avec URL vide sont inclus dans la liste `rows` et rendus tels quels, avec le label de substitution `"à valider"`.

---

## Q6 — Tests existants

### Fichiers de tests

| Fichier | Nombre approximatif de `def test_` |
|---|---|
| `tests/test_gsc.py` | 43 |
| `tests/test_report_refonte.py` | 30 |
| `tests/test_audit.py` | 38 |
| `tests/test_web_ui.py` | 32 |
| `tests/test_date_detection.py` | 28 |
| `tests/test_discover.py` | 20 |
| `tests/test_iteration2.py` | 16 |
| `tests/test_qualify.py` | 9 |
| `tests/test_scoring.py` | 6 |
| `tests/test_audit_tools.py` | 2 |

### Existence d'un `test_qualify.py`

**Oui**, `tests/test_qualify.py` existe, avec 9 fonctions de test.

---

## Annexe — Observations annexes

**1. Double score (legacy vs opportunity)** : `analyze_pages()` (lignes 1372–1382) calcule deux scores distincts — un `legacy_score` (somme de `gsc_score_position + gsc_score_impressions + gsc_score_ctr + gsc_score_decline` depuis `scoring.py`) et un `opportunity_score` (issu de `seo_opportunity_score()`). Le `score` final retenu est `max(legacy_score, float(opportunity_score))`, mais `priority_for_page()` utilise `analysis.opportunity_score or int(round(analysis.score))` (ligne 1744). Ces deux scores ne sont pas équivalents et peuvent diverger silencieusement.

**2. `qualify.py` n'est pas lié au pipeline GSC** : le fichier `qualify.py` traite la qualification de domaines prospects (crawl HTTP, détection CMS, scoring éditorial), non les pages-opportunités GSC. Les règles métier GSC sont entièrement dans `gsc.py`.

**3. Absence de template Jinja2** : le rapport GSC est généré par f-strings Python concaténées dans `gsc.py` (fonctions `render_gsc_html_report`, `render_client_page_card`, etc.). Toute la logique conditionnelle et tous les seuils métier sont dans `gsc.py`, pas dans un fichier template séparé.

**4. `_("à valider")` passe par `gsc_gettext(lang)`** : la chaîne est traduite via le mécanisme i18n de `gsc.py`, ce qui implique qu'une version EN du rapport utilise la traduction anglaise de cette chaîne (non auditée ici).

**5. Validation post-génération quasi-absente** : les champs `constat`, `action_recommandee_specifique` et `objectif_mesurable` n'ont aucune validation de longueur ou de ponctuation finale. Seul le champ `title`/`meta` (snippets) bénéficie d'un `trim_to_length` et d'un filtre `has_specific_snippet_angle`.
