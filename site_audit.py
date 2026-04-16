from __future__ import annotations

import argparse
from dataclasses import asdict

from audit import audit_domains
from io_helpers import write_json_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Legacy wrapper around prospect_machine audit --site",
    )
    parser.add_argument("url", help="Site URL or domain")
    parser.add_argument("-n", "--max-pages", type=int, default=150, help="Maximum pages to crawl")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay between requests")
    parser.add_argument("-o", "--output", default="site_audit.json", help="Output JSON path")
    args = parser.parse_args()

    reports = audit_domains(
        input_csv=None,
        output_dir="/tmp/prospect_machine_legacy_audit",
        site=args.url,
        max_pages=args.max_pages,
        delay=args.delay,
    )
    write_json_file(args.output, asdict(reports[0]))
    print(f"Audit ecrit dans {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
