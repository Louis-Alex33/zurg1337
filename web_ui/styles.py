from __future__ import annotations

PAGE_STYLE = """
    :root {
      --bg: #f3efe6;
      --paper: #fcfaf4;
      --ink: #1f2b24;
      --muted: #66756c;
      --line: #d9d3c3;
      --clay: #d77842;
      --sage: #6f8f72;
      --gold: #b5862c;
      --inkdeep: #22384d;
      --danger: #b34a3c;
      --shadow: 0 14px 40px rgba(59, 48, 27, 0.08);
      --radius: 18px;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Trebuchet MS", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(215,120,66,0.16), transparent 24rem),
        radial-gradient(circle at top right, rgba(111,143,114,0.18), transparent 22rem),
        linear-gradient(180deg, #f9f5ec 0%, var(--bg) 100%);
    }
    a { color: inherit; text-decoration: none; }
    .page { max-width: 1260px; margin: 0 auto; padding: 32px 24px 64px; }
    .hero {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 24px;
      margin-bottom: 28px;
      align-items: stretch;
    }
    .hero h1 {
      margin: 0 0 12px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2rem, 4vw, 4rem);
      line-height: 0.98;
      letter-spacing: -0.03em;
    }
    .lede { color: var(--muted); max-width: 52rem; font-size: 1.05rem; }
    .eyebrow {
      margin: 0 0 10px;
      color: var(--clay);
      text-transform: uppercase;
      letter-spacing: 0.14em;
      font-weight: 700;
      font-size: 0.76rem;
    }
    .hero-panel, .panel {
      background: rgba(252,250,244,0.92);
      border: 1px solid rgba(217,211,195,0.9);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      backdrop-filter: blur(8px);
    }
    .hero-panel {
      padding: 18px;
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .hero-stat {
      border-radius: 14px;
      padding: 14px;
      background: linear-gradient(135deg, rgba(255,255,255,0.85), rgba(238,234,223,0.85));
      border: 1px solid rgba(217,211,195,0.8);
    }
    .hero-stat strong { display: block; margin-bottom: 4px; }
    .hero-stat span { color: var(--muted); font-size: 0.92rem; }
    .grid { display: grid; gap: 20px; margin-bottom: 20px; }
    .grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .onboarding-grid { grid-template-columns: 1fr; }
    .panel { padding: 22px; }
    .subpanel {
      padding: 18px;
      border-radius: 14px;
      background: rgba(255,255,255,0.55);
      border: 1px solid rgba(217,211,195,0.9);
    }
    .panel-head {
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 16px;
      margin-bottom: 16px;
    }
    .panel h2, .subpanel h2 {
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 1.45rem;
    }
    .onboarding-panel {
      background:
        linear-gradient(135deg, rgba(255,255,255,0.78), rgba(247,241,229,0.92)),
        rgba(252,250,244,0.92);
    }
    .quick-start-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    .quick-start-card {
      border-radius: 16px;
      padding: 16px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.6);
    }
    .quick-start-card h3 {
      margin: 0 0 10px;
      font-size: 1.08rem;
      font-family: Georgia, "Times New Roman", serif;
    }
    .compact-flow {
      margin: 0;
      padding-left: 1.1rem;
      line-height: 1.55;
    }
    .compact-list {
      margin: 0;
      line-height: 1.55;
    }
    .badge {
      border-radius: 999px;
      padding: 7px 11px;
      font-size: 0.78rem;
      background: rgba(31,43,36,0.07);
      color: var(--muted);
    }
    .card-lede {
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.55;
    }
    .card-tip {
      margin: 0 0 16px;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(34,56,77,0.06);
      border: 1px solid rgba(34,56,77,0.08);
      color: var(--inkdeep);
      line-height: 1.5;
    }
    .stack { display: grid; gap: 14px; }
    label {
      display: grid;
      gap: 7px;
      font-weight: 600;
      color: var(--inkdeep);
    }
    input,
    select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px 14px;
      font-size: 0.98rem;
      background: rgba(255,255,255,0.9);
      color: var(--ink);
      appearance: none;
    }
    input:focus,
    select:focus {
      outline: 2px solid rgba(215,120,66,0.26);
      border-color: var(--clay);
    }
    .inline-fields {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .field-help {
      margin: -6px 2px 0;
      font-size: 0.9rem;
      color: var(--muted);
      line-height: 1.45;
    }
    .running-help {
      margin-top: 6px;
    }
    .checkbox-line {
      display: flex;
      align-items: center;
      gap: 10px;
      padding-top: 24px;
    }
    .checkbox-line input {
      width: auto;
      transform: scale(1.2);
    }
    .button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: none;
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 700;
      background: linear-gradient(135deg, #1f2b24, #365448);
      color: #fffdf6;
      cursor: pointer;
      transition: transform 140ms ease, box-shadow 140ms ease;
      box-shadow: 0 10px 26px rgba(31,43,36,0.16);
    }
    .button:hover { transform: translateY(-1px); }
    .button.secondary {
      background: linear-gradient(135deg, #d9d3c3, #ebe4d5);
      color: var(--ink);
      box-shadow: none;
    }
    .print-button {
      background: linear-gradient(135deg, #b5862c, #d7a74a);
      color: #fffdf6;
      box-shadow: 0 12px 28px rgba(181,134,44,0.22);
    }
    .hero-actions {
      margin-top: 16px;
      align-items: center;
      flex-wrap: wrap;
    }
    .audit-summary-preview {
      display: grid;
      gap: 12px;
    }
    .audit-compact-card,
    .audit-metric-card {
      border-radius: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.62);
      padding: 14px;
    }
    .audit-compact-head,
    .audit-domain-cell {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
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
    .audit-metric-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }
    .audit-metric-card strong {
      display: block;
      font-size: 1.7rem;
      font-family: Georgia, "Times New Roman", serif;
      margin-bottom: 4px;
    }
    .audit-metric-card span {
      display: block;
      font-weight: 700;
      color: var(--inkdeep);
    }
    .audit-metric-card p {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .priority-chip,
    .audit-pages-pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.8rem;
      font-weight: 700;
      margin: 2px 6px 2px 0;
    }
    .priority-chip {
      background: rgba(215,120,66,0.12);
      color: #9b5125;
      border: 1px solid rgba(215,120,66,0.18);
    }
    .audit-pages-pill {
      background: rgba(34,56,77,0.08);
      color: var(--inkdeep);
    }
    .health-pill {
      white-space: nowrap;
    }
    .health-good {
      background: rgba(111,143,114,0.18);
      color: #35553d;
    }
    .health-watch {
      background: rgba(181,134,44,0.18);
      color: #8b641d;
    }
    .health-bad {
      background: rgba(179,74,60,0.15);
      color: var(--danger);
    }
    .audit-summary-table td:nth-child(4) {
      min-width: 18rem;
    }
    .audit-report-grid {
      margin-bottom: 0;
    }
    .report-page {
      display: grid;
      gap: 18px;
      margin-bottom: 18px;
    }
    .report-page:last-child {
      margin-bottom: 0;
    }
    .cover-layout-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.95fr);
      gap: 18px;
      align-items: start;
    }
    .cover-side-stack {
      display: grid;
      gap: 14px;
      align-content: start;
    }
    .audit-report-topbar {
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: start;
      margin-bottom: 22px;
    }
    .audit-report-heading {
      max-width: 48rem;
    }
    .audit-report-actions {
      margin-top: 0;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .audit-hero-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.9fr);
      gap: 18px;
      margin-bottom: 18px;
    }
    .audit-hero-card {
      border-radius: 20px;
      border: 1px solid rgba(217,211,195,0.95);
      padding: 22px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.82), rgba(248,243,234,0.92));
      box-shadow: var(--shadow);
    }
    .audit-hero-primary {
      background:
        radial-gradient(circle at top right, rgba(215,120,66,0.12), transparent 16rem),
        linear-gradient(180deg, rgba(255,255,255,0.9), rgba(248,243,234,0.95));
    }
    .audit-hero-secondary {
      background:
        radial-gradient(circle at top left, rgba(34,56,77,0.08), transparent 14rem),
        linear-gradient(180deg, rgba(255,255,255,0.88), rgba(246,241,232,0.95));
    }
    .audit-score-row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .audit-hero-kicker {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.8rem;
      font-weight: 700;
      background: rgba(34,56,77,0.08);
      color: var(--inkdeep);
    }
    .audit-hero-card h2 {
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(1.45rem, 2vw, 2rem);
      line-height: 1.08;
    }
    .audit-hero-copy {
      margin: 0;
      max-width: 44rem;
      color: var(--inkdeep);
      font-size: 1.02rem;
      line-height: 1.7;
    }
    .audit-score-explainer {
      margin: 14px 0 0;
      color: var(--muted);
      line-height: 1.55;
      font-size: 0.94rem;
    }
    .audit-hero-stat-block {
      display: grid;
      gap: 10px;
      margin-bottom: 14px;
    }
    .audit-hero-stat-block strong {
      display: block;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 2rem;
      line-height: 1;
    }
    .audit-hero-stat-block p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .audit-status-chip {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      border-radius: 999px;
      padding: 7px 12px;
      background: rgba(34,56,77,0.08);
      color: var(--inkdeep);
      font-size: 0.82rem;
      font-weight: 700;
    }
    .cover-main-card {
      min-height: 100%;
    }
    .cover-brief-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .cover-brief-card strong {
      font-size: 1.08rem;
      line-height: 1.35;
    }
    .cover-side-card {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.78), rgba(248,243,234,0.88));
    }
    .cover-side-card h2 {
      margin-bottom: 10px;
    }
    .cover-strong-line {
      margin: 0;
      color: var(--inkdeep);
      font-size: 1.08rem;
      font-weight: 700;
      line-height: 1.5;
    }
    .cover-url-list {
      margin-top: 0;
    }
    .cover-url-list li + li {
      margin-top: 8px;
    }
    .cover-url-link {
      color: var(--inkdeep);
      font-weight: 700;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .audit-urgency-line {
      margin: 16px 0 0;
      display: inline-flex;
      width: fit-content;
      border-radius: 999px;
      padding: 7px 12px;
      background: rgba(179,74,60,0.10);
      color: var(--danger);
      font-weight: 800;
      font-size: 0.88rem;
    }
    .positive-panel {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.78), rgba(241,247,238,0.86));
    }
    .score-explanation-panel,
    .method-limits-panel,
    .editorial-opportunities-panel {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.78), rgba(248,243,234,0.88));
    }
    .roadmap-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 16px;
    }
    .roadmap-card {
      border-radius: 8px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.72);
      padding: 15px;
      display: grid;
      gap: 8px;
    }
    .roadmap-card span {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.74rem;
      font-weight: 800;
    }
    .roadmap-card strong {
      color: var(--inkdeep);
      font-size: 1.04rem;
    }
    .roadmap-card p {
      margin: 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .impact-table {
      min-width: 720px;
    }
    .impact-table td:nth-child(2) {
      min-width: 18rem;
      color: var(--inkdeep);
      font-weight: 650;
    }
    .appendix-grid {
      margin-top: 16px;
    }
    .appendix-inner-panel {
      box-shadow: none;
      background: rgba(255,255,255,0.54);
    }
    .appendix-inner-panel h2 {
      font-size: 1.15rem;
    }
    .technical-fact-list dd {
      overflow-wrap: anywhere;
    }
    .technical-page-table {
      min-width: 920px;
    }
    .report-intro-grid,
    .portfolio-kpi-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .report-summary-card {
      border-radius: 16px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.68);
      padding: 14px;
      display: grid;
      gap: 8px;
    }
    .report-summary-card strong {
      color: var(--inkdeep);
      line-height: 1.5;
      font-size: 1rem;
    }
    .report-summary-label {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.76rem;
      font-weight: 700;
    }
    .compact-metric-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .section-intro {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.55;
    }
    .audit-highlight-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .audit-highlight-card {
      border-radius: 16px;
      border: 1px solid rgba(217,211,195,0.92);
      background: rgba(255,255,255,0.68);
      padding: 14px;
    }
    .audit-highlight-card strong {
      display: block;
      font-family: Georgia, "Times New Roman", serif;
      font-size: 1.7rem;
      line-height: 1;
      margin-bottom: 6px;
    }
    .audit-highlight-card span {
      display: block;
      color: var(--inkdeep);
      font-weight: 700;
    }
    .audit-side-label {
      margin: 0 0 14px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.78rem;
      font-weight: 700;
    }
    .audit-fact-list {
      margin: 0;
      display: grid;
      gap: 12px;
    }
    .audit-fact-list div {
      padding-bottom: 12px;
      border-bottom: 1px solid rgba(217,211,195,0.92);
    }
    .audit-fact-list div:last-child {
      padding-bottom: 0;
      border-bottom: none;
    }
    .audit-fact-list dt {
      margin: 0 0 4px;
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 700;
    }
    .audit-fact-list dd {
      margin: 0;
      color: var(--inkdeep);
      line-height: 1.5;
      font-weight: 700;
    }
    .audit-path {
      word-break: break-word;
      font-weight: 600;
    }
    .audit-print-note {
      margin: 18px 0 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 0.92rem;
    }
    .audit-technical-panel {
      margin-bottom: 18px;
    }
    .audit-tech-details summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--inkdeep);
      list-style: none;
    }
    .audit-tech-details summary::-webkit-details-marker {
      display: none;
    }
    .audit-tech-grid {
      margin-top: 14px;
      margin-bottom: 0;
    }
    .audit-report-shell > .subpanel {
      margin-bottom: 18px;
      padding: 22px;
      background:
        linear-gradient(180deg, rgba(255,255,255,0.74), rgba(248,243,234,0.86));
    }
    .audit-report-shell > .subpanel h2 {
      margin-bottom: 14px;
    }
    .audit-report-shell .audit-metric-card {
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.82);
    }
    .audit-report-shell .signal-row-card,
    .audit-report-shell .page-priority-card,
    .audit-report-shell .pair-card {
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.84);
    }
    .audit-report-shell .signal-row-card {
      border: 1px solid rgba(217,211,195,0.92);
    }
    .audit-report-shell .signal-row,
    .audit-report-shell .page-priority-card,
    .audit-report-shell .pair-card {
      border: none;
      background: transparent;
      padding: 0;
    }
    .audit-report-shell .copy-block {
      border-radius: 18px;
      padding: 18px 20px;
      background: linear-gradient(135deg, rgba(34,56,77,0.08), rgba(255,255,255,0.82));
    }
    .audit-report-shell .copy-block p {
      font-size: 1rem;
    }
    .audit-report-shell .clean-list li + li {
      margin-top: 10px;
    }
    .signal-list,
    .page-priority-list,
    .pair-list {
      display: grid;
      gap: 12px;
    }
    .signal-row-card {
      border-radius: 14px;
      padding: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.62);
    }
    .signal-row,
    .page-priority-card,
    .pair-card {
      border-radius: 14px;
      padding: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.62);
    }
    .signal-row {
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 10px;
      align-items: center;
    }
    .signal-help {
      margin: 10px 0 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .signal-pill.signal-high {
      background: rgba(179,74,60,0.14);
      color: var(--danger);
    }
    .signal-pill.signal-medium {
      background: rgba(181,134,44,0.18);
      color: #8b641d;
    }
    .page-priority-meta {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .page-client-brief {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 14px;
    }
    .page-client-brief div {
      border-radius: 8px;
      border: 1px solid rgba(217,211,195,0.86);
      background: rgba(255,255,255,0.58);
      padding: 11px 12px;
      display: grid;
      gap: 5px;
    }
    .page-client-brief span {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.07em;
      font-size: 0.7rem;
      font-weight: 800;
    }
    .page-client-brief strong {
      color: var(--inkdeep);
      line-height: 1.45;
      font-size: 0.92rem;
    }
    .page-url {
      display: block;
      font-weight: 700;
      color: var(--inkdeep);
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .pair-card p {
      margin: 8px 0 0;
      line-height: 1.45;
      color: var(--inkdeep);
    }
    .signal-details {
      margin-top: 12px;
      border-top: 1px solid rgba(217,211,195,0.85);
      padding-top: 12px;
    }
    .signal-details summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--inkdeep);
    }
    .signal-example-list {
      margin-top: 10px;
    }
    .raw-json-box summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--inkdeep);
      margin-bottom: 12px;
    }
    .copy-block {
      padding: 16px 18px;
      border-radius: 14px;
      border: 1px solid rgba(34,56,77,0.12);
      background: linear-gradient(135deg, rgba(34,56,77,0.06), rgba(255,255,255,0.7));
    }
    .copy-block p {
      margin: 0;
      line-height: 1.7;
      color: var(--inkdeep);
      white-space: pre-wrap;
    }
    .portfolio-page {
      background:
        linear-gradient(180deg, rgba(255,255,255,0.38), rgba(255,255,255,0.05));
      border-radius: 22px;
      padding: 4px;
    }
    .portfolio-hero-grid {
      align-items: stretch;
    }
    .portfolio-method-strip {
      margin-top: 12px;
      padding: 16px;
    }
    .portfolio-method-strip .clean-list {
      margin-top: 6px;
    }
    .ghost-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 999px;
      padding: 10px 14px;
      border: 1px solid rgba(217,211,195,0.95);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      font-weight: 700;
      cursor: pointer;
    }
    .ghost-button.danger {
      color: var(--danger);
      border-color: rgba(179,74,60,0.25);
      background: rgba(179,74,60,0.08);
    }
    .panel-actions { margin-top: 18px; display: flex; gap: 10px; }
    .panel-tools {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }
    .inline-form { margin: 0; }
    .status-pill {
      border-radius: 999px;
      padding: 7px 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.72rem;
    }
    .status-queued { background: rgba(181,134,44,0.12); color: var(--gold); }
    .status-running { background: rgba(34,56,77,0.12); color: var(--inkdeep); }
    .status-done { background: rgba(111,143,114,0.18); color: var(--sage); }
    .status-cancelled { background: rgba(179,74,60,0.12); color: #8c4538; }
    .status-failed { background: rgba(179,74,60,0.14); color: var(--danger); }
    .job-card {
      display: grid;
      gap: 8px;
      padding: 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.58);
      border: 1px solid rgba(217,211,195,0.92);
      margin-bottom: 10px;
    }
    .job-main-link {
      display: block;
    }
    .job-meta {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.92rem;
    }
    .job-top {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
    }
    .job-actions {
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      flex-wrap: wrap;
    }
    .job-delete {
      padding: 8px 12px;
      font-size: 0.84rem;
    }
    .muted, .subtle-link { color: var(--muted); }
    .flow {
      margin: 0;
      padding-left: 1.2rem;
      color: var(--inkdeep);
      line-height: 1.7;
    }
    .table-wrap {
      overflow: auto;
      border-radius: 14px;
      border: 1px solid rgba(217,211,195,0.9);
      background: rgba(255,255,255,0.68);
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
      border-collapse: collapse;
      min-width: 540px;
      font-size: 0.92rem;
    }
    th, td {
      padding: 10px 12px;
      border-bottom: 1px solid rgba(217,211,195,0.85);
      text-align: left;
      vertical-align: top;
    }
    th {
      position: sticky;
      top: 0;
      background: #f5efe4;
      z-index: 1;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }
    .file-shell h1 {
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(1.8rem, 3vw, 3rem);
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
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 6px 10px;
      font-size: 0.8rem;
      font-weight: 700;
      white-space: nowrap;
    }
    .domain-pill {
      background: rgba(34,56,77,0.10);
      color: var(--inkdeep);
    }
    .provider-pill {
      background: rgba(181,134,44,0.14);
      color: #8b641d;
    }
    .soft-pill {
      background: rgba(111,143,114,0.16);
      color: #43624b;
    }
    .score-high {
      background: rgba(111,143,114,0.2);
      color: #35553d;
    }
    .score-mid {
      background: rgba(181,134,44,0.18);
      color: #8b641d;
    }
    .score-low {
      background: rgba(215,120,66,0.18);
      color: #9b5125;
    }
    .cell-empty {
      background: rgba(255,255,255,0.3);
    }
    .cell-text {
      max-width: 28rem;
      line-height: 1.45;
      color: var(--inkdeep);
    }
    .log-box {
      margin: 0;
      max-height: 360px;
      overflow: auto;
      background: #1d2622;
      color: #eef4ed;
      padding: 16px;
      border-radius: 14px;
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
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.6);
      border: 1px solid rgba(217,211,195,0.9);
      display: grid;
      gap: 4px;
    }
    .meta-grid strong { font-size: 0.82rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .clean-list {
      margin: 0;
      padding-left: 1rem;
      line-height: 1.7;
    }
    .error-box {
      margin-bottom: 18px;
      padding: 14px 16px;
      border-radius: 14px;
      border: 1px solid rgba(179,74,60,0.26);
      background: rgba(179,74,60,0.08);
      color: var(--danger);
      font-weight: 700;
    }
    .flash-banner {
      margin-bottom: 20px;
      padding: 14px 18px;
      border-radius: 14px;
      border: 1px solid rgba(111,143,114,0.24);
      background: rgba(111,143,114,0.12);
      color: #35553d;
      font-weight: 700;
    }
    .accent-clay { border-top: 4px solid var(--clay); }
    .accent-sage { border-top: 4px solid var(--sage); }
    .accent-ink { border-top: 4px solid var(--inkdeep); }
    .accent-gold { border-top: 4px solid var(--gold); }
    @page {
      size: A4;
      margin: 14mm;
    }
    @media print {
      body {
        background: #ffffff;
      }
      .page {
        max-width: none;
        padding: 0;
      }
      .no-print,
      .panel-actions,
      .raw-json-box,
      .hero,
      .flash-banner {
        display: none !important;
      }
      .panel,
      .subpanel,
      .audit-hero-card,
      .audit-metric-card,
      .signal-row-card,
      .page-priority-card,
      .pair-card,
      .copy-block,
      .audit-highlight-card {
        background: #ffffff !important;
        box-shadow: none !important;
        border: 1px solid #d8d3c6 !important;
        backdrop-filter: none !important;
      }
      .audit-report-shell {
        padding: 0;
        border: none;
        box-shadow: none;
        background: transparent;
      }
      .audit-report-topbar {
        margin-bottom: 14px;
      }
      .audit-hero-grid,
      .cover-layout-grid,
      .grid.two,
      .audit-metric-grid,
      .audit-highlight-grid,
      .roadmap-grid,
      .report-intro-grid,
      .portfolio-kpi-grid,
      .file-meta {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
      }
      .report-page {
        page-break-after: always;
        break-after: page;
      }
      .report-page:last-child {
        page-break-after: auto;
        break-after: auto;
      }
      .audit-report-shell > .subpanel,
      .audit-hero-card,
      .audit-metric-card,
      .signal-row-card,
      .page-priority-card,
      .pair-card,
      .copy-block {
        break-inside: avoid;
        page-break-inside: avoid;
      }
      .file-shell h1 {
        font-size: 28pt;
      }
      .audit-hero-copy,
      .copy-block p,
      .clean-list,
      .signal-help {
        font-size: 11pt;
        line-height: 1.55;
      }
      a {
        color: #111111;
        text-decoration: none;
      }
    }
    @media (max-width: 900px) {
      .hero, .grid.two, .inline-fields, .meta-grid, .audit-metric-grid, .quick-start-grid, .audit-hero-grid, .audit-highlight-grid, .report-intro-grid, .portfolio-kpi-grid, .compact-metric-grid, .cover-layout-grid, .cover-brief-grid, .roadmap-grid, .page-client-brief {
        grid-template-columns: 1fr;
      }
      .page { padding: 20px 14px 40px; }
      .panel { padding: 18px; }
      .audit-report-topbar {
        flex-direction: column;
      }
      .audit-report-actions {
        width: 100%;
        justify-content: flex-start;
      }
    }
"""
