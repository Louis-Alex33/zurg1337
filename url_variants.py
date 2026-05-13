"""Détection de variantes d'URL quasi-identiques (typos, redirections 301 résiduelles).

Cas typique : une redirection 301 posée après correction d'une faute de frappe dans un slug.
Les anciennes données GSC persistent 3-6 mois. Ce module détecte ces paires sans fetch HTTP.
"""
from __future__ import annotations

import difflib
import re
from urllib.parse import urlparse


def detect_url_variants(
    urls: list[str],
    threshold_ratio: float = 0.92,
) -> list[tuple[str, str, float]]:
    """Détecte les paires d'URLs quasi-identiques (typos, variantes mineures).

    Retourne une liste de tuples (url_a, url_b, similarity_ratio) où :
    - similarity_ratio >= threshold_ratio
    - même domaine et même profondeur de path
    - différence portée sur un seul segment de slug
    - ratio calculé sur ce segment uniquement (pas sur l'URL complète)
    - longueur du segment commun >= 8 caractères (évite /p-1/ vs /p-2/)
    """
    parsed = [(url, _parse_url(url)) for url in urls]
    results: list[tuple[str, str, float]] = []
    seen: set[frozenset[str]] = set()

    for i, (url_a, (domain_a, segments_a)) in enumerate(parsed):
        for j, (url_b, (domain_b, segments_b)) in enumerate(parsed):
            if j <= i:
                continue
            pair_key = frozenset({url_a, url_b})
            if pair_key in seen:
                continue
            if domain_a != domain_b:
                continue
            if len(segments_a) != len(segments_b):
                continue
            # Trouver les segments qui diffèrent
            differing = [
                (seg_a, seg_b)
                for seg_a, seg_b in zip(segments_a, segments_b)
                if seg_a != seg_b
            ]
            # Un seul segment différent
            if len(differing) != 1:
                continue
            seg_a, seg_b = differing[0]
            if _has_discriminating_numeric_delta(seg_a, seg_b):
                continue
            # Le segment commun doit être assez long
            min_len = min(len(seg_a), len(seg_b))
            if min_len < 8:
                continue
            ratio = difflib.SequenceMatcher(None, seg_a, seg_b).ratio()
            if ratio >= threshold_ratio:
                seen.add(pair_key)
                results.append((url_a, url_b, ratio))

    return results


def _parse_url(url: str) -> tuple[str, list[str]]:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    segments = [s for s in parsed.path.strip("/").split("/") if s]
    return domain, segments


def _split_slug_tokens(segment: str) -> list[str]:
    return [token for token in re.split(r"[-_]+", segment.lower()) if token]


def _token_numeric_signature(token: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"([a-z]+)?(\d+)([a-z]+)?", token)
    if not match:
        return None
    prefix, number, suffix = match.groups()
    return f"{prefix or ''}#{suffix or ''}", number


def _has_discriminating_numeric_delta(seg_a: str, seg_b: str) -> bool:
    """Reject variant matches where a numeric slug token is the identifier.

    Example: tournoi-padel-p100, tournoi-padel-p1000 and tournoi-padel-p1500
    are distinct tournament levels, not typo variants.
    """
    tokens_a = _split_slug_tokens(seg_a)
    tokens_b = _split_slug_tokens(seg_b)
    if len(tokens_a) != len(tokens_b):
        return False
    for token_a, token_b in zip(tokens_a, tokens_b):
        if token_a == token_b:
            continue
        sig_a = _token_numeric_signature(token_a)
        sig_b = _token_numeric_signature(token_b)
        if sig_a and sig_b and sig_a[0] == sig_b[0] and sig_a[1] != sig_b[1]:
            return True
    return False


def merge_variant_pair_metrics(
    metrics_a: dict[str, object],
    metrics_b: dict[str, object],
) -> dict[str, object]:
    """Fusionne les métriques GSC de deux URLs variantes.

    Additionne clics et impressions, calcule une position pondérée par les impressions.
    Retourne un dict avec clics, impressions, position, ctr fusionnés.
    """
    clicks_a = float(metrics_a.get("clicks") or 0)
    clicks_b = float(metrics_b.get("clicks") or 0)
    impr_a = float(metrics_a.get("impressions") or 0)
    impr_b = float(metrics_b.get("impressions") or 0)
    pos_a = float(metrics_a.get("position") or 0)
    pos_b = float(metrics_b.get("position") or 0)

    total_clicks = clicks_a + clicks_b
    total_impr = impr_a + impr_b
    # Position moyenne pondérée par impressions
    if total_impr > 0:
        avg_pos = (pos_a * impr_a + pos_b * impr_b) / total_impr
    else:
        avg_pos = (pos_a + pos_b) / 2 if (pos_a or pos_b) else 0.0

    return {
        "clicks": total_clicks,
        "impressions": total_impr,
        "position": avg_pos,
        "ctr": (total_clicks / total_impr) if total_impr > 0 else 0.0,
    }


def canonical_url_from_pair(url_a: str, url_b: str) -> str:
    """Retourne l'URL canonique d'une paire de variantes.

    Heuristique : l'URL la plus longue est retenue comme canonique.
    Justification : la correction d'une typo ajoute généralement un caractère
    (ex. "chassures" -> "chaussures"), donc la version corrigée est plus longue.
    """
    return url_a if len(url_a) >= len(url_b) else url_b
