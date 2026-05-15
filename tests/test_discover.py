from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from discover import (
    BingHtmlProvider,
    SearchProvider,
    StaticSearchProvider,
    build_queries,
    build_topic_fallback_queries,
    contains_search_operators,
    discover_domains,
    discovery_from_link,
    extract_bing_html_results,
    extract_bing_rss_results,
    extract_duckduckgo_results,
    import_domains_from_file,
    infer_query_family,
    niche_contains_modifier,
    normalize_query,
    sanitize_discovery_niche,
    search_page_starts,
    score_discovery_item,
    should_use_exact_query,
)
from io_helpers import read_discovery_csv
from models import DomainDiscovery
from utils import CLIError


class DiscoverTests(unittest.TestCase):
    def test_discover_deduplicates_domains_and_keeps_output_shape(self) -> None:
        fixtures = {
            "padel": [
                DomainDiscovery(
                    domain="example-padel.fr",
                    source_query="padel",
                    source_provider="static",
                    first_seen="2026-04-13T10:00:00+00:00",
                    title="Example Padel",
                    snippet="Guide padel",
                ),
                DomainDiscovery(
                    domain="example-padel.fr",
                    source_query="padel",
                    source_provider="static",
                    first_seen="2026-04-13T10:00:00+00:00",
                    title="Example Padel duplicate",
                    snippet="Duplicate result",
                ),
            ],
        }
        provider = StaticSearchProvider(fixtures)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=provider):
                results = discover_domains(["padel"], limit=10, output=output, delay=0)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].domain, "example-padel.fr")
            with open(output, "r", encoding="utf-8") as handle:
                header = handle.readline().strip()
            self.assertEqual(
                header,
                "domain,discovery_score,lead_reason,query_family,source_query,source_provider,first_seen,title,snippet",
            )

    def test_discover_continues_when_one_query_fails(self) -> None:
        class FlakyProvider(SearchProvider):
            name = "flaky"

            def search(self, query: str, limit: int, session) -> list[DomainDiscovery]:
                if query == "guide padel":
                    raise CLIError("temporary failure")
                return [
                    DomainDiscovery(
                        domain="example-padel.fr",
                        source_query=query,
                        source_provider=self.name,
                        first_seen="2026-04-13T10:00:00+00:00",
                        title="Example Padel",
                        snippet="Guide padel",
                    )
                ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=FlakyProvider()):
                results = discover_domains(["padel"], limit=10, output=output, delay=0)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].domain, "example-padel.fr")

    def test_discover_logs_query_progress_even_before_first_result(self) -> None:
        fixtures = {
            "padel": [
                DomainDiscovery(
                    domain="example-padel.fr",
                    source_query="padel",
                    source_provider="static",
                    first_seen="2026-04-13T10:00:00+00:00",
                    title="Example Padel",
                    snippet="Guide padel",
                ),
            ],
        }
        provider = StaticSearchProvider(fixtures)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=provider), patch("builtins.print") as mock_print:
                discover_domains(["padel"], limit=10, output=output, delay=0)

        printed_lines = " | ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
        self.assertIn("Discover lance", printed_lines)
        self.assertIn("Requete en cours: 'padel'", printed_lines)
        self.assertIn("nouveaux domaines gardes", printed_lines)

    def test_import_domains_from_file_filters_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_path = f"{tmp_dir}/domains.txt"
            output = f"{tmp_dir}/domains_raw.csv"
            with open(input_path, "w", encoding="utf-8") as handle:
                handle.write("https://example.com\n")
                handle.write("example.com\n")
                handle.write("www.small-blog.fr\n")

            results = import_domains_from_file(input_path=input_path, output=output)

            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].source_provider, "manual")
            self.assertEqual(results[0].query_family, "manual")

    def test_extract_duckduckgo_results_supports_structured_markup(self) -> None:
        html = """
        <div class="result">
          <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fsmall-yoga-blog.fr%2Fguide">Guide Yoga</a>
          <div class="result__snippet">Blog yoga pour debutants</div>
        </div>
        """

        results = extract_duckduckgo_results(
            html=html,
            query="blog yoga",
            provider_name="duckduckgo",
            limit=10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].domain, "small-yoga-blog.fr")

    def test_extract_duckduckgo_results_supports_fallback_links(self) -> None:
        html = """
        <html>
          <body>
            <a href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fmini-site-velo.fr%2Fcomparatif">
              Comparatif velo electrique 2026
            </a>
          </body>
        </html>
        """

        results = extract_duckduckgo_results(
            html=html,
            query="comparatif velo electrique",
            provider_name="duckduckgo",
            limit=10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].domain, "mini-site-velo.fr")

    def test_normalize_query_removes_duplicate_words(self) -> None:
        self.assertEqual(normalize_query("blog blog yoga"), "blog yoga")

    def test_sanitize_discovery_niche_removes_ui_like_prefix(self) -> None:
        self.assertEqual(sanitize_discovery_niche("Niches = blog cpf"), "blog cpf")
        self.assertEqual(sanitize_discovery_niche("query: blog yoga"), "blog yoga")

    def test_modifier_niche_does_not_expand_to_weird_queries(self) -> None:
        self.assertTrue(niche_contains_modifier("blog yoga"))
        self.assertTrue(niche_contains_modifier("comparatif velo electrique"))
        self.assertFalse(niche_contains_modifier("yoga"))

    def test_advanced_query_uses_exact_mode_automatically(self) -> None:
        query = 'site:.fr "CPF" "blog" "guides" intitle:CPF inbody:CPF'

        self.assertTrue(contains_search_operators(query))
        self.assertTrue(should_use_exact_query(query))
        self.assertEqual(build_queries([query], query_mode="auto"), [query])
        self.assertEqual(build_queries(["Niches = blog cpf"], query_mode="auto"), ["blog cpf"])

    def test_exact_query_mode_keeps_plain_query_unchanged(self) -> None:
        self.assertEqual(build_queries(["yoga"], query_mode="exact"), ["yoga"])
        self.assertEqual(
            build_queries(["yoga"], query_mode="expand"),
            [
                "yoga",
                "blog yoga",
                "guide yoga",
                "comparatif yoga",
                "avis yoga",
                "magazine yoga",
                "ressources yoga",
                "actualites yoga",
                "meilleur yoga",
                "yoga conseils",
                "yoga guide 2024",
                "yoga comparatif 2024",
            ],
        )

    def test_topic_fallback_queries_expand_short_modifier_query(self) -> None:
        self.assertEqual(
            build_topic_fallback_queries("blog cpf"),
            [
                "cpf",
                "blog cpf",
                "guide cpf",
                "comparatif cpf",
                "avis cpf",
                "magazine cpf",
                "ressources cpf",
                "actualites cpf",
                "meilleur cpf",
                "cpf conseils",
                "cpf guide 2024",
                "cpf comparatif 2024",
            ],
        )

    def test_extract_bing_rss_results_parses_items(self) -> None:
        xml_payload = """
        <rss>
          <channel>
            <item>
              <title>Guide yoga debutant</title>
              <link>https://small-yoga-blog.fr/guide-yoga</link>
              <description>Un blog yoga pour debutants</description>
            </item>
          </channel>
        </rss>
        """

        results = extract_bing_rss_results(
            xml_payload=xml_payload,
            query="blog yoga",
            provider_name="bingrss",
            limit=10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].domain, "small-yoga-blog.fr")

    def test_extract_bing_html_results_parses_standard_serp_markup(self) -> None:
        html = """
        <html>
          <body>
            <ol>
              <li class="b_algo">
                <h2><a href="https://small-yoga-blog.fr/guide-yoga">Guide yoga debutant</a></h2>
                <div class="b_caption"><p>Un blog yoga pour debutants</p></div>
              </li>
            </ol>
          </body>
        </html>
        """

        results = extract_bing_html_results(
            html=html,
            query="blog yoga",
            provider_name="binghtml",
            limit=10,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].domain, "small-yoga-blog.fr")

    def test_bing_html_provider_paginates_past_first_result_page(self) -> None:
        class FakeResponse:
            def __init__(self, text: str) -> None:
                self.text = text

            def raise_for_status(self) -> None:
                return None

        class FakeSession:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def get(self, url: str, params: dict[str, object], timeout: int) -> FakeResponse:
                self.calls.append(params)
                first = params.get("first")
                domain = "first-yoga-blog.fr" if first == 1 else "second-yoga-guide.fr"
                title = "Blog yoga" if first == 1 else "Guide yoga 2024"
                html = f"""
                <ol>
                  <li class="b_algo">
                    <h2><a href="https://{domain}/article">{title}</a></h2>
                    <div class="b_caption"><p>Conseils yoga pour debutants</p></div>
                  </li>
                </ol>
                """
                return FakeResponse(html)

        session = FakeSession()
        results = BingHtmlProvider().search(query="yoga", limit=50, session=session)  # type: ignore[arg-type]

        self.assertEqual([item.domain for item in results], ["first-yoga-blog.fr", "second-yoga-guide.fr"])
        self.assertEqual([call["first"] for call in session.calls], [1, 11, 21, 31, 41])

    def test_extract_bing_rss_results_filters_platform_domains(self) -> None:
        xml_payload = """
        <rss>
          <channel>
            <item>
              <title>Blogger.com - Create a unique and beautiful blog easily.</title>
              <link>https://www.blogger.com/</link>
              <description>Create a blog easily.</description>
            </item>
          </channel>
        </rss>
        """

        results = extract_bing_rss_results(
            xml_payload=xml_payload,
            query="blog yoga",
            provider_name="bingrss",
            limit=10,
        )

        self.assertEqual(results, [])

    def test_discovery_from_link_filters_institutional_domains(self) -> None:
        discovery = discovery_from_link(
            href="https://service-public.gouv.fr/particuliers/vosdroits/F00001",
            title="MaPrimeRenov | Service Public",
            snippet="Aides a la renovation energetique",
            query="renovation energetique",
            provider_name="bingrss",
            first_seen="2026-04-14T21:37:09+00:00",
        )

        self.assertIsNone(discovery)

    def test_discovery_from_link_filters_hard_blocked_media_domains(self) -> None:
        discovery = discovery_from_link(
            href="https://www.capital.fr/votre-argent/guide-epargne",
            title="Guide epargne",
            snippet="Conseils epargne",
            query="guide epargne",
            provider_name="bingrss",
            first_seen="2026-04-14T21:37:09+00:00",
        )

        self.assertIsNone(discovery)

    def test_discovery_from_link_filters_irrelevant_results_even_with_modifier_query(self) -> None:
        discovery = discovery_from_link(
            href="https://guideauto.com/article/123",
            title="7 SUV fiables a moins de 45 000$",
            snippet="Le guide auto des SUV fiables",
            query="guide renovation energetique",
            provider_name="bingrss",
            first_seen="2026-04-14T21:37:09+00:00",
        )

        self.assertIsNone(discovery)

    def test_discover_domains_keeps_relevant_niche_sites_and_removes_noise(self) -> None:
        fixtures = {
            "blog renovation energetique": [
                DomainDiscovery(
                    domain="service-public.gouv.fr",
                    source_query="blog renovation energetique",
                    source_provider="static",
                    first_seen="2026-04-14T21:37:09+00:00",
                    title="MaPrimeRenov | Service Public",
                    snippet="Aides a la renovation energetique",
                ),
                DomainDiscovery(
                    domain="guideauto.com",
                    source_query="blog renovation energetique",
                    source_provider="static",
                    first_seen="2026-04-14T21:37:09+00:00",
                    title="Guide auto",
                    snippet="SUV fiables",
                ),
                DomainDiscovery(
                    domain="renovation-ecologique.fr",
                    source_query="blog renovation energetique",
                    source_provider="static",
                    first_seen="2026-04-14T21:37:09+00:00",
                    title="Le Blog de la Performance Energetique",
                    snippet="Conseils en renovation energetique",
                ),
            ],
        }
        provider = StaticSearchProvider(fixtures)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=provider):
                results = discover_domains(["blog renovation energetique"], limit=10, output=output, delay=0)

            self.assertEqual([item.domain for item in results], ["renovation-ecologique.fr"])

    def test_discover_ranks_candidates_by_lead_score(self) -> None:
        fixtures = {
            "padel": [
                DomainDiscovery(
                    domain="padel-login-app.fr",
                    source_query="padel",
                    source_provider="static",
                    first_seen="2026-04-14T21:37:09+00:00",
                    title="Padel app login dashboard",
                    snippet="Connexion support pricing pour clubs de padel",
                ),
                DomainDiscovery(
                    domain="guide-padel-club.fr",
                    source_query="padel",
                    source_provider="static",
                    first_seen="2026-04-14T21:37:09+00:00",
                    title="Guide padel club 2024",
                    snippet="Blog conseils padel et comparatif materiel",
                ),
            ],
        }
        provider = StaticSearchProvider(fixtures)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=provider):
                results = discover_domains(["padel"], limit=1, output=output, delay=0, query_mode="exact")

            self.assertEqual([item.domain for item in results], ["guide-padel-club.fr"])
            self.assertGreater(results[0].discovery_score, 70)
            self.assertIn("contenu date", results[0].lead_reason)

    def test_discovery_csv_reader_accepts_legacy_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/legacy_domains_raw.csv"
            with open(output, "w", encoding="utf-8") as handle:
                handle.write("domain,source_query,source_provider,first_seen,title,snippet\n")
                handle.write("example.com,padel,manual,2026-05-15T10:00:00+00:00,Title,Snippet\n")

            rows = read_discovery_csv(output)

            self.assertEqual(rows[0].domain, "example.com")
            self.assertEqual(rows[0].discovery_score, 0)
            self.assertEqual(rows[0].lead_reason, "")

    def test_score_discovery_item_rewards_refreshable_editorial_results(self) -> None:
        score, reasons = score_discovery_item(
            domain="guide-padel-club.fr",
            title="Guide padel 2024",
            snippet="Blog conseils et comparatif padel",
            query="guide padel",
        )

        self.assertGreaterEqual(score, 80)
        self.assertIn("contenu date", reasons)
        self.assertEqual(infer_query_family("comparatif padel 2024"), "editorial_refresh")
        self.assertEqual(search_page_starts(30), [1, 11, 21])

    def test_discover_auto_falls_back_to_topic_queries_when_modifier_query_is_empty(self) -> None:
        class TopicFallbackProvider(SearchProvider):
            name = "topic-fallback"

            def search(self, query: str, limit: int, session) -> list[DomainDiscovery]:
                if query == "blog cpf":
                    return []
                if query == "guide cpf":
                    return [
                        DomainDiscovery(
                            domain="cpf-info.fr",
                            source_query=query,
                            source_provider=self.name,
                            first_seen="2026-04-15T16:19:13+00:00",
                            title="Guide CPF",
                            snippet="Ressources CPF et formation",
                        )
                    ]
                return []

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=TopicFallbackProvider()):
                results = discover_domains(["blog cpf"], limit=10, output=output, delay=0, query_mode="auto")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].domain, "cpf-info.fr")

    def test_discover_auto_expands_modifier_query_when_limit_is_underfilled(self) -> None:
        class UnderfilledProvider(SearchProvider):
            name = "underfilled"

            def search(self, query: str, limit: int, session) -> list[DomainDiscovery]:
                if query == "blog yoga":
                    return [
                        DomainDiscovery(
                            domain="small-yoga-blog.fr",
                            source_query=query,
                            source_provider=self.name,
                            first_seen="2026-04-15T16:19:13+00:00",
                            title="Blog yoga",
                            snippet="Conseils yoga",
                        )
                    ]
                if query == "guide yoga":
                    return [
                        DomainDiscovery(
                            domain="guide-yoga-debutant.fr",
                            source_query=query,
                            source_provider=self.name,
                            first_seen="2026-04-15T16:19:13+00:00",
                            title="Guide yoga debutant",
                            snippet="Guide conseils yoga 2024",
                        )
                    ]
                return []

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = f"{tmp_dir}/domains_raw.csv"
            with patch("discover.get_provider", return_value=UnderfilledProvider()):
                results = discover_domains(["blog yoga"], limit=10, output=output, delay=0, query_mode="auto")

            self.assertEqual(
                [item.domain for item in results],
                ["guide-yoga-debutant.fr", "small-yoga-blog.fr"],
            )


if __name__ == "__main__":
    unittest.main()
