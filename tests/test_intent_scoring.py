from __future__ import annotations

import csv
import os
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from prospect_machine.intent.post_age import compute_post_age_score
from prospect_machine.intent.wayback import (
    _linear_slope,
    _quarter_boundaries,
    compute_wayback_score,
)
from prospect_machine.intent.whois_age import compute_whois_score
from prospect_machine.intent.ga_detect import compute_ga_obsolete_score, detect_ga_tags
from prospect_machine.intent.signals import IntentSignals


# ---------------------------------------------------------------------------
# post_age.py
# ---------------------------------------------------------------------------

class TestPostAgeScore:
    def test_inactive_site_scores_1(self) -> None:
        old_date = (date.today() - timedelta(days=400)).isoformat()
        age, score = compute_post_age_score(old_date, inactive_days=180)
        assert age is not None and age >= 400
        assert score == 1.0

    def test_very_recent_scores_near_0(self) -> None:
        recent = (date.today() - timedelta(days=5)).isoformat()
        age, score = compute_post_age_score(recent, inactive_days=180)
        assert age == 5
        assert score < 0.05

    def test_exactly_at_threshold_scores_1(self) -> None:
        threshold_date = (date.today() - timedelta(days=180)).isoformat()
        _, score = compute_post_age_score(threshold_date, inactive_days=180)
        assert score == pytest.approx(1.0)

    def test_empty_string_returns_none_zero(self) -> None:
        age, score = compute_post_age_score("")
        assert age is None
        assert score == 0.0

    def test_invalid_date_returns_none_zero(self) -> None:
        age, score = compute_post_age_score("not-a-date")
        assert age is None
        assert score == 0.0

    def test_score_clamped_to_1(self) -> None:
        very_old = (date.today() - timedelta(days=3000)).isoformat()
        _, score = compute_post_age_score(very_old, inactive_days=180)
        assert score == 1.0

    def test_score_between_0_and_1_for_mid_age(self) -> None:
        mid = (date.today() - timedelta(days=90)).isoformat()
        _, score = compute_post_age_score(mid, inactive_days=180)
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# wayback.py
# ---------------------------------------------------------------------------

class TestLinearSlope:
    def test_declining_series_negative_slope(self) -> None:
        assert _linear_slope([100, 80, 60, 40, 20]) < 0

    def test_growing_series_positive_slope(self) -> None:
        assert _linear_slope([10, 20, 30, 40, 50]) > 0

    def test_flat_series_zero_slope(self) -> None:
        assert _linear_slope([5, 5, 5, 5]) == pytest.approx(0.0)

    def test_single_value_returns_zero(self) -> None:
        assert _linear_slope([42]) == 0.0


class TestQuarterBoundaries:
    def test_returns_n_quarters(self) -> None:
        bounds = _quarter_boundaries(date(2025, 6, 15), 8)
        assert len(bounds) == 8

    def test_ordered_oldest_first(self) -> None:
        bounds = _quarter_boundaries(date(2025, 6, 15), 4)
        for i in range(len(bounds) - 1):
            assert bounds[i][0] < bounds[i + 1][0]

    def test_no_gap_between_quarters(self) -> None:
        bounds = _quarter_boundaries(date(2025, 9, 1), 4)
        for i in range(len(bounds) - 1):
            assert (bounds[i + 1][0] - bounds[i][1]).days == 1


class TestWaybackScore:
    def test_declining_series_scores_high(self) -> None:
        _, score = compute_wayback_score([100, 80, 60, 40, 20, 10, 5, 2])
        assert score > 0.5

    def test_growing_series_scores_low(self) -> None:
        _, score = compute_wayback_score([2, 5, 10, 20, 40, 60, 80, 100])
        assert score == 0.0

    def test_flat_series_scores_zero(self) -> None:
        _, score = compute_wayback_score([50, 50, 50, 50])
        assert score == pytest.approx(0.0)

    def test_empty_returns_zero(self) -> None:
        slope, score = compute_wayback_score([])
        assert slope == 0.0 and score == 0.0

    def test_score_clamped_to_1(self) -> None:
        _, score = compute_wayback_score([1000, 0, 0, 0, 0, 0, 0, 0])
        assert score <= 1.0


class TestFetchWaybackQuarters:
    def test_returns_n_values(self) -> None:
        from prospect_machine.intent.wayback import fetch_wayback_quarters

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [["timestamp"], ["20240101120000"], ["20240202120000"]]

        mock_sess = MagicMock()
        mock_sess.get.return_value = mock_resp

        result = fetch_wayback_quarters("example.com", num_quarters=4, _session=mock_sess)
        assert len(result) == 4
        assert all(isinstance(c, int) for c in result)

    def test_network_error_returns_zeros(self) -> None:
        from prospect_machine.intent.wayback import fetch_wayback_quarters

        mock_sess = MagicMock()
        mock_sess.get.side_effect = Exception("network down")

        result = fetch_wayback_quarters("fail.com", num_quarters=4, _session=mock_sess)
        assert result == [0, 0, 0, 0]


# ---------------------------------------------------------------------------
# whois_age.py
# ---------------------------------------------------------------------------

class TestWhoisScore:
    def test_old_domain_stagnant_content_scores_high(self) -> None:
        # 10-year-old domain, last post 2 years ago → ratio = 5
        ratio, score = compute_whois_score(
            domain_age_years=10.0,
            last_post_age_days=730,
            stagnation_threshold=0.5,
        )
        assert ratio is not None and ratio > 1.0
        assert score > 0.0

    def test_young_domain_recent_content_scores_low(self) -> None:
        ratio, score = compute_whois_score(
            domain_age_years=0.5,
            last_post_age_days=10,
            stagnation_threshold=0.5,
        )
        assert score < 0.5

    def test_none_age_returns_zero(self) -> None:
        ratio, score = compute_whois_score(None, 100)
        assert ratio is None
        assert score == 0.0

    def test_none_post_age_returns_zero(self) -> None:
        ratio, score = compute_whois_score(5.0, None)
        assert score == 0.0

    def test_zero_post_age_does_not_raise(self) -> None:
        ratio, score = compute_whois_score(5.0, 0)
        assert score == 0.0


class TestFetchWhoisAge:
    def test_returns_age_years_from_creation_date(self) -> None:
        from prospect_machine.intent.whois_age import fetch_whois_age
        from datetime import datetime

        mock_w = MagicMock()
        mock_w.get = MagicMock(return_value=None)
        # python-whois returns an object with creation_date attribute
        mock_w.__class__ = object  # not a dict
        mock_w.creation_date = datetime(2015, 1, 1)

        with patch("prospect_machine.intent.whois_age.whois.whois", return_value=mock_w):
            age = fetch_whois_age("old.com")

        assert age is not None
        assert age > 9.0  # at least 9 years since 2015

    def test_whois_exception_returns_none(self) -> None:
        from prospect_machine.intent.whois_age import fetch_whois_age

        with patch("prospect_machine.intent.whois_age.whois.whois", side_effect=Exception("timeout")):
            age = fetch_whois_age("broken.com")

        assert age is None


# ---------------------------------------------------------------------------
# ga_detect.py
# ---------------------------------------------------------------------------

class TestDetectGaTags:
    def test_detects_ua_tag(self) -> None:
        html = "<script>gtag('config', 'UA-12345-1');</script>"
        has_ua, has_ga4 = detect_ga_tags(html)
        assert has_ua is True
        assert has_ga4 is False

    def test_detects_ga4_tag(self) -> None:
        html = "<script>gtag('config', 'G-ABCDEF1234');</script>"
        has_ua, has_ga4 = detect_ga_tags(html)
        assert has_ua is False
        assert has_ga4 is True

    def test_detects_both(self) -> None:
        html = "UA-99999-1 and G-XYZ123456"
        has_ua, has_ga4 = detect_ga_tags(html)
        assert has_ua is True
        assert has_ga4 is True

    def test_no_tags(self) -> None:
        html = "<html><body>No analytics here</body></html>"
        has_ua, has_ga4 = detect_ga_tags(html)
        assert has_ua is False
        assert has_ga4 is False


class TestComputeGaObsoleteScore:
    def test_ua_without_ga4_scores_1(self) -> None:
        assert compute_ga_obsolete_score(True, False) == 1.0

    def test_both_present_scores_0(self) -> None:
        assert compute_ga_obsolete_score(True, True) == 0.0

    def test_neither_scores_0(self) -> None:
        assert compute_ga_obsolete_score(False, False) == 0.0

    def test_only_ga4_scores_0(self) -> None:
        assert compute_ga_obsolete_score(False, True) == 0.0


class TestFetchGaSignals:
    def test_returns_tags_from_html(self) -> None:
        from prospect_machine.intent.ga_detect import fetch_ga_signals

        html = b"<script>UA-12345-1</script>"
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.iter_content.return_value = [html]

        mock_sess = MagicMock()
        mock_sess.get.return_value = mock_resp

        has_ua, has_ga4 = fetch_ga_signals("example.com", _session=mock_sess)
        assert has_ua is True
        assert has_ga4 is False

    def test_network_error_returns_false_false(self) -> None:
        from prospect_machine.intent.ga_detect import fetch_ga_signals

        mock_sess = MagicMock()
        mock_sess.get.side_effect = Exception("connection refused")

        has_ua, has_ga4 = fetch_ga_signals("down.com", _session=mock_sess)
        assert has_ua is False
        assert has_ga4 is False


# ---------------------------------------------------------------------------
# runner.py
# ---------------------------------------------------------------------------

class TestComputeIntentSignals:
    def _make_config(self) -> dict:
        return {
            "weights": {"post_age": 0.35, "wayback": 0.30, "whois": 0.20, "ga_obsolete": 0.15},
            "post_age_inactive_days": 180,
            "wayback_quarters": 4,
            "wayback_min_snapshots": 1,
            "whois_stagnation_ratio": 0.5,
        }

    def test_intent_score_between_0_and_1(self) -> None:
        from prospect_machine.intent.runner import compute_intent_signals

        old_date = (date.today() - timedelta(days=400)).isoformat()
        config = self._make_config()

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [["timestamp"]]  # 0 snapshots

        mock_w = MagicMock()
        mock_w.__class__ = object
        mock_w.creation_date = date(2010, 1, 1)

        with (
            patch("prospect_machine.intent.wayback.requests.Session") as mock_sess_cls,
            patch("prospect_machine.intent.whois_age.whois.whois", return_value=mock_w),
            patch("prospect_machine.intent.ga_detect.requests.Session") as mock_ga_sess_cls,
        ):
            mock_sess = MagicMock()
            mock_sess.get.return_value = mock_resp
            mock_sess_cls.return_value = mock_sess

            mock_ga_resp = MagicMock()
            mock_ga_resp.ok = True
            mock_ga_resp.iter_content.return_value = [b"UA-99999-1"]
            mock_ga_sess = MagicMock()
            mock_ga_sess.get.return_value = mock_ga_resp
            mock_ga_sess_cls.return_value = mock_ga_sess

            sig = compute_intent_signals("stagnant.fr", old_date, config)

        assert 0.0 <= sig.intent_score <= 1.0
        assert sig.last_post_age_days is not None and sig.last_post_age_days >= 400
        assert sig.ga_has_ua_tag is True

    def test_unknown_post_date_gives_zero_post_age(self) -> None:
        from prospect_machine.intent.runner import compute_intent_signals

        config = self._make_config()

        with (
            patch("prospect_machine.intent.wayback.requests.Session") as mock_sess_cls,
            patch("prospect_machine.intent.whois_age.whois.whois", side_effect=Exception("no whois")),
            patch("prospect_machine.intent.ga_detect.requests.Session") as mock_ga_sess_cls,
        ):
            mock_sess = MagicMock()
            mock_resp = MagicMock()
            mock_resp.ok = True
            mock_resp.json.return_value = [["timestamp"]]
            mock_sess.get.return_value = mock_resp
            mock_sess_cls.return_value = mock_sess

            mock_ga_resp = MagicMock()
            mock_ga_resp.ok = True
            mock_ga_resp.iter_content.return_value = [b""]
            mock_ga_sess = MagicMock()
            mock_ga_sess.get.return_value = mock_ga_resp
            mock_ga_sess_cls.return_value = mock_ga_sess

            sig = compute_intent_signals("unknown.fr", "", config)

        assert sig.post_age_score == 0.0
        assert sig.last_post_age_days is None


class TestRunIntentScoring:
    def _make_config(self) -> dict:
        return {
            "weights": {"post_age": 0.35, "wayback": 0.30, "whois": 0.20, "ga_obsolete": 0.15},
            "post_age_inactive_days": 180,
            "wayback_quarters": 4,
            "wayback_min_snapshots": 1,
            "whois_stagnation_ratio": 0.5,
        }

    def test_returns_one_result_per_row(self) -> None:
        from prospect_machine.intent.runner import run_intent_scoring

        rows = [
            {"domain": "a.fr", "last_post_date": ""},
            {"domain": "b.fr", "last_post_date": ""},
        ]
        config = self._make_config()

        with (
            patch("prospect_machine.intent.runner.fetch_wayback_quarters", return_value=[0, 0, 0, 0]),
            patch("prospect_machine.intent.runner.fetch_whois_age", return_value=None),
            patch("prospect_machine.intent.runner.fetch_ga_signals", return_value=(False, False)),
        ):
            results = run_intent_scoring(rows, config, concurrency=2)

        assert len(results) == 2
        assert {r.domain for r in results} == {"a.fr", "b.fr"}

    def test_crash_in_one_domain_does_not_stop_others(self) -> None:
        from prospect_machine.intent.runner import run_intent_scoring

        rows = [
            {"domain": "ok.fr", "last_post_date": ""},
            {"domain": "crash.fr", "last_post_date": ""},
        ]
        config = self._make_config()

        def boom(domain: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            if domain == "crash.fr":
                raise RuntimeError("boom")
            return [0, 0, 0, 0]

        with (
            patch("prospect_machine.intent.runner.fetch_wayback_quarters", side_effect=boom),
            patch("prospect_machine.intent.runner.fetch_whois_age", return_value=None),
            patch("prospect_machine.intent.runner.fetch_ga_signals", return_value=(False, False)),
        ):
            results = run_intent_scoring(rows, config, concurrency=2)

        assert len(results) == 2


# ---------------------------------------------------------------------------
# IntentScoringStep (pipeline integration)
# ---------------------------------------------------------------------------

class TestIntentScoringStep:
    def _write_enriched_csv(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_adds_intent_columns(self, tmp_path: Path) -> None:
        from pipeline.steps.intent_scoring import IntentScoringStep

        input_csv = tmp_path / "EnrichmentStep" / "domains_enriched.csv"
        rows = [
            {"domain": "alpha.fr", "last_post_date": "", "score": "42", "email": "x@alpha.fr"},
            {"domain": "beta.fr", "last_post_date": "", "score": "10", "email": ""},
        ]
        self._write_enriched_csv(input_csv, rows)

        config_path = tmp_path / "intent_scoring.yaml"
        config_path.write_text(
            "weights:\n  post_age: 0.35\n  wayback: 0.30\n  whois: 0.20\n  ga_obsolete: 0.15\n"
            "post_age_inactive_days: 180\nwayback_quarters: 4\n"
            "wayback_min_snapshots: 1\nwhois_stagnation_ratio: 0.5\n"
        )

        run_dir = tmp_path / "run01"
        step = IntentScoringStep(config_path=config_path, concurrency=2)

        with (
            patch("prospect_machine.intent.runner.fetch_wayback_quarters", return_value=[0, 0, 0, 0]),
            patch("prospect_machine.intent.runner.fetch_whois_age", return_value=None),
            patch("prospect_machine.intent.runner.fetch_ga_signals", return_value=(False, False)),
        ):
            output = step.run(input_path=input_csv, run_dir=run_dir)

        assert output.exists()
        with output.open(encoding="utf-8", newline="") as fh:
            result_rows = list(csv.DictReader(fh))

        assert len(result_rows) == 2
        for r in result_rows:
            assert "intent_score" in r
            assert "wayback_quarters" in r
            assert "ga_has_ua_tag" in r
            # Original columns preserved
            assert "email" in r

    def test_raises_on_missing_input(self, tmp_path: Path) -> None:
        from pipeline.steps.intent_scoring import IntentScoringStep

        config_path = tmp_path / "cfg.yaml"
        config_path.write_text("weights: {}\n")
        step = IntentScoringStep(config_path=config_path)
        with pytest.raises(FileNotFoundError):
            step.run(input_path=tmp_path / "ghost.csv", run_dir=tmp_path / "run")

    def test_writes_done_marker(self, tmp_path: Path) -> None:
        from pipeline.steps.intent_scoring import IntentScoringStep

        input_csv = tmp_path / "enriched.csv"
        rows = [{"domain": "x.fr", "last_post_date": "", "score": "1"}]
        self._write_enriched_csv(input_csv, rows)

        config_path = tmp_path / "cfg.yaml"
        config_path.write_text(
            "weights:\n  post_age: 0.35\n  wayback: 0.30\n  whois: 0.20\n  ga_obsolete: 0.15\n"
            "post_age_inactive_days: 180\nwayback_quarters: 4\n"
            "wayback_min_snapshots: 1\nwhois_stagnation_ratio: 0.5\n"
        )

        run_dir = tmp_path / "runX"
        step = IntentScoringStep(config_path=config_path, concurrency=1)

        with (
            patch("prospect_machine.intent.runner.fetch_wayback_quarters", return_value=[0, 0, 0, 0]),
            patch("prospect_machine.intent.runner.fetch_whois_age", return_value=None),
            patch("prospect_machine.intent.runner.fetch_ga_signals", return_value=(False, False)),
        ):
            step.run(input_path=input_csv, run_dir=run_dir)

        assert (run_dir / ".IntentScoringStep.done").exists()
