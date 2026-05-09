"""Test de stabilité post-2B — baseline après correction des 6 bugs métier.

Vérifie que le rapport HTML produit par gsc.py + gsc_rules.py est strictement
identique octet-pour-octet au baseline post-2B capturé après la correction des
bugs de l'étape 2B (garde-fou position, constat dynamique, cap cluster,
filtrage cibles non résolues, validation snippets, sync plan d'action).

Le rapport de référence est stocké dans tests/fixtures/baseline_report.html.
Ce baseline remplace le baseline pré-2B (archivé dans baseline_report_pre_2B.html).
"""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASELINE_HTML = FIXTURES_DIR / "baseline_report.html"

CURRENT_CSV = str(FIXTURES_DIR / "pages_recent.csv")
PREVIOUS_CSV = str(FIXTURES_DIR / "pages_old.csv")
QUERIES_CSV = str(FIXTURES_DIR / "queries.csv")


class TestHTMLPost2BStability(unittest.TestCase):
    def test_html_output_identical_to_post_2B_baseline(self) -> None:
        """Le rapport régénéré doit être octet-pour-octet identique au baseline post-2B."""
        self.assertTrue(
            BASELINE_HTML.exists(),
            f"Baseline post-2B manquant : {BASELINE_HTML}. Régénérez-le après toute modification.",
        )
        from gsc import run_gsc_analysis

        baseline = BASELINE_HTML.read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            out_html = tmp_path / "gsc_report.html"
            run_gsc_analysis(
                current_csv=CURRENT_CSV,
                previous_csv=PREVIOUS_CSV,
                queries_csv=QUERIES_CSV,
                output_csv=str(tmp_path / "report.csv"),
                output_html=str(out_html),
                site_name="BaselineTest",
                mode="full",
            )
            regenerated = out_html.read_bytes()

        baseline_md5 = hashlib.md5(baseline).hexdigest()
        regen_md5 = hashlib.md5(regenerated).hexdigest()

        if baseline != regenerated:
            diff_byte = next(
                (i for i, (a, b) in enumerate(zip(baseline, regenerated)) if a != b),
                min(len(baseline), len(regenerated)),
            )
            ctx_b = baseline[max(0, diff_byte - 80): diff_byte + 80].decode("utf-8", "replace")
            ctx_r = regenerated[max(0, diff_byte - 80): diff_byte + 80].decode("utf-8", "replace")
            self.fail(
                f"HTML non identique au baseline post-2B (tailles : {len(baseline)} vs {len(regenerated)}, "
                f"md5 : {baseline_md5} vs {regen_md5}).\n"
                f"Premier octet différent à l'index {diff_byte}.\n"
                f"Contexte baseline : {ctx_b!r}\n"
                f"Contexte régénéré : {ctx_r!r}"
            )


if __name__ == "__main__":
    unittest.main()
