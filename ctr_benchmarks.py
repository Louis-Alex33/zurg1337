"""Benchmarks CTR par position pour le calcul de potentiel.

Source : moyennes consolidées de benchmarks publics (AWR, Sistrix, Backlinko).
À mettre à jour annuellement.
"""
from __future__ import annotations

# CTR médian observé par position (toutes niches confondues)
CTR_BY_POSITION_MEDIAN: dict[int, float] = {
    1: 0.275, 2: 0.155, 3: 0.110, 4: 0.080, 5: 0.060,
    6: 0.045, 7: 0.035, 8: 0.025, 9: 0.020, 10: 0.015,
    11: 0.012, 12: 0.010, 13: 0.009, 14: 0.008, 15: 0.007,
    16: 0.006, 17: 0.005, 18: 0.005, 19: 0.004, 20: 0.004,
}

# CTR au 75e percentile (pages bien optimisées à même position)
CTR_BY_POSITION_P75: dict[int, float] = {
    1: 0.40, 2: 0.22, 3: 0.16, 4: 0.11, 5: 0.085,
    6: 0.065, 7: 0.05, 8: 0.038, 9: 0.030, 10: 0.022,
    11: 0.018, 12: 0.015, 13: 0.013, 14: 0.011, 15: 0.010,
    16: 0.009, 17: 0.008, 18: 0.007, 19: 0.006, 20: 0.005,
}


def ctr_median(position: float) -> float:
    bucket = max(1, min(20, round(position)))
    return CTR_BY_POSITION_MEDIAN.get(bucket, 0.004)


def ctr_p75(position: float) -> float:
    bucket = max(1, min(20, round(position)))
    return CTR_BY_POSITION_P75.get(bucket, 0.005)


def ctr_target_position(current_position: float) -> float:
    """Position cible pour le calcul du potentiel haut : -2 si > 5, sinon 3."""
    if current_position > 5:
        return max(1.0, current_position - 2.0)
    return 3.0


def potential_range(impressions: float, ctr_current: float, position: float) -> tuple[int, int]:
    """Retourne (gain_bas, gain_haut) en clics pour une page donnée.

    gain_bas  = impressions × (CTR médian position actuelle - CTR actuel)
    gain_haut = impressions × (CTR P75 position cible - CTR actuel)
    """
    med = ctr_median(position)
    target_pos = ctr_target_position(position)
    p75 = ctr_p75(target_pos)

    low = round(impressions * max(0.0, med - ctr_current))
    high = round(impressions * max(0.0, p75 - ctr_current))
    high = max(low, high)
    return low, high
