"""
gsc_rules.py — Règles métier GSC extraites de gsc.py (refonte iso-comportement).

Contient les 6 fonctions publiques et leurs helpers privés exclusifs :
  priority_for_page, diagnostic_for_page, generate_page_recommendation,
  build_target_metric, generate_snippet_recommendation, resolve_target_label.

Mapping des dépendances
=======================
priority_for_page(analysis: GSCPageAnalysis) -> str
  - is_dead_gsc_page        ← scoring.py (importé directement)
  - GSCPageAnalysis         ← models.py

diagnostic_for_page(item: GSCPageAnalysis) -> str
  - is_dead_gsc_page        ← scoring.py
  - is_snippet_opportunity  ← défini ici (helper privé exclusif)
  - GSCPageAnalysis         ← models.py

generate_page_recommendation(page, main_queries, page_type, business_value, analysis) -> str
  - keyword_phrase_from_url ← défini ici (helper déplacé depuis gsc.py)
  - strip_accents           ← défini ici (helper déplacé depuis gsc.py)
  - detect_tournament_level ← défini ici (helper déplacé depuis gsc.py)
  - tournament_recommendation ← défini ici
  - _dominant_signal        ← défini ici (helper privé exclusif)
  - EXPECTED_CTR_BY_POSITION ← constante déplacée depuis gsc.py
  - GSCPageAnalysis         ← models.py

build_target_metric(item: GSCPageAnalysis) -> str
  - compute_target_metric   ← défini ici (helper déplacé depuis gsc.py)
  - format_percent          ← défini ici (helper déplacé depuis gsc.py)
  - format_number           ← défini ici (helper déplacé depuis gsc.py)
  - GSCPageAnalysis         ← models.py

generate_snippet_recommendation(page, main_query, page_type, business_value, gsc_data, intent) -> dict
  - clean_query_for_snippet ← défini ici
  - strip_accents           ← défini ici
  - detect_tournament_level ← défini ici
  - _TOURNAMENT_LEVEL_DESCRIPTIONS ← défini ici
  - keyword_phrase_from_url ← défini ici
  - title_case_snippet      ← défini ici
  - trim_to_length          ← défini ici
  - sanitize_snippet_text   ← défini ici
  - has_specific_snippet_angle ← défini ici
  - TOURNAMENT_LEVEL_RE     ← constante déplacée depuis gsc.py
  - Any (typing)

resolve_target_label(target_url: str) -> str
  - compact_url_for_display ← défini ici (helper déplacé depuis gsc.py)
  - gsc_gettext             ← importée depuis gsc via paramètre _ passé à l'appelant
    NOTE : resolve_target_label reçoit la fonction _ en paramètre optionnel pour
    éviter tout import circulaire. Par défaut _ = str (pas de traduction).

Helpers déplacés depuis gsc.py (re-importés dans gsc.py depuis ce module) :
  strip_accents, display_slug, keyword_phrase_from_url,
  detect_tournament_level, tournament_recommendation,
  _TOURNAMENT_LEVEL_DESCRIPTIONS, TOURNAMENT_LEVEL_RE,
  is_snippet_opportunity, expected_ctr_for_position,
  compute_target_metric, format_number, format_percent,
  compact_url_for_display,
  clean_query_for_snippet, title_case_snippet, trim_to_length,
  sanitize_snippet_text, has_specific_snippet_angle,
  EXPECTED_CTR_BY_POSITION (constante également déplacée).

Helpers partagés qui RESTENT dans gsc.py (non importés ici) :
  is_dead_gsc_page ← scoring.py (importé directement ici depuis scoring)
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import replace as dataclass_replace
from typing import Any
from urllib.parse import unquote, urlparse

from models import GSCPageAnalysis
from scoring import is_dead_gsc_page

# ---------------------------------------------------------------------------
# Constantes et seuils
# ---------------------------------------------------------------------------

EXPECTED_CTR_BY_POSITION: dict[int, float] = {
    1: 0.30,
    2: 0.18,
    3: 0.12,
    4: 0.08,
    5: 0.06,
    6: 0.05,
    7: 0.04,
    8: 0.03,
    9: 0.025,
    10: 0.02,
    11: 0.015,
    12: 0.013,
    13: 0.011,
    14: 0.010,
    15: 0.009,
    16: 0.008,
    17: 0.007,
    18: 0.006,
    19: 0.005,
    20: 0.004,
}

TOURNAMENT_LEVEL_RE = re.compile(r"(?<![a-z0-9])p(25|100|250|500|1000|1500|2000)(?![a-z0-9])", re.I)

# Seuil au-dessus duquel les impressions sont considérées "significatives" pour le constat dynamique.
# Calibré sur le dataset eversportzone : les pages utiles dépassent 500 impressions/période.
IMPRESSIONS_THRESHOLD_HIGH: int = 500

# Tolérance CTR : le CTR doit être < CTR_TOLERANCE × médiane attendue pour déclencher
# le template "CTR sous médiane". 0.85 = 15 % sous la médiane avant d'alerter.
CTR_TOLERANCE: float = 0.85

# Nombre max de pages d'un même cluster autorisées en priorité haute dans le top 10.
MAX_PAGES_PER_CLUSTER: int = 2

# Position au-delà de laquelle une page ne peut jamais être "HIGH" (=> forcée MEDIUM).
POSITION_CAP_HIGH: int = 30

# Position au-delà de laquelle une page ne peut pas dépasser "LOW" (=> forcée LOW sauf DEAD).
POSITION_CAP_LOW: int = 50

# Stopwords français ignorés lors de la déduplication de tokens dans les snippets.
_FR_STOPWORDS: frozenset[str] = frozenset({
    "le", "la", "les", "de", "du", "des", "un", "une", "et", "ou", "mais",
    "à", "au", "aux", "en", "par", "sur", "sous", "dans", "avec", "pour",
    "que", "qui", "ce", "se", "sa", "son", "ses", "mon", "ma", "mes",
    "il", "elle", "ils", "elles", "on", "y", "ne", "pas", "plus", "très",
    "tout", "tous", "toute", "toutes", "cette", "ces", "cet",
})

_TOURNAMENT_LEVEL_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "P25":   ("débutants absolus, premier tournoi officiel", "le format open, les règles de base et l'attitude attendue en match"),
    "P100":  ("joueurs débutants ou en progression", "le niveau attendu, les points FFT et le déroulé d'une journée de compétition"),
    "P250":  ("joueurs réguliers de niveau intermédiaire", "les points à gagner, le classement, les conditions d'inscription et les coupes possibles"),
    "P500":  ("joueurs intermédiaires confirmés", "les points distribués, le format, les conditions de qualification et les pièges fréquents"),
    "P1000": ("joueurs de niveau avancé", "le nombre de points, les critères de sélection et ce qui distingue un P1000 d'un P500"),
    "P1500": ("joueurs expérimentés visant la compétition régionale", "le niveau requis, les points FFT et les conditions de participation"),
    "P2000": ("joueurs experts et compétiteurs confirmés", "les points distribués, le format tableau et les critères de niveau"),
}

# ---------------------------------------------------------------------------
# Helpers purs déplacés depuis gsc.py (re-importés dans gsc.py)
# ---------------------------------------------------------------------------

def strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def format_number(value: int | float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def format_percent(value: float) -> str:
    percent = float(value) * 100
    decimals = 2 if 0 < percent < 1 else 1
    return f"{percent:.{decimals}f} %".replace(".", ",")


def display_slug(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return path if path != "/" else parsed.netloc or url


def keyword_phrase_from_url(url: str) -> str:
    slug = display_slug(url).strip("/")
    if not slug:
        return "la requête principale"
    last_segment = slug.split("/")[-1]
    words = [word for word in re.split(r"[-_]+", last_segment) if word and not word.isdigit()]
    return " ".join(words[:6]) or "la requête principale"


def compact_url_for_display(url: str, max_length: int = 76) -> str:
    parsed = urlparse(str(url or ""))
    if not parsed.netloc:
        text = str(url or "")
    else:
        text = f"{parsed.netloc.replace('www.', '')}{parsed.path or '/'}"
    text = unquote(text)
    if len(text) <= max_length:
        return text
    keep = max(12, max_length - 1)
    return text[:keep].rstrip("/") + "…"


def expected_ctr_for_position(position: float) -> float:
    return EXPECTED_CTR_BY_POSITION.get(max(1, min(20, round(position))), 0.004)


def ctr_norm_lower_bound_for_position(position: float) -> float:
    from ctr_benchmarks import ctr_median

    return ctr_median(position) * 0.65


def is_snippet_opportunity(item: GSCPageAnalysis) -> bool:
    return (
        item.impressions >= 100
        and bool(item.estimated_recoverable_clicks)
        and any("ctr" in action.lower() or "title" in action.lower() or "méta" in action.lower() for action in item.actions)
    )


def compute_target_metric(position: float, ctr_actual: float, impressions: int) -> dict[str, object]:
    """Calcule la fourchette CTR cible et les gains estimés bas/haut.

    Garantit toujours une fourchette non dégénérée : ctr_high >= 1.3 × ctr_low.
    """
    from ctr_benchmarks import CTR_BY_POSITION_MEDIAN, CTR_BY_POSITION_P75
    pos_rounded = max(1, min(20, round(position)))

    # Borne basse : médiane de la position actuelle
    ctr_low_target = CTR_BY_POSITION_MEDIAN.get(pos_rounded, 0.005)

    # Borne haute : P75 de la position cible
    if pos_rounded <= 5:
        target_pos = max(1, pos_rounded - 1)
    else:
        target_pos = max(3, pos_rounded - 2)
    ctr_high_target = CTR_BY_POSITION_P75.get(target_pos, ctr_low_target * 1.4)

    # Garantie de fourchette non dégénérée
    if ctr_high_target < ctr_low_target * 1.3:
        ctr_high_target = ctr_low_target * 1.5

    # La borne basse ne peut pas être inférieure au CTR actuel (gain bas jamais négatif)
    ctr_low_target = max(ctr_low_target, ctr_actual * 1.1)

    gain_low = max(0, round(impressions * (ctr_low_target - ctr_actual)))
    gain_high = max(gain_low + 1, round(impressions * (ctr_high_target - ctr_actual)))

    return {
        "ctr_low_target": ctr_low_target,
        "ctr_high_target": ctr_high_target,
        "gain_low": gain_low,
        "gain_high": gain_high,
        "target_pos": target_pos,
        "pos_rounded": pos_rounded,
    }


def detect_tournament_level(*values: object) -> str:
    for value in values:
        text = strip_accents(str(value or "")).lower()
        match = TOURNAMENT_LEVEL_RE.search(text)
        if match:
            return f"P{match.group(1)}"
    return ""


def tournament_recommendation(level: str, page: str, query: str) -> str:
    topic = strip_accents(f"{page} {query}").lower()
    desc, focus = _TOURNAMENT_LEVEL_DESCRIPTIONS.get(level, ("joueurs de ce niveau", "le format et les conditions d'inscription"))
    if "points" in topic or "classement" in topic:
        return (
            f"Clarifier pour le niveau {level} (destiné aux {desc}) : {focus}. "
            f"Ajouter un tableau de points, les cas fréquents qui déclenchent la recherche et une FAQ courte."
        )
    if "inscription" in topic or "format" in topic:
        return (
            f"Structurer la page {level} pour les {desc} : détailler {focus}, "
            f"puis ajouter les informations à vérifier avant de s'inscrire et un lien vers le guide global des tournois."
        )
    return (
        f"Recentrer la page {level} sur l'intention principale des {desc} : réponse directe sur {focus}, "
        f"FAQ courte et liens internes vers les pages des niveaux adjacents."
    )


def clean_query_for_snippet(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", query.replace("-", " ")).strip(" /")
    return cleaned or "la requête principale"


def title_case_snippet(value: str) -> str:
    return value[:1].upper() + value[1:]


_TRAILING_PUNCT_RE = re.compile(r"[,;:\-–—\s]+$")
# Mots orphelins en fin de meta signalant une phrase tronquée : conjonctions, pronoms,
# relatifs, déterminants et prépositions courtes qui ne peuvent pas clore une phrase.
_TRAILING_COORD_RE = re.compile(
    r"\s+(et|ou|mais|donc|or|ni|car|pour|dont|que|qui"
    r"|lesquels|lesquelles|elles|ils|elle|il|leur|leurs|y|en"
    r"|le|la|les|l|un|une|des|du|au|aux|de|d|ce|cet|cette|ces"
    r"|à|par|sur|sous|dans|avec|sans|vers|entre)$",
    re.I,
)

def trim_to_length(value: str, max_length: int) -> str:
    """Coupe au dernier mot complet <= max_length.

    - Supprime toute ponctuation orpheline (virgule, point-virgule, tiret) en fin.
    - Supprime les mots orphelins en fin (conjonctions, pronoms, déterminants, prépositions)
      qui signalent une phrase tronquée — appliqué même si le texte n'est pas tronqué.
    - N'ajoute jamais de point ; la ponctuation finale est gérée par l'appelant.
    """
    if len(value) <= max_length:
        # Nettoyer les mots orphelins même sans troncature (meta template trop proche de la limite)
        cleaned = value
        for _ in range(4):
            prev = cleaned
            cleaned = _TRAILING_COORD_RE.sub("", cleaned)
            cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
            if cleaned == prev:
                break
        return cleaned or value
    # Couper au dernier espace avant max_length+1 (pour ne pas couper en milieu de mot)
    shortened = value[: max_length + 1].rsplit(" ", 1)[0]
    # Supprimer ponctuation et mots orphelins traînants (itéré jusqu'à stabilisation)
    for _ in range(4):
        prev = shortened
        shortened = _TRAILING_PUNCT_RE.sub("", shortened)
        shortened = _TRAILING_COORD_RE.sub("", shortened)
        if shortened == prev:
            break
    return shortened or value[:max_length].rstrip()


def dedupe_tokens(text: str) -> str:
    """Supprime les répétitions de mots significatifs (hors stopwords français).

    Garde la première occurrence de chaque token non-stopword. Les stopwords
    peuvent se répéter librement. L'ordre des mots est conservé.
    """
    words = text.split()
    seen: set[str] = set()
    result: list[str] = []
    for word in words:
        # Normaliser pour la comparaison uniquement (conserver casse originale)
        key = strip_accents(word.lower()).rstrip(".,;:!?")
        if key in _FR_STOPWORDS or key not in seen:
            result.append(word)
            if key not in _FR_STOPWORDS:
                seen.add(key)
    return " ".join(result)


def sanitize_snippet_text(value: str) -> str:
    cleaned = value
    replacements = {
        "conseils et points clés": "repères pratiques",
        "conseils et points cles": "repères pratiques",
        "guide clair": "réponse précise",
        "points clés": "repères utiles",
        "points cles": "repères utiles",
        "points à vérifier": "critères utiles",
        "points a verifier": "critères utiles",
        "Découvrez les informations essentielles": "Retrouvez les informations utiles",
        "conseils pour avancer plus simplement": "repères pour décider quoi faire ensuite",
        "promesse plus concrète": "angle plus précis",
        "promesse plus concrete": "angle plus précis",
    }
    for bad, good in replacements.items():
        cleaned = re.sub(re.escape(bad), good, cleaned, flags=re.I)
    return cleaned


def has_specific_snippet_angle(title: str, query: str) -> bool:
    normalized_title = strip_accents(title).lower()
    normalized_query = strip_accents(clean_query_for_snippet(query)).lower()
    if not normalized_title or normalized_title == normalized_query:
        return False
    return any(
        marker in normalized_title
        for marker in (
            "critere",
            "avis",
            "choix",
            "methode",
            "erreur",
            "regle",
            "niveau",
            "inscription",
            "comparatif",
            "profil",
            "style",
            "reussir",
            "controle",
            "points",
        )
    )

# ---------------------------------------------------------------------------
# Helper privé exclusif à generate_page_recommendation
# ---------------------------------------------------------------------------

def _dominant_signal(analysis: GSCPageAnalysis | None) -> str:
    """Identifie le signal dominant pour orienter la recommandation."""
    if analysis is None:
        return "generic"
    position_bucket = max(1, min(20, round(analysis.position)))
    expected = EXPECTED_CTR_BY_POSITION.get(position_bucket, 0.015)
    if analysis.cannibalization_group_id:
        return "cannibalization"
    if analysis.position <= 10 and analysis.ctr < expected * 0.5:
        return "low_ctr"
    if 10 < analysis.position <= 20 and analysis.impressions >= 100:
        return "low_position"
    if analysis.business_value == "high" and analysis.ctr < 0.01:
        return "business_underused"
    return "generic"

# ---------------------------------------------------------------------------
# Fonctions extraites (dans l'ordre prescrit)
# ---------------------------------------------------------------------------

def priority_for_page(analysis: GSCPageAnalysis) -> str:
    """Retourne HIGH, MEDIUM, LOW ou DEAD selon le score d'opportunité de la page.

    Garde-fou position (bug 2B-1) :
    - position > POSITION_CAP_HIGH (30) ET priority == HIGH → force MEDIUM.
      Une page hors top 30 ne génère pas de gain rapide via réécriture title/meta.
    - position > POSITION_CAP_LOW (50) ET priority != DEAD → force LOW.
      Au-delà de la position 50 la page n'est pas dans la SERP utile.
    """
    if is_dead_gsc_page(analysis):
        return "DEAD"
    score = analysis.opportunity_score or int(round(analysis.score))
    if score >= 60:
        priority = "HIGH"
    elif score >= 40:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    # Garde-fou position : couche additive, ne remplace pas la logique DEAD
    if analysis.position > POSITION_CAP_LOW:
        priority = "LOW"
    elif analysis.position > POSITION_CAP_HIGH and priority == "HIGH":
        priority = "MEDIUM"

    return priority


def diagnostic_for_page(item: GSCPageAnalysis) -> str:
    """Retourne le texte du champ Constat selon le profil position/CTR de la page (bug 2B-2).

    Sélectionne parmi 5 templates selon les règles explicites suivantes :
    1. position < 10 + CTR sous médiane → CTR à optimiser via title/meta
    2. position < 10 + CTR conforme → enrichissement éditorial pour gagner des positions
    3. position 10-20 + impressions élevées → volume visible mais hors top 10
    4. position 20-30 → visible mais trop bas pour capter du trafic
    5. position > 30 → hors SERP utile
    DEAD capturé en premier.
    """
    if is_dead_gsc_page(item):
        return "La page ne capte presque pas de trafic et doit être arbitrée plutôt qu'optimisée à l'aveugle."

    expected = expected_ctr_for_position(item.position)
    norm_low = ctr_norm_lower_bound_for_position(item.position)

    if 10 <= item.position <= 20 and item.ctr >= norm_low:
        return (
            "La page reste hors top 10, mais son CTR actuel se situe déjà dans la fourchette attendue "
            "pour cette position. La marge de clic immédiate est limitée ; le levier prioritaire est "
            "l'enrichissement du contenu et le maillage interne pour franchir le seuil."
        )

    if item.position < 10 and item.ctr >= norm_low:
        return (
            "Le CTR actuel se situe déjà dans la fourchette attendue pour cette position. "
            "La marge de clic immédiate est limitée ; le gain prioritaire vient plutôt d'un enrichissement "
            "du contenu, d'un maillage interne plus fort ou d'un suivi GSC après test."
        )

    if item.position < 10:
        if item.ctr < expected * CTR_TOLERANCE:
            return (
                "La page est déjà bien positionnée (top 10) mais son CTR reste sous la médiane attendue "
                "à cette position. Le gain probable vient d'une réécriture du résultat Google (title + meta)."
            )
        return (
            "La page est bien positionnée et son CTR est conforme à la médiane attendue à cette position. "
            "Le gain prioritaire vient d'un enrichissement éditorial pour gagner des positions supplémentaires."
        )

    if 10 <= item.position <= 20 and item.impressions >= IMPRESSIONS_THRESHOLD_HIGH:
        return (
            "La page reçoit un volume d'impressions significatif mais reste juste hors du top 10. "
            "Le levier prioritaire est le contenu et le maillage interne pour franchir le seuil."
        )

    if 20 < item.position <= 30:
        return (
            "La page est visible dans Google mais positionnée trop bas pour capter du trafic. "
            "Renforcement éditorial et maillage requis avant d'optimiser le résultat Google."
        )

    if item.position > 30:
        return (
            "La page n'est pas dans la SERP visible. Une réécriture title/meta seule ne suffira pas "
            "— refonte de fond ou désindexation à arbitrer."
        )

    # Cas 10-20 avec impressions faibles
    return (
        "La page est visible mais manque probablement de profondeur ou de soutien interne pour passer un cap."
    )


def generate_page_recommendation(
    page: str,
    main_queries: list[str] | None,
    page_type: str,
    business_value: str,
    analysis: GSCPageAnalysis | None = None,
) -> str:
    """Retourne le texte de l'action recommandée spécifique pour une page."""
    query = (main_queries or [keyword_phrase_from_url(page)])[0] or keyword_phrase_from_url(page)
    lower = strip_accents(f"{page} {query} {page_type}").lower()
    level = detect_tournament_level(page, query)

    # — Contenu spécifique au domaine padel (prioritaire) —
    if "tournoi" in lower and level:
        return tournament_recommendation(level, page, query)
    if "tournoi" in lower:
        return "Structurer la page tournoi autour du niveau attendu, du format, de l'inscription et des repères utiles, sans afficher de niveau précis tant qu'il n'est pas fiable."
    if "tenir-raquette-padel" in lower:
        return "Ajouter des visuels de prise, une section sur la prise continentale, les erreurs fréquentes et des liens vers coups de base, service et raquette débutant."
    if "pressurisateur" in lower:
        return "Renforcer l'intention achat : critères de choix, modèles recommandés, limites réelles, puis liens vers balles padel et comparaisons Decathlon/Amazon si pertinentes."
    if "chaussures-padel" in lower and "test-chaussures" not in lower and "test-chassures" not in lower:
        return "Structurer la page autour des critères d'achat : semelle, maintien, amorti, surface et morphologie, puis lier vers les tests chaussures Kuikma, Asics, Nox et Joma."
    if "raquette-padel" in lower and "/test-" not in lower and "test-raquette" not in lower:
        return "Recentrer la page sur l'aide au choix : tableau par niveau, forme, mousse, poids et budget, puis liens vers les tests et comparatifs raquettes."
    if "/test-" in lower or "test-" in lower:
        return "Ajouter un verdict en haut de page, les profils de joueurs concernés, les limites du produit et des liens vers la page catégorie ou le comparatif correspondant."
    if "sac-padel" in lower or "balles-padel" in lower:
        return "Transformer la page en aide au choix avec critères d'achat, cas d'usage, erreurs fréquentes et liens vers les tests ou produits associés."

    # — Recommandation conditionnelle sur signal dominant —
    action_type = analysis.action_type if analysis is not None else ""
    signal = _dominant_signal(analysis)

    if action_type == "cannibalization" or signal == "cannibalization":
        canon = analysis.cannibalization_recommendation if analysis is not None else ""
        return canon or f"Clarifier le rôle de cette URL dans le cluster « {query} » et différencier l'intention principale vs les pages sœurs avant toute optimisation."

    if signal == "low_ctr":
        return (
            f"Le CTR est anormalement bas pour la position actuelle sur « {query} » : "
            f"réécrire le title autour du bénéfice concret, renforcer la meta avec un angle distinctif et vérifier si un featured snippet ou un PAA domine la SERP."
        )

    if signal == "low_position":
        return (
            f"La page est visible mais positionnée trop bas pour capter du trafic sur « {query} » : "
            f"enrichir le contenu avec une FAQ, approfondir les sous-intentions, ajouter du maillage interne entrant depuis les pages du même cluster."
        )

    if signal == "business_underused":
        return (
            f"La page cible « {query} » mais convertit peu : ajouter un bloc décisionnel (verdict, critères, limites), "
            f"des liens vers les pages commerciales proches et un appel à l'action clair pour transformer la visibilité en clics qualifiés."
        )

    if action_type == "snippet":
        return f"Réécrire le title autour de « {query} », puis faire porter la meta sur le bénéfice exact de la page et les éléments consultables dès l'arrivée."
    if action_type == "internal linking":
        return f"Créer des liens internes vers cette page depuis les contenus du même cluster avec des ancres proches de « {query} », puis renforcer les sections qui répondent aux sous-intentions visibles."
    if business_value == "high":
        return "Ajouter critères de décision, limites, comparaisons et liens de monétisation utiles afin de transformer la visibilité Google en clics business qualifiés."
    return "Garder en suivi GSC et prioriser seulement si les impressions ou la position progressent."


def build_target_metric(item: GSCPageAnalysis) -> str:
    """Formate la cible chiffrée CTR + gain estimé pour une page prioritaire."""
    if item.impressions < 10:
        return ""
    result = compute_target_metric(item.position, item.ctr, item.impressions)
    gain_low = int(result["gain_low"])
    gain_high = int(result["gain_high"])
    ctr_low_target = float(result["ctr_low_target"])
    ctr_high_target = float(result["ctr_high_target"])
    pos_rounded = int(result["pos_rounded"])
    target_pos = int(result["target_pos"])

    if gain_high <= 0:
        return ""
    ctr_current_pct = format_percent(item.ctr)
    ctr_low_pct = format_percent(ctr_low_target)
    ctr_high_pct = format_percent(ctr_high_target)
    if gain_low == 0:
        return (
            f"CTR actuel {ctr_current_pct} → cible {ctr_low_pct}–{ctr_high_pct} "
            f"(médiane pos. {pos_rounded} / P75 pos. {target_pos}). "
            f"Gain estimé : jusqu'à +{format_number(gain_high)} clics/mois sous 6-8 semaines."
        )
    return (
        f"CTR actuel {ctr_current_pct} → cible {ctr_low_pct}–{ctr_high_pct} "
        f"(médiane pos. {pos_rounded} / P75 pos. {target_pos}). "
        f"Gain estimé : +{format_number(gain_low)} à +{format_number(gain_high)} clics/mois sous 6-8 semaines."
    )


def generate_snippet_recommendation(
    page: str,
    main_query: str,
    page_type: str = "",
    business_value: str = "",
    gsc_data: dict[str, Any] | None = None,
    intent: str = "",
) -> dict[str, str]:
    """Génère une proposition de title + meta pour une page snippets, avec validation de longueur."""
    query = clean_query_for_snippet(main_query or keyword_phrase_from_url(page))
    lower = strip_accents(f"{page} {query} {page_type} {business_value} {intent}").lower()
    level = detect_tournament_level(page, query)
    if level:
        desc, focus = _TOURNAMENT_LEVEL_DESCRIPTIONS.get(
            level, ("joueurs de ce niveau", "le format, le niveau requis et les conditions d'inscription")
        )
        # Choisir un angle différent selon les requêtes secondaires disponibles
        gsc = gsc_data or {}
        secondary = [str(q) for q in gsc.get("secondary_queries", [])[:5]]
        secondary_text = strip_accents(" ".join(secondary)).lower()
        if "points" in secondary_text or "classement" in secondary_text:
            title = f"Tournoi {level} : points, classement et niveau requis"
            meta = (f"Retrouvez les points distribués en {level}, le classement FFT associé et les repères de niveau "
                    f"pour les {desc}. Inclut les conditions d'inscription et les variantes fréquentes.")
        elif "inscription" in secondary_text or "format" in secondary_text:
            title = f"Tournoi {level} : format, inscription et repères pratiques"
            meta = (f"Tout ce que les {desc} doivent savoir avant de s'inscrire en {level} : "
                    f"{focus}. Format tableau, délais et FAQ courte.")
        else:
            title = f"Tournoi {level} padel : niveau, points et repères clés"
            meta = (f"Recentré sur l'intention principale des {desc} : réponse directe sur {focus}, "
                    f"FAQ courte et liens vers les niveaux adjacents.")
    elif "par 4" in lower or "par-4" in lower:
        title = "Par 4 au padel : réussir le smash qui sort du terrain"
        meta = "Placement, hauteur de balle, timing et erreurs fréquentes : les repères pour tenter un par 4 plus proprement en match."
    elif "tenir" in lower and "raquette" in lower:
        title = "Comment tenir sa raquette de padel sans se crisper"
        meta = "Placement de la main, prise continentale, erreurs fréquentes : les bases pour mieux tenir votre raquette et gagner en contrôle."
    elif "agustin" in lower or "tapia" in lower:
        title = "Agustín Tapia : profil, palmarès et style de jeu"
        meta = "Découvrez le parcours d'Agustín Tapia, son style sur le circuit pro, ses forces en match et les repères clés pour suivre sa carrière."
    elif "pressurisateur" in lower:
        title = "Meilleur pressurisateur de balles de padel : comparatif"
        meta = "Comparez les pressurisateurs utiles pour prolonger la durée de vie des balles, avec critères d'achat, limites et conseils pratiques."
    elif "chaussure" in lower:
        title = "Chaussures de padel : modèles, critères et erreurs à éviter"
        meta = "Semelle, maintien, confort, surface de jeu : les critères à vérifier avant de choisir une paire de chaussures de padel."
    elif any(term in lower for term in ("meilleur", "comparatif", "avis", "test", "raquette", "chaussure", "balle", "sac")):
        title = title_case_snippet(f"{query} : critères, avis et choix utiles")
        meta = f"Critères de choix, limites et profils adaptés : ce qu'il faut savoir sur {query} avant de décider."
    elif lower.startswith("comment") or "comment " in lower:
        title = title_case_snippet(f"{query} : méthode simple et erreurs à éviter")
        meta = f"Retrouvez les gestes, repères et erreurs fréquentes pour {query.replace('comment ', '')}, avec une approche concrète à appliquer sur le terrain."
    elif "tournoi" in lower:
        title = title_case_snippet(f"{query} : règles, niveau et inscription")
        meta = f"Faites le point sur {query} : format, niveau attendu, inscription, points et repères utiles avant de vous engager."
    else:
        return {"title": "", "meta": "", "reason": ""}
    # Bug 2B-5 : déduplication tokens avant troncature, limites 60/155, ponctuation finale propre
    title = sanitize_snippet_text(trim_to_length(dedupe_tokens(title), 60))
    meta = sanitize_snippet_text(trim_to_length(dedupe_tokens(meta), 155))
    # Garantir ponctuation finale cohérente : jamais virgule/point-virgule en fin
    title = re.sub(r"[,;]+$", "", title).rstrip()
    meta = re.sub(r"[,;]+$", "", meta).rstrip()
    if not has_specific_snippet_angle(title, query):
        return {"title": "", "meta": "", "reason": ""}
    if len(meta) < 120:
        suffix = " Une synthèse pratique pour décider quoi faire ensuite."
        # N'ajouter le suffix que si le résultat reste dans les 155 chars,
        # sinon la troncature couperait en milieu de phrase.
        if len(meta) + len(suffix) <= 155:
            meta = sanitize_snippet_text(f"{meta}{suffix}")
        meta = re.sub(r"[,;]+$", "", meta).rstrip()
    return {
        "title": title,
        "meta": meta,
        "reason": f"Faire correspondre le résultat Google à l'intention « {query} » avec un angle précis et vérifiable.",
    }


def slug_prefix(url: str, depth: int = 1) -> str:
    """Retourne le préfixe de slug à profondeur N pour grouper les pages similaires (bug 2B-3).

    Extrait le dernier segment significatif du path et prend les `depth` derniers tokens
    séparés par '-'. Ex: '/agustin-tapia-joueur-padel/' → 'joueur-padel' (depth=2).
    Utilisé pour la signature de cluster : les pages joueurs partagent le même suffixe.
    """
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return ""
    last_segment = path.split("/")[-1]
    tokens = [t for t in re.split(r"[-_]+", last_segment) if t and not t.isdigit()]
    # Prendre les `depth` derniers tokens comme suffixe distinctif de profil
    return "-".join(tokens[-depth:]) if tokens else ""


# Mots thématiques padel : présents dans les slugs de pages de contenu mais PAS dans les noms propres.
# Un slug dont les 2 premiers tokens sont absents de ce lexique = slug de personnalité.
_PADEL_THEMATIC_TOKENS: frozenset[str] = frozenset({
    "tournoi", "raquette", "balle", "balles", "niveau", "niveaux", "classement",
    "chaussure", "chaussures", "padel", "regle", "regles", "grip", "prise",
    "technique", "tactique", "service", "smash", "vibora", "bajada", "bandeja",
    "poids", "perte", "fibre", "verre", "carbone", "foam", "eva", "pressurisateur",
    "cours", "terrain", "club", "federations", "arbitre", "coaching", "entrainement",
    "comment", "guide", "comparatif", "meilleur", "avis", "test", "tutoriel",
    "reussir", "progresser", "gagner", "apprendre", "tenir", "nettoyer",
    "quand", "changer", "choisir", "comparer",
})


def _is_personality_page(url: str) -> bool:
    """True si l'URL ressemble à une fiche biographique de joueur/joueuse de padel.

    Heuristique : slug se terminant par 'padel' ET les 2 premiers tokens du slug
    ne sont pas dans le lexique thématique padel (= probablement un prénom + nom).
    Couvre agustin-tapia-padel, fernando-belasteguin-padel, marta-ortega-padel,
    arturo-coello-joueur-padel, juan-lebron-padel, etc.
    """
    parsed = urlparse(url)
    last_segment = parsed.path.strip("/").split("/")[-1]
    tokens = [t for t in re.split(r"[-_]+", last_segment) if t and not t.isdigit()]
    if not tokens or tokens[-1] != "padel":
        return False
    # Les 2 premiers tokens doivent être absents du lexique thématique
    first_two = {strip_accents(t.lower()) for t in tokens[:2]}
    return not first_two.intersection(_PADEL_THEMATIC_TOKENS)


def _cluster_sig(page: "GSCPageAnalysis") -> tuple[str, str, str]:
    """Calcule la signature de cluster d'une page.

    Les pages de personnalité padel (*-padel où les premiers tokens sont un nom propre)
    partagent la clé canonique ("", "", "personnalite-padel") quel que soit leur
    action_type ou business_value — ce qui les regroupe toutes dans un même cluster.
    Pour les autres pages, la signature tripartite assure une granularité fine.
    """
    if _is_personality_page(page.url):
        return ("", "", "personnalite-padel")
    suffix = slug_prefix(page.url, depth=2)
    return (str(page.action_type or ""), str(page.business_value or ""), suffix)


def cap_top_priority_per_cluster(
    pages: list["GSCPageAnalysis"],
    max_per_cluster: int = MAX_PAGES_PER_CLUSTER,
) -> list["GSCPageAnalysis"]:
    """Limite à `max_per_cluster` le nombre de pages par cluster dans le top prioritaire (bug 2B-3).

    Cluster défini par _cluster_sig : signature complète sauf pour les groupes
    homogènes connus (ex : *-joueur-padel) où seul le slug suffix suffit.
    Les pages excédentaires voient leur priorité descendue d'un cran (HIGH→MEDIUM, MEDIUM→LOW).
    Les pages DEAD ne sont pas affectées.
    Les pages les mieux scorées (opportunity_score) sont conservées en priorité haute.
    """
    _DOWNGRADE = {"HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}

    cluster_counts: dict[tuple[str, str, str], int] = {}
    result: list[GSCPageAnalysis] = []

    # Trier par score décroissant pour traiter d'abord les meilleures pages
    sorted_pages = sorted(pages, key=lambda p: p.opportunity_score or 0, reverse=True)

    for page in sorted_pages:
        if page.priority == "DEAD":
            result.append(page)
            continue
        sig = _cluster_sig(page)
        count = cluster_counts.get(sig, 0)
        if count >= max_per_cluster:
            downgraded = dataclass_replace(page, priority=_DOWNGRADE.get(page.priority, page.priority))
            result.append(downgraded)
        else:
            cluster_counts[sig] = count + 1
            result.append(page)

    # Restaurer l'ordre d'origine (par position dans sorted_pages → par url)
    original_order = {p.url: i for i, p in enumerate(pages)}
    result.sort(key=lambda p: original_order.get(p.url, 0))
    return result


def is_resolvable_target(target_url: str) -> bool:
    """True si l'URL cible est exploitable (non vide, non placeholder) (bug 2B-4)."""
    stripped = (target_url or "").strip()
    if not stripped:
        return False
    # Rejeter les valeurs placeholder connues
    placeholders = {"à valider", "a valider", "tbd", "n/a", "#", "/"}
    return stripped.lower() not in placeholders


def resolve_target_label(target_url: str, _: Callable[[str], str] = str) -> str:
    """Retourne l'URL compacte pour affichage. Lève ValueError si non résolvable (bug 2B-4).

    Le paramètre _ est la fonction de traduction (gsc_gettext(lang)) à passer par l'appelant
    pour éviter tout import circulaire avec gsc.py. Par défaut str() = pas de traduction.
    """
    if not is_resolvable_target(target_url):
        raise ValueError(f"URL cible non résolvable : {target_url!r}")
    return compact_url_for_display(target_url)
