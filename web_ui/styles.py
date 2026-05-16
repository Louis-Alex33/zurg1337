from __future__ import annotations

PAGE_STYLE = """
    @import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,600;1,400;1,600&family=Inter:wght@400;600;700;800&display=swap');

    :root {
      --bg: #f5f0e8;
      --card: #faf8f3;
      --ink: #1a1a1a;
      --muted: #6b6560;
      --line: #ddd8cc;
      --line-strong: #c8c2b4;
      --navy: #0c0f14;
      --accent: #c4622d;
      --accent-soft: #f5e8e0;
      --cyan: #4a7c8a;
      --emerald: #3a6b4a;
      --high-bg: #faeae4;
      --high-text: #8b3018;
      --medium-bg: #f5eedc;
      --medium-text: #7a5c1a;
      --healthy-bg: #e4ede8;
      --healthy-text: #2e5e3a;
      --shadow-card: none;
      --shadow-soft: none;
      --radius: 4px;
    }

    * {
      box-sizing: border-box;
    }

    html {
      background: var(--bg);
    }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background: var(--bg);
      font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, sans-serif;
      font-size: 15px;
      line-height: 1.55;
    }

    a {
      color: inherit;
      text-decoration: none;
    }

    button,
    input,
    select {
      font: inherit;
    }

    .page {
      max-width: 1260px;
      margin: 0 auto;
      padding: 32px 24px 64px;
    }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.75fr);
      gap: 20px;
      align-items: stretch;
      margin-bottom: 22px;
    }

    .hero h1,
    .file-shell h1 {
      margin: 0 0 10px;
      color: var(--navy);
      font-family: 'EB Garamond', Georgia, serif;
      font-size: clamp(2.4rem, 4.5vw, 4.5rem);
      font-weight: 400;
      font-style: italic;
      line-height: 1;
      letter-spacing: 0;
    }

    .lede {
      margin: 0;
      max-width: 58rem;
      color: var(--muted);
      font-size: 1.02rem;
      line-height: 1.65;
    }

    .eyebrow,
    .report-summary-label,
    .roadmap-card span,
    .audit-fact-list dt,
    .audit-side-label,
    .page-client-brief span,
    .page-card-label,
    .impact-quadrant-head span,
    .meta-grid strong,
    .status-pill,
    .audit-hero-surtitle {
      margin: 0;
      color: var(--muted);
      text-transform: uppercase;
      font-size: 0.7rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      line-height: 1.2;
    }

    .panel,
    .hero-panel,
    .subpanel,
    .quick-start-card,
    .audit-compact-card,
    .audit-metric-card,
    .job-card,
    .report-summary-card,
    .roadmap-card,
    .audit-hero-card,
    .report-chart-card,
    .signal-row-card,
    .page-priority-card,
    .pair-card,
    .impact-quadrant,
    .impact-action-card,
    .score-donut-widget,
    .copy-block,
    .audit-highlight-card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: none;
    }

    .panel,
    .subpanel {
      padding: 22px;
    }

    .hero-panel {
      display: grid;
      gap: 12px;
      align-content: start;
      padding: 16px;
    }

    .hero-stat {
      padding: 14px;
      border-radius: var(--radius);
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .hero-stat strong {
      display: block;
      color: var(--navy);
      margin-bottom: 4px;
    }

    .hero-stat span {
      color: var(--muted);
      font-size: 0.9rem;
    }

    .grid {
      display: grid;
      gap: 20px;
      margin-bottom: 20px;
    }

    .grid.two {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .onboarding-grid {
      grid-template-columns: 1fr;
    }

    .panel-head {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 16px;
    }

    .panel h2,
    .subpanel h2,
    .report-chart-card h2 {
      margin: 0 0 12px;
      color: var(--navy);
      font-family: 'EB Garamond', Georgia, serif;
      font-size: 1.55rem;
      font-weight: 400;
      line-height: 1.2;
      letter-spacing: 0;
    }

    .onboarding-panel {
      background: var(--card);
    }

    .quick-start-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }

    .quick-start-card {
      padding: 16px;
      box-shadow: none;
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .quick-start-card h3 {
      margin: 8px 0 10px;
      color: var(--navy);
      font-family: 'EB Garamond', Georgia, serif;
      font-size: 1.2rem;
      font-weight: 400;
      line-height: 1.3;
    }

    .compact-flow,
    .compact-list,
    .flow,
    .clean-list {
      margin: 0;
      padding-left: 1.1rem;
      color: var(--ink);
      line-height: 1.7;
    }

    .clean-list li + li,
    .flow li + li {
      margin-top: 6px;
    }

    .badge,
    .pill,
    .priority-chip,
    .audit-pages-pill,
    .report-status-label,
    .audit-status-chip,
    .impact-action-meta span {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border-radius: 2px;
      padding: 4px 8px;
      background: var(--bg);
      border: 1px solid var(--line);
      color: var(--ink);
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      line-height: 1.2;
      white-space: nowrap;
    }

    .badge {
      color: var(--muted);
    }

    .card-lede,
    .section-intro,
    .audit-score-explainer,
    .signal-help,
    .field-help,
    .audit-print-note,
    .job-meta {
      color: var(--muted);
      line-height: 1.6;
    }

    .card-lede {
      margin: 0 0 12px;
    }

    .section-intro {
      margin: 8px 0 0;
    }

    .card-tip,
    .copy-block {
      margin: 0 0 16px;
      padding: 14px 16px;
      border-radius: var(--radius);
      background: var(--bg);
      border-left: 3px solid var(--accent);
      color: var(--ink);
      line-height: 1.55;
    }

    .stack {
      display: grid;
      gap: 14px;
    }

    label {
      display: grid;
      gap: 7px;
      color: var(--ink);
      font-weight: 650;
    }

    input,
    select {
      width: 100%;
      border: 1px solid var(--line-strong);
      border-radius: var(--radius);
      padding: 11px 12px;
      background: var(--card);
      color: var(--ink);
      appearance: none;
    }

    input:focus,
    select:focus {
      outline: 2px solid rgba(196, 98, 45, 0.2);
      border-color: var(--accent);
    }

    .inline-fields {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }

    .field-help {
      margin: -6px 2px 0;
      font-size: 0.9rem;
    }

    .running-help {
      margin-top: 8px;
    }

    .checkbox-line {
      display: flex;
      align-items: center;
      gap: 10px;
      padding-top: 24px;
    }

    .checkbox-line input {
      width: auto;
      transform: scale(1.15);
    }

    .button,
    .ghost-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 1px solid var(--navy);
      border-radius: var(--radius);
      padding: 10px 16px;
      background: var(--navy);
      color: #faf8f3;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: pointer;
      box-shadow: none;
      transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
    }

    .button:hover,
    .ghost-button:hover {
      background: #2a2f3a;
      border-color: #2a2f3a;
    }

    .button.secondary,
    .ghost-button {
      background: transparent;
      color: var(--ink);
      border-color: var(--line-strong);
    }

    .button.secondary:hover,
    .ghost-button:hover {
      background: var(--bg);
      border-color: var(--navy);
      color: var(--navy);
    }

    .ghost-button.danger {
      color: var(--high-text);
      background: var(--high-bg);
      border-color: transparent;
    }

    .print-button {
      background: var(--accent);
      border-color: var(--accent);
      color: #faf8f3;
    }

    .print-button:hover {
      background: #a8511f;
      border-color: #a8511f;
    }

    .hero-actions {
      margin-top: 16px;
      align-items: center;
      flex-wrap: wrap;
    }

    .panel-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }

    .panel-tools,
    .audit-compact-head,
    .audit-domain-cell,
    .job-top,
    .job-actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .inline-form {
      margin: 0;
    }

    .audit-summary-preview {
      display: grid;
      gap: 12px;
    }

    .audit-compact-card,
    .audit-metric-card {
      padding: 14px;
    }

    .audit-compact-body {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }

    .audit-compact-foot {
      margin-top: 10px;
      font-size: 0.9rem;
    }

    .audit-metric-grid,
    .compact-metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }

    .compact-metric-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .audit-metric-card strong,
    .audit-highlight-card strong {
      display: block;
      color: var(--navy);
      font-size: 1.8rem;
      line-height: 1;
      margin-bottom: 6px;
    }

    .audit-metric-card span,
    .audit-highlight-card span {
      display: block;
      color: var(--ink);
      font-weight: 700;
    }

    .audit-metric-card p {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }

    .priority-chip,
    .audit-pages-pill {
      margin: 2px 4px 2px 0;
    }

    .priority-chip {
      background: var(--accent-soft);
      color: var(--accent);
    }

    .priority-badge {
      font-weight: 800;
    }

    .priority-high,
    .signal-pill.signal-high,
    .health-bad,
    .status-failed,
    .status-cancelled {
      background: var(--high-bg);
      color: var(--high-text);
    }

    .priority-moderate,
    .signal-pill.signal-medium,
    .health-watch,
    .score-mid,
    .status-queued {
      background: var(--medium-bg);
      color: var(--medium-text);
    }

    .priority-healthy,
    .health-good,
    .score-high,
    .status-done,
    .soft-pill {
      background: var(--healthy-bg);
      color: var(--healthy-text);
    }

    .audit-pages-pill,
    .domain-pill,
    .provider-pill,
    .score-low,
    .status-running {
      background: var(--bg);
      border-color: var(--line-strong);
      color: var(--ink);
    }

    .health-pill {
      white-space: nowrap;
    }

    .audit-summary-table td:nth-child(4) {
      min-width: 18rem;
    }

    .audit-shell,
    .audit-report-shell {
      background: transparent;
      border: 0;
      box-shadow: none;
    }

    .audit-report-shell {
      --report-ink: #1a1a1a;
      --report-muted: #6b6560;
      --report-line: #ddd8cc;
      --report-surface: #faf8f3;
      --report-bg: #f5f0e8;
      --report-blue: #c4622d;
      --report-navy: #0c0f14;
      --report-orange: #c4622d;
      --report-teal: #4a7c8a;
      --report-green: #3a6b4a;
      --report-red: #8b3018;
      padding: 0;
      color: var(--report-ink);
    }

    .audit-report-grid {
      margin-bottom: 0;
    }

    .report-page {
      display: grid;
      gap: 18px;
      margin-bottom: 22px;
    }

    .report-page:last-child {
      margin-bottom: 0;
    }

    .audit-report-topbar {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: start;
      margin-bottom: 18px;
    }

    .audit-report-heading {
      max-width: 54rem;
    }

    .audit-report-actions {
      position: sticky;
      top: 14px;
      z-index: 5;
      justify-content: flex-end;
      margin: 0 0 18px;
      padding: 10px;
      border-radius: var(--radius);
      background: rgba(245, 240, 232, 0.94);
      border: 1px solid var(--line);
      backdrop-filter: blur(8px);
    }

    .cover-layout-grid,
    .audit-hero-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.8fr);
      gap: 18px;
      align-items: stretch;
    }

    .cover-side-stack {
      display: grid;
      gap: 14px;
      align-content: start;
    }

    .audit-hero-card {
      padding: 24px;
    }

    .audit-hero-primary {
      border: 1px solid var(--line-strong);
    }

    .audit-cover-main {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(220px, 260px);
      gap: 24px;
      align-items: center;
    }

    .audit-hero-surtitle {
      color: var(--accent);
      margin-bottom: 10px;
    }

    .audit-hero-card h2 {
      margin: 0 0 12px;
      color: var(--navy);
      font-family: 'EB Garamond', Georgia, serif;
      font-size: clamp(1.7rem, 2.2vw, 2.6rem);
      font-weight: 400;
      line-height: 1.1;
      letter-spacing: 0;
    }

    .audit-hero-copy {
      margin: 0;
      max-width: 46rem;
      color: var(--ink);
      font-size: 1.02rem;
      line-height: 1.75;
    }

    .audit-score-explainer {
      margin: 14px 0 0;
      font-size: 0.94rem;
    }

    .audit-urgency-line {
      display: inline-flex;
      width: fit-content;
      margin: 16px 0 0;
      padding: 7px 10px;
      border-radius: 6px;
      background: var(--medium-bg);
      color: var(--medium-text);
      font-weight: 800;
      font-size: 0.86rem;
    }

    .score-donut-widget {
      display: grid;
      justify-items: center;
      gap: 12px;
      padding: 16px;
      background: var(--bg);
    }

    .score-donut-widget.score-donut-high {
      --score-color: var(--healthy-text);
    }

    .score-donut-widget.score-donut-mid {
      --score-color: var(--medium-text);
    }

    .score-donut-widget.score-donut-low {
      --score-color: var(--high-text);
    }

    .score-donut {
      width: 156px;
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      border-radius: 50%;
      background: conic-gradient(var(--score-color) var(--score-pct), var(--line) 0);
    }

    .score-donut-inner {
      width: 104px;
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      align-content: center;
      border-radius: 50%;
      background: var(--card);
      box-shadow: inset 0 0 0 1px var(--line);
    }

    .score-donut-inner strong {
      display: block;
      color: var(--navy);
      font-size: 2.2rem;
      line-height: 1;
    }

    .score-donut-inner span {
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 800;
    }

    .score-donut-copy {
      display: grid;
      justify-items: center;
      gap: 6px;
      text-align: center;
    }

    .score-donut-copy p {
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.45;
    }

    .score-donut-high .report-status-label {
      background: var(--healthy-bg);
      color: var(--healthy-text);
    }

    .score-donut-mid .report-status-label {
      background: var(--medium-bg);
      color: var(--medium-text);
    }

    .score-donut-low .report-status-label {
      background: var(--high-bg);
      color: var(--high-text);
    }

    .report-dashboard-row {
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
      gap: 18px;
      align-items: stretch;
    }

    .cover-brief-grid,
    .report-dashboard-row .cover-brief-grid,
    .report-intro-grid,
    .portfolio-kpi-grid,
    .audit-highlight-grid,
    .roadmap-grid {
      display: grid;
      gap: 12px;
    }

    .cover-brief-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 18px;
    }

    .report-dashboard-row .cover-brief-grid {
      grid-template-columns: repeat(4, minmax(0, 1fr));
      margin-top: 0;
    }

    .report-intro-grid,
    .portfolio-kpi-grid,
    .audit-highlight-grid,
    .roadmap-grid {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      margin-top: 16px;
    }

    .report-summary-card,
    .roadmap-card,
    .audit-highlight-card {
      padding: 15px;
      display: grid;
      gap: 8px;
    }

    .report-summary-card strong,
    .roadmap-card strong,
    .cover-strong-line {
      color: var(--navy);
      font-size: 1rem;
      line-height: 1.45;
    }

    .roadmap-card p,
    .pair-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }

    .cover-side-card h2 {
      margin-bottom: 10px;
    }

    .cover-url-list {
      margin-top: 0;
    }

    .cover-url-list li + li {
      margin-top: 8px;
    }

    .cover-url-link,
    .page-url {
      color: var(--navy);
      font-weight: 700;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }

    .report-chart-card {
      display: grid;
      align-content: start;
      padding: 22px;
    }

    .signal-chart-layout {
      display: grid;
      grid-template-columns: 152px minmax(0, 1fr);
      gap: 18px;
      align-items: center;
      margin-top: 16px;
    }

    .signal-pie {
      position: relative;
      width: 152px;
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      border-radius: 50%;
      box-shadow: inset 0 0 0 1px var(--line);
    }

    .signal-pie::before {
      content: "";
      position: absolute;
      width: 92px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: var(--card);
      box-shadow: inset 0 0 0 1px var(--line);
    }

    .signal-pie div {
      position: relative;
      display: grid;
      justify-items: center;
      gap: 2px;
    }

    .signal-pie strong {
      color: var(--navy);
      font-size: 1.8rem;
      line-height: 1;
    }

    .signal-pie span {
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 800;
    }

    .chart-legend {
      display: grid;
      gap: 10px;
      list-style: none;
      margin: 0;
      padding: 0;
    }

    .chart-legend li {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
      color: var(--ink);
      font-weight: 800;
    }

    .chart-legend small {
      display: block;
      margin-top: 2px;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 500;
      line-height: 1.35;
    }

    .chart-dot {
      width: 12px;
      aspect-ratio: 1;
      border-radius: 50%;
      background: currentColor;
    }

    .chart-dot.signal-indexing {
      color: var(--accent);
    }

    .chart-dot.signal-content {
      color: var(--report-orange);
    }

    .chart-dot.signal-structure {
      color: var(--cyan);
    }

    .chart-dot.signal-clear {
      color: var(--healthy-text);
    }

    .positive-panel,
    .score-explanation-panel,
    .method-limits-panel,
    .editorial-opportunities-panel,
    .report-action-panel {
      background: var(--card);
    }

    .impact-matrix-shell {
      margin-top: 18px;
    }

    .impact-quadrant-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-template-rows: repeat(2, minmax(220px, auto));
      gap: 14px;
    }

    .impact-quadrant {
      display: grid;
      gap: 12px;
      align-content: start;
      min-height: 220px;
      padding: 16px;
    }

    .impact-quick-wins {
      border-color: rgba(58, 107, 74, 0.4);
    }

    .impact-quadrant-head {
      display: grid;
      gap: 5px;
    }

    .impact-quadrant-head span {
      color: var(--accent);
    }

    .impact-quadrant-head h3 {
      margin: 0;
      color: var(--navy);
      font-family: 'EB Garamond', Georgia, serif;
      font-size: 1.25rem;
      font-weight: 400;
      line-height: 1.2;
    }

    .impact-quadrant-head p {
      margin: 0;
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.4;
    }

    .impact-quadrant-body {
      display: grid;
      gap: 10px;
    }

    .impact-action-card {
      display: grid;
      gap: 8px;
      padding: 12px;
      box-shadow: none;
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .impact-action-card strong {
      color: var(--navy);
      line-height: 1.35;
    }

    .impact-action-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .impact-axis {
      display: none;
    }

    .appendix-grid {
      margin-top: 16px;
    }

    .appendix-inner-panel {
      box-shadow: none;
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .technical-fact-list dd,
    .audit-path {
      overflow-wrap: anywhere;
    }

    .audit-fact-list {
      display: grid;
      gap: 12px;
      margin: 0;
    }

    .audit-fact-list div {
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }

    .audit-fact-list div:last-child {
      padding-bottom: 0;
      border-bottom: 0;
    }

    .audit-fact-list dd {
      margin: 0;
      color: var(--ink);
      font-weight: 700;
      line-height: 1.5;
    }

    .audit-technical-panel {
      margin-bottom: 18px;
    }

    .audit-tech-details summary,
    .signal-details summary,
    .raw-json-box summary {
      color: var(--navy);
      cursor: pointer;
      font-weight: 700;
      list-style: none;
    }

    .audit-tech-details summary::-webkit-details-marker {
      display: none;
    }

    .audit-tech-grid {
      margin-top: 14px;
      margin-bottom: 0;
    }

    .technical-page-table {
      min-width: 920px;
    }

    .signal-list,
    .page-priority-list,
    .pair-list {
      display: grid;
      gap: 14px;
    }

    .audit-report-shell .page-priority-list {
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      align-items: start;
    }

    .signal-row-card,
    .pair-card {
      padding: 16px;
    }

    .signal-row {
      display: grid;
      grid-template-columns: auto minmax(0, 1fr) auto;
      gap: 10px;
      align-items: center;
    }

    .signal-help {
      margin: 10px 0 0;
    }

    .signal-details {
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
    }

    .signal-example-list {
      margin-top: 10px;
    }

    .page-priority-card {
      display: grid;
      gap: 14px;
      padding: 18px;
    }

    .priority-card-high {
      border-left: 3px solid var(--high-text);
    }

    .priority-card-moderate {
      border-left: 3px solid var(--medium-text);
    }

    .priority-card-healthy {
      border-left: 3px solid var(--healthy-text);
    }

    .page-priority-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    .page-context-note {
      display: grid;
      gap: 6px;
      padding: 12px;
      border-radius: var(--radius);
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .page-context-note strong {
      color: var(--ink);
      font-size: 0.94rem;
      line-height: 1.55;
    }

    .page-client-brief {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }

    .page-brief-column {
      display: grid;
      gap: 10px;
      align-content: start;
    }

    .page-brief-block {
      display: grid;
      gap: 7px;
      padding: 13px;
      border-radius: var(--radius);
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .page-brief-block strong {
      color: var(--ink);
      font-size: 0.94rem;
      line-height: 1.55;
    }

    .page-brief-block.is-impact {
      background: #f7ece5;
      border-color: #e0c8be;
    }

    .page-brief-block.is-action {
      background: #eaf1ec;
      border-color: #c4d8c9;
    }

    .page-brief-block.is-angle {
      background: #f5f1e6;
      border-color: #ddd4bc;
    }

    .page-url {
      display: block;
      font-size: 1rem;
    }

    .copy-block p {
      margin: 0;
      color: var(--ink);
      line-height: 1.7;
      white-space: pre-wrap;
    }

    .portfolio-page {
      display: grid;
      gap: 18px;
    }

    .portfolio-hero-grid {
      align-items: stretch;
    }

    .portfolio-method-strip {
      margin-top: 12px;
      padding: 16px;
      box-shadow: none;
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .status-pill {
      border-radius: 6px;
      padding: 7px 10px;
    }

    .job-card {
      display: grid;
      gap: 8px;
      padding: 14px;
      margin-bottom: 10px;
    }

    .job-main-link {
      display: block;
    }

    .job-meta {
      margin: 4px 0 0;
      font-size: 0.92rem;
    }

    .job-delete {
      padding: 8px 12px;
      font-size: 0.84rem;
    }

    .muted {
      color: var(--muted);
    }

    .subtle-link {
      color: var(--accent);
      font-weight: 700;
    }

    .table-wrap {
      overflow: auto;
      border-radius: var(--radius);
      background: var(--card);
      border: 1px solid var(--line);
    }

    .table-filter-row {
      margin: 0 0 10px;
      max-width: 360px;
    }

    .table-filter-input {
      border-radius: 10px;
      padding: 10px 12px;
      font-size: 0.92rem;
    }

    table {
      width: 100%;
      min-width: 540px;
      border-collapse: collapse;
      font-size: 0.92rem;
    }

    th,
    td {
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--bg);
      color: var(--muted);
      text-transform: uppercase;
      font-size: 0.7rem;
      font-weight: 700;
      letter-spacing: 0.06em;
    }

    .file-meta {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .file-table table {
      min-width: 900px;
    }

    .col-name {
      display: inline-block;
      padding: 2px 0;
      white-space: nowrap;
    }

    .cell-empty {
      background: var(--bg);
    }

    .cell-text {
      max-width: 28rem;
      color: var(--ink);
      line-height: 1.45;
    }

    .log-box {
      margin: 0;
      max-height: 360px;
      overflow: auto;
      padding: 16px;
      border-radius: var(--radius);
      background: #0f172a;
      color: #e2e8f0;
      font-size: 0.87rem;
      line-height: 1.5;
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 20px;
    }

    .meta-grid div {
      display: grid;
      gap: 4px;
      padding: 12px 14px;
      border-radius: var(--radius);
      background: var(--bg);
      border: 1px solid var(--line);
    }

    .meta-grid span {
      color: var(--ink);
      font-weight: 700;
    }

    .error-box,
    .flash-banner {
      margin-bottom: 18px;
      padding: 14px 16px;
      border-radius: var(--radius);
      font-weight: 700;
    }

    .error-box {
      background: var(--high-bg);
      color: var(--high-text);
    }

    .flash-banner {
      background: var(--healthy-bg);
      color: var(--healthy-text);
    }

    .accent-clay,
    .accent-sage,
    .accent-ink,
    .accent-gold {
      border-left: 4px solid var(--accent);
    }

    @page {
      size: A4;
      margin: 14mm;
    }

    @media print {
      html,
      body,
      * {
        -webkit-print-color-adjust: exact !important;
        print-color-adjust: exact !important;
      }

      body {
        background: var(--bg) !important;
      }

      .page {
        max-width: none;
        padding: 0;
      }

      .no-print,
      .report-toolbar,
      .panel-actions,
      button,
      .raw-json-box,
      .flash-banner,
      .table-filter-row {
        display: none !important;
      }

      .audit-report-shell {
        padding: 0;
        background: transparent !important;
        box-shadow: none !important;
      }

      .panel,
      .subpanel,
      .hero-panel,
      .quick-start-card,
      .audit-compact-card,
      .audit-metric-card,
      .job-card,
      .report-summary-card,
      .roadmap-card,
      .audit-hero-card,
      .report-chart-card,
      .signal-row-card,
      .page-priority-card,
      .pair-card,
      .impact-quadrant,
      .impact-action-card,
      .score-donut-widget,
      .copy-block,
      .audit-highlight-card,
      .page-context-note,
      .page-brief-block {
        break-inside: avoid;
        page-break-inside: avoid;
      }

      .panel,
      .subpanel,
      .audit-hero-card,
      .audit-metric-card,
      .report-chart-card,
      .signal-row-card,
      .page-priority-card,
      .pair-card,
      .impact-quadrant,
      .impact-action-card,
      .score-donut-widget,
      .report-summary-card,
      .roadmap-card,
      .page-context-note,
      .page-brief-block {
        box-shadow: none !important;
        border: 1px solid var(--line) !important;
      }

      .report-page {
        gap: 12px;
        margin-bottom: 0;
        break-after: page;
        page-break-after: always;
      }

      .report-page:last-child {
        break-after: auto;
        page-break-after: auto;
      }

      .audit-report-topbar {
        margin-bottom: 12px;
      }

      .cover-layout-grid,
      .audit-cover-main,
      .audit-hero-grid,
      .report-dashboard-row,
      .report-dashboard-row .cover-brief-grid,
      .grid.two,
      .audit-metric-grid,
      .audit-highlight-grid,
      .report-intro-grid,
      .portfolio-kpi-grid,
      .roadmap-grid,
      .impact-quadrant-grid,
      .page-client-brief,
      .file-meta {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      }

      .signal-chart-layout {
        grid-template-columns: 132px minmax(0, 1fr) !important;
      }

      .score-donut,
      .signal-pie {
        width: 132px;
      }

      .score-donut-inner {
        width: 88px;
      }

      .signal-pie::before {
        width: 82px;
      }

      .file-shell h1 {
        font-size: 28pt;
      }

      .audit-hero-copy,
      .copy-block p,
      .clean-list,
      .score-donut-copy p,
      .signal-help {
        font-size: 11pt;
        line-height: 1.55;
      }

      a {
        color: var(--ink);
        text-decoration: none;
      }
    }

    @media (max-width: 900px) {
      .page {
        padding: 20px 14px 40px;
      }

      .hero,
      .grid.two,
      .inline-fields,
      .meta-grid,
      .audit-metric-grid,
      .quick-start-grid,
      .audit-hero-grid,
      .audit-highlight-grid,
      .report-intro-grid,
      .portfolio-kpi-grid,
      .compact-metric-grid,
      .cover-layout-grid,
      .cover-brief-grid,
      .roadmap-grid,
      .page-client-brief,
      .audit-cover-main,
      .report-dashboard-row,
      .report-dashboard-row .cover-brief-grid,
      .signal-chart-layout,
      .impact-quadrant-grid,
      .file-meta {
        grid-template-columns: 1fr;
      }

      .panel,
      .subpanel,
      .audit-hero-card {
        padding: 18px;
      }

      .audit-report-topbar {
        flex-direction: column;
      }

      .audit-report-actions {
        position: static;
        width: 100%;
        justify-content: flex-start;
      }

      .audit-report-shell .page-priority-list {
        grid-template-columns: 1fr;
      }

      .signal-row {
        grid-template-columns: 1fr;
      }
    }
"""
