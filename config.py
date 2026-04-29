from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TIMEOUT = 10
DEFAULT_DELAY = 0.2
DEFAULT_MAX_PAGES = 100
DEFAULT_UI_AUDIT_MAX_PAGES = 100
DEFAULT_DISCOVER_PROVIDER = "auto"
DEFAULT_QUALIFY_MODE = "qualify_fast"
DEFAULT_AUDIT_MODE = "audit_light"
DEFAULT_CRAWL_SOURCE = "mixed"
DISCOVER_HTTP_TIMEOUT = 6
DISCOVER_RETRY_ATTEMPTS = 2
DISCOVER_RETRY_BACKOFF = 1.0
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": DEFAULT_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

SEARCH_QUERY_TEMPLATES = [
    "{niche}",
    "blog {niche}",
    "guide {niche}",
    "comparatif {niche}",
    "meilleur {niche}",
    "{niche} conseils",
]

QUERY_MODIFIER_HINTS = {
    "actualites",
    "actualités",
    "blog",
    "comparatif",
    "comparatifs",
    "conseils",
    "guide",
    "guides",
    "magazine",
    "meilleur",
    "meilleurs",
}

DISCOVERY_QUERY_STOPWORDS = {
    "a",
    "au",
    "aux",
    "avec",
    "dans",
    "de",
    "des",
    "du",
    "en",
    "et",
    "la",
    "le",
    "les",
    "pour",
    "sur",
    "un",
    "une",
}

DISCOVERY_EXCLUDED_DOMAIN_PATTERNS = (
    ".gouv.fr",
    ".gov",
    ".edu",
    "ademe.fr",
    "anah.fr",
    "ameli.fr",
    "beta.gouv",
    "caf.fr",
    "data.gouv.fr",
    "france-renov",
    "legifrance.gouv.fr",
    "service-public",
    "urssaf.fr",
    "vie-publique.fr",
)

HARD_BLOCKED_DOMAINS = {
    "bfmtv.com",
    "capital.fr",
    "journaldunet.com",
    "lemonde.fr",
    "service-public.fr",
    "wikipedia.org",
}

HARD_BLOCKED_SUFFIXES = (
    ".gouv.fr",
    ".gov",
    ".edu",
)

BIG_SITE_DOMAINS = {
    "amazon.com",
    "amazon.fr",
    "apple.com",
    "bfmtv.com",
    "blogger.com",
    "cdiscount.com",
    "facebook.com",
    "francetvinfo.fr",
    "ghost.io",
    "google.com",
    "google.fr",
    "instagram.com",
    "journaldunet.com",
    "lefigaro.fr",
    "lemonde.fr",
    "leboncoin.fr",
    "linkedin.com",
    "medium.com",
    "microsoft.com",
    "notion.site",
    "pinterest.com",
    "reddit.com",
    "substack.com",
    "tumblr.com",
    "tiktok.com",
    "wikipedia.org",
    "wixsite.com",
    "x.com",
    "youtube.com",
    "wordpress.com",
}

BLOG_PATH_HINTS = [
    "/blog",
    "/articles",
    "/actualites",
    "/actualites/",
    "/guides",
    "/guide",
    "/conseils",
    "/ressources",
    "/comparatif",
    "/comparatifs",
    "/magazine",
    "/journal",
]

EDITORIAL_PATH_HINTS = tuple(
    dict.fromkeys(
        [
            *BLOG_PATH_HINTS,
            "/actualite",
            "/analysis",
            "/analyses",
            "/blogue",
            "/case-study",
            "/case-studies",
            "/comparateur",
            "/editorial",
            "/insights",
            "/news",
            "/newsroom",
            "/publication",
            "/publications",
            "/review",
            "/reviews",
            "/stories",
        ]
    )
)

APP_PATH_HINTS = (
    "/app",
    "/auth",
    "/dashboard",
    "/demo",
    "/login",
    "/pricing",
    "/register",
    "/signup",
)

DOCS_PATH_HINTS = (
    "/api",
    "/developer",
    "/developers",
    "/docs",
    "/documentation",
    "/help",
    "/knowledge-base",
    "/support",
)

MARKETPLACE_PATH_HINTS = (
    "/boutique",
    "/cart",
    "/checkout",
    "/marketplace",
    "/product",
    "/products",
    "/seller",
    "/shop",
    "/store",
    "/vendor",
)

SOCIAL_HOST_HINTS = {
    "facebook.com": "facebook",
    "instagram.com": "instagram",
    "linkedin.com": "linkedin",
    "tiktok.com": "tiktok",
    "x.com": "x",
    "twitter.com": "twitter",
    "youtube.com": "youtube",
}

CMS_SIGNATURES = [
    ("wp-content", "WordPress"),
    ("wordpress", "WordPress"),
    ("shopify", "Shopify"),
    ("wix.com", "Wix"),
    ("squarespace", "Squarespace"),
    ("webflow", "Webflow"),
    ("prestashop", "PrestaShop"),
    ("joomla", "Joomla"),
    ("ghost", "Ghost"),
]

SITEMAP_CANDIDATES = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/wp-sitemap.xml",
    "/post-sitemap.xml",
    "/page-sitemap.xml",
    "/category-sitemap.xml",
]

EXCLUDED_CRAWL_EXTENSIONS = {
    ".atom",
    ".avi",
    ".css",
    ".doc",
    ".docx",
    ".gif",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rss",
    ".svg",
    ".webp",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}

EXCLUDED_CRAWL_PATH_PREFIXES = {
    "/account",
    "/admin",
    "/app",
    "/cart",
    "/checkout",
    "/compte",
    "/dashboard",
    "/docs",
    "/feed",
    "/go",
    "/help",
    "/login",
    "/my-account",
    "/panier",
    "/pricing",
    "/register",
    "/search",
    "/signup",
    "/support",
    "/wp-admin",
    "/wp-content/uploads",
    "/wp-json",
    "/wp-login",
    "/xmlrpc",
}

CONTENT_PATH_HINTS = tuple(
    dict.fromkeys(
        [
            *EDITORIAL_PATH_HINTS,
            "/202",
            "/compare",
            "/comparison",
            "/comparisons",
            "/guide-",
            "/how-to",
            "/learn",
            "/tutorial",
            "/tutorials",
        ]
    )
)

NON_CONTENT_PATH_PREFIXES = tuple(
    dict.fromkeys(
        [
            *EXCLUDED_CRAWL_PATH_PREFIXES,
            "/author",
            "/category",
            "/legal",
            "/mentions-legales",
            "/privacy",
            "/tag",
            "/terms",
        ]
    )
)

UI_HEADING_PATTERNS = (
    "account",
    "cart",
    "checkout",
    "connect",
    "connexion",
    "contact us",
    "dashboard",
    "docs",
    "documentation",
    "help center",
    "knowledge base",
    "log in",
    "login",
    "pricing",
    "search",
    "se connecter",
    "sign in",
    "sign up",
    "support",
)

GSC_TECHNICAL_URL_PATTERNS = (
    "/wp-content/",
    "/wp-includes/",
    "/category/",
    "/tag/",
    "/author/",
    "/feed/",
    "?",
    "#",
)

GSC_TECHNICAL_URL_SUFFIXES = (
    ".gif",
    ".jpeg",
    ".jpg",
    ".json",
    ".pdf",
    ".png",
    ".svg",
    ".webp",
    ".xml",
)

GSC_STRUCTURAL_SLUGS = {
    "404",
    "a-propos",
    "about",
    "about-us",
    "blog",
    "cart",
    "cgu",
    "cgv",
    "checkout",
    "commande",
    "conditions-generales",
    "contact",
    "contact-us",
    "contactez-nous",
    "legal",
    "legales",
    "login",
    "mentions-legales",
    "mentions-légales",
    "mon-compte",
    "my-account",
    "page-not-found",
    "plan-du-site",
    "politique-de-confidentialite",
    "privacy",
    "privacy-policy",
    "qui-sommes-nous",
    "register",
    "sitemap",
    "terms",
}

GSC_CANNIBAL_STOPWORDS = {
    "avec",
    "best",
    "blog",
    "comment",
    "dans",
    "des",
    "from",
    "guide",
    "how",
    "les",
    "page",
    "pour",
    "that",
    "the",
    "this",
    "top",
    "une",
    "what",
}


@dataclass(frozen=True)
class QualificationScoringWeights:
    pages_20: int = 10
    pages_50: int = 15
    pages_100: int = 20
    pages_200: int = 25
    has_blog: int = 10
    wordpress: int = 10
    modern_cms: int = 5
    has_dated_content: int = 20
    dated_urls_low: int = 5
    dated_urls_high: int = 10
    contact_found: int = 5
    social_links: int = 5
    issue_cap: int = 15
    issue_unit: int = 5
    missing_sitemap_penalty: int = 2
    editorial_candidate_bonus: int = 8
    app_like_penalty: int = 35
    docs_like_penalty: int = 30
    marketplace_like_penalty: int = 12
    size_score_medium_penalty: int = 10
    size_score_high_penalty: int = 25


QUALIFICATION_WEIGHTS = QualificationScoringWeights()


@dataclass(frozen=True)
class QualifyModeConfig:
    homepage_timeout: int = 8
    check_sitemap: bool = False
    max_html_bytes: int = 650_000
    max_total_seconds_per_domain: float = 8.0
    max_total_requests_per_domain: int = 2
    max_sitemap_urls: int = 0
    max_nested_sitemaps: int = 0
    max_redirects: int = 4


@dataclass(frozen=True)
class AuditModeConfig:
    timeout: int = 8
    max_pages: int = 100
    max_depth: int = 2
    max_total_requests_per_domain: int = 35
    max_links_per_page: int = 12
    max_html_bytes: int = 700_000
    max_total_seconds_per_domain: float = 20.0
    overlap_enabled: bool = False
    overlap_max_pages: int = 0
    max_consecutive_errors: int = 5
    max_redirects: int = 5


QUALIFY_MODE_CONFIGS = {
    "qualify_fast": QualifyModeConfig(),
    "qualify_full": QualifyModeConfig(
        homepage_timeout=10,
        check_sitemap=True,
        max_html_bytes=900_000,
        max_total_seconds_per_domain=18.0,
        max_total_requests_per_domain=6,
        max_sitemap_urls=180,
        max_nested_sitemaps=2,
        max_redirects=5,
    ),
}

AUDIT_MODE_CONFIGS = {
    "audit_light": AuditModeConfig(),
    "audit_full": AuditModeConfig(
        timeout=12,
        max_pages=100,
        max_depth=4,
        max_total_requests_per_domain=100,
        max_links_per_page=20,
        max_html_bytes=1_200_000,
        max_total_seconds_per_domain=45.0,
        overlap_enabled=True,
        overlap_max_pages=24,
        max_consecutive_errors=8,
        max_redirects=6,
    ),
}
