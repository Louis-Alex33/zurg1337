# Changelog

## [Unreleased]

### Corrections de bugs — étape 2B (rapport eversportzone du 09/05/2026)

- **Bug 1 — Garde-fou position** : `priority_for_page()` force désormais `MEDIUM` si `position > 30` et `HIGH`, et `LOW` si `position > 50`. La page `/niveaux-padel-classement-padel/` (pos 51.3) n'est plus classée HIGH.
- **Bug 2 — Constat dynamique** : `diagnostic_for_page()` sélectionne parmi 5 templates selon le profil (position × CTR vs médiane attendue × impressions). Le constat varie selon chaque page. Constantes `IMPRESSIONS_THRESHOLD_HIGH` et `CTR_TOLERANCE` ajoutées.
- **Bug 3 — Cap cluster** : `cap_top_priority_per_cluster()` limite à 2 pages par cluster dans le top 10 (signature = action_type + business_value + slug_prefix). Les pages Belasteguin / Tapia / Coello / Ortega ne saturent plus le top 10. Helper `slug_prefix()` ajouté. Branché dans `build_priority_page_cards()` de `gsc.py`.
- **Bug 4 — Filtrage cibles non résolues** : `is_resolvable_target()` détecte les URLs vides ou placeholder. `resolve_target_label()` lève `ValueError` au lieu de retourner "à valider". `render_executive_query_opportunities()` filtre les lignes non résolvables et log le count + sample. Aucune ligne `URL cible: à valider` dans le tableau.
- **Bug 5 — Validation snippets** : `trim_to_length()` coupe proprement (ponctuation et conjonctions orphelines supprimées). `dedupe_tokens()` ajouté (déduplication des tokens significatifs). Limites 60 / 155 caractères respectées. Appliqué dans `generate_snippet_recommendation()`.
- **Bug 6 — Sync plan d'action** : le plan d'action 30 jours est dérivé du même `priority_pages` (post-garde-fou, post-cap cluster) que le top 10. Commentaire `# bug 2B-6` ajouté dans `gsc.py` au point de synchronisation.

### Tests
- 36 tests nouveaux dans `tests/test_gsc_rules.py` (6 classes de tests bug + cas limites), 54 au total dans ce fichier.
- Nouveau test de stabilité post-2B : `tests/test_gsc_rules_post_2B_stability.py`.
- Baseline pré-2B archivé dans `tests/fixtures/baseline_report_pre_2B.html`.
- Test binaire pré-2B renommé en `tests/test_gsc_rules_baseline_archive.py` et marqué `@skip` (attendu comme différent post-2B).

### Refactoring
- Extraction des règles métier GSC dans `gsc_rules.py` (refonte iso-comportement, aucune correction de bug à cette étape). Les fonctions `priority_for_page`, `diagnostic_for_page`, `generate_page_recommendation`, `build_target_metric`, `generate_snippet_recommendation` et `resolve_target_label` sont désormais définies dans `gsc_rules.py` et importées dans `gsc.py`. Le rapport HTML produit est strictement identique avant et après cette extraction (validé par test de comparaison binaire).
