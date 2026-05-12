from __future__ import annotations

GSC_REPORT_STYLE = """
    :root {
      --paper:#faf9f4; --paper-warm:#f3f0e6; --paper-outer:#e7e3d6;
      --ink:#0c0f14; --ink-soft:#2a2f3a; --ink-mid:#4b5260; --muted:#7a7e89; --muted-soft:#a8a89e;
      --line:#e0dcce; --line-strong:#c9c4b1; --rule:#1a1d24;
      --accent:#1f3a8a; --accent-soft:#e6ecf7;
      --hot:#b45309; --hot-soft:#f7ecdb;
      --gain:#166534; --gain-soft:#dcefe1;
      --danger:#991b1b; --danger-soft:#f4dcdc;
      --warn:#92400e; --warn-soft:#f5e4cc;
      --shadow-card:0 1px 1px rgba(12,15,20,.04),0 20px 50px -20px rgba(12,15,20,.10);
      --serif:"Fraunces","Iowan Old Style","Hoefler Text",Georgia,serif;
      --sans:"Inter",ui-sans-serif,system-ui,sans-serif;
      --mono:"JetBrains Mono",ui-monospace,"SF Mono",Menlo,monospace;
    }
    *{box-sizing:border-box;}
    html,body{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#efece1 0%,transparent 60%),var(--paper-outer);color:var(--ink-soft);font-family:var(--sans);font-size:13.5px;line-height:1.6;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;font-feature-settings:"ss01","cv11","tnum";}
    a{color:var(--accent);overflow-wrap:anywhere;}
    .doc{max-width:920px;margin:0 auto;padding:40px 0 80px;display:grid;gap:26px;}
    .page{background:var(--paper);border-radius:4px;box-shadow:var(--shadow-card);padding:64px 74px 88px;position:relative;min-height:1180px;display:grid;gap:28px;align-content:start;overflow:hidden;}
    .runhead{position:absolute;top:30px;left:74px;right:74px;display:flex;justify-content:space-between;align-items:baseline;font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--line);padding-bottom:16px;font-weight:600;}
    .runhead .mark{color:var(--ink);letter-spacing:.16em;font-weight:700;}
    .pagenum{position:absolute;bottom:30px;left:74px;right:74px;display:flex;justify-content:space-between;font-size:10.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);padding-top:14px;border-top:1px solid var(--line);font-weight:600;}
    .pagenum .num{color:var(--ink);font-family:var(--serif);font-style:italic;text-transform:none;letter-spacing:-.01em;font-size:12px;}
    .page.no-running .runhead,.page.no-running .pagenum{display:none;}
    .display{font-family:var(--serif);font-weight:400;letter-spacing:-.02em;color:var(--ink);}
    .smallcaps{text-transform:uppercase;letter-spacing:.16em;font-weight:700;font-size:11px;color:var(--muted);}
    .eyebrow{margin:0;text-transform:uppercase;letter-spacing:.18em;font-size:10.5px;font-weight:700;color:var(--muted);}
    .eyebrow .num{color:var(--ink);font-family:var(--serif);font-style:italic;margin-right:10px;text-transform:none;letter-spacing:-.01em;font-weight:500;font-size:13px;}
    .section-title{margin:0;font-family:var(--serif);font-weight:400;font-size:38px;line-height:1.08;letter-spacing:-.02em;color:var(--ink);}
    .section-title em{font-weight:400;font-style:italic;color:var(--ink);}
    .section-title-sm{margin:0;font-family:var(--serif);font-weight:400;font-size:22px;line-height:1.15;letter-spacing:-.015em;color:var(--ink);}
    .lede{margin:0;color:var(--ink-mid);font-size:15px;line-height:1.65;max-width:56ch;text-wrap:pretty;}
    .rule{height:1px;background:var(--line);}
    .rule-strong{height:1px;background:var(--rule);}
    .rule-short{width:56px;height:2px;background:var(--ink);}
    .tnum{font-variant-numeric:tabular-nums;}
    .url-mono{font-family:var(--mono);font-size:11.5px;color:var(--ink-soft);background:var(--paper-warm);padding:2px 6px;border-radius:3px;word-break:break-all;}
    /* Cover */
    .page.cover{padding:0;background:var(--paper);display:grid;grid-template-rows:auto 1fr auto;min-height:1280px;background-image:linear-gradient(180deg,transparent 0%,transparent 60%,var(--paper-warm) 100%);}
    .cover-mast{padding:36px 64px 24px;display:flex;justify-content:space-between;align-items:flex-start;border-bottom:1px solid var(--rule);}
    .wordmark{font-family:var(--serif);font-weight:500;font-size:17px;letter-spacing:-.01em;color:var(--ink);display:flex;align-items:baseline;gap:6px;}
    .wordmark em{font-style:italic;font-weight:400;color:var(--ink-mid);}
    .wordmark .glyph{display:inline-block;width:22px;height:22px;border:1.5px solid var(--ink);transform:rotate(-12deg);margin-right:12px;position:relative;top:4px;}
    .wordmark .glyph::after{content:"";position:absolute;inset:4px;background:var(--ink);transform:rotate(12deg);}
    .ref-block{text-align:right;font-family:var(--mono);font-size:11px;letter-spacing:.04em;color:var(--muted);line-height:1.6;}
    .ref-block strong{color:var(--ink);font-weight:600;}
    .cover-body{padding:80px 64px 40px;display:grid;grid-template-columns:1fr;gap:36px;align-content:end;}
    .cover-cat{margin:0;text-transform:uppercase;letter-spacing:.22em;font-size:11px;font-weight:700;color:var(--ink);}
    .cover-cat .dot{color:var(--muted);margin:0 10px;}
    .cover-title{margin:0;font-family:var(--serif);font-weight:300;font-size:88px;line-height:0.96;letter-spacing:-.03em;color:var(--ink);max-width:16ch;word-break:break-word;}
    .cover-tag{margin:0;font-family:var(--serif);font-style:italic;font-weight:400;font-size:22px;line-height:1.35;color:var(--ink-mid);max-width:36ch;letter-spacing:-.01em;}
    .cover-pull{margin-top:8px;padding:24px 0 0;border-top:1px solid var(--rule);display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:28px;}
    .pull-label{font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);font-weight:700;max-width:12ch;line-height:1.4;}
    .pull-number{font-family:var(--serif);font-weight:300;font-size:64px;line-height:1;letter-spacing:-.03em;color:var(--ink);font-variant-numeric:tabular-nums;}
    .pull-number .dash{color:var(--hot);margin:0 6px;font-style:italic;}
    .pull-unit{text-align:right;color:var(--muted);font-size:12px;max-width:18ch;line-height:1.4;}
    .cover-foot{padding:22px 64px 36px;background:var(--paper-warm);border-top:1px solid var(--line);display:grid;grid-template-columns:repeat(4,1fr);gap:16px;}
    .cover-foot div{display:grid;gap:4px;}
    .cover-foot .lbl{text-transform:uppercase;letter-spacing:.16em;font-size:9.5px;font-weight:700;color:var(--muted);}
    .cover-foot strong{font-family:var(--serif);font-weight:400;font-style:italic;color:var(--ink);font-size:15px;letter-spacing:-.005em;}
    /* Toolbar / nav */
    .report-toolbar{position:sticky;top:0;z-index:20;max-width:920px;margin:0 auto;padding:10px 30px;background:rgba(250,249,244,.96);border-bottom:1px solid var(--line);display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap;}
    .report-toolbar-button{appearance:none;border:1px solid var(--line-strong);background:var(--paper);color:var(--ink-soft);border-radius:4px;padding:7px 12px;font:600 11.5px/1 var(--sans);text-decoration:none;cursor:pointer;letter-spacing:.02em;}
    .report-toolbar-button:hover{background:var(--paper-warm);}
    .language-toggle.is-active{background:var(--ink);border-color:var(--ink);color:var(--paper);}
    .language-toggle-group{display:inline-flex;gap:6px;}
    nav.gsc-nav{position:sticky;top:52px;background:rgba(250,249,244,.96);border-bottom:1px solid var(--line);padding:10px 74px;display:flex;gap:8px;flex-wrap:wrap;z-index:10;max-width:920px;margin:0 auto;}
    nav.gsc-nav a{color:var(--ink-mid);text-decoration:none;font:600 11px/1 var(--sans);letter-spacing:.08em;text-transform:uppercase;padding:5px 10px;border-radius:3px;border:1px solid transparent;}
    nav.gsc-nav a:hover{border-color:var(--line);background:var(--paper-warm);color:var(--ink);}
    /* Sections */
    .report-section{margin-top:0;padding-top:0;border-top:none;}
    .section-header{margin-bottom:22px;display:grid;gap:8px;}
    .section-header h2{margin:0;font-family:var(--serif);font-weight:400;font-size:32px;line-height:1.1;letter-spacing:-.02em;color:var(--ink);}
    .section-header h2 em{font-style:italic;}
    .section-intro{margin:0;color:var(--ink-mid);font-size:13.5px;line-height:1.6;}
    .reliability-note,.page-constat,.why{color:var(--ink-mid);}
    /* Source box */
    .source-box{padding:16px 22px;background:var(--paper-warm);border-left:3px solid var(--line-strong);font-size:12px;color:var(--ink-mid);}
    .source-list{margin:0;padding-left:18px;}
    /* KPI grid */
    .kpi-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;border-top:1px solid var(--rule);margin:18px 0;}
    .kpi-card{padding:18px 16px 16px;border-bottom:1px solid var(--line);border-right:1px solid var(--line);break-inside:avoid;page-break-inside:avoid;}
    .kpi-card:nth-child(3n){border-right:none;}
    .kpi-label{display:block;color:var(--muted);font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;margin-bottom:6px;}
    .kpi-value{font-family:var(--serif);font-weight:400;font-size:30px;line-height:1;letter-spacing:-.02em;color:var(--ink);font-variant-numeric:tabular-nums;}
    .kpi-value.is-hot{color:var(--hot);font-style:italic;}
    .kpi-value.is-accent{color:var(--accent);}
    .kpi-note{font-size:11px;color:var(--muted);margin-top:4px;}
    /* Executive summary */
    .executive-summary{padding:18px 22px;border-left:3px solid var(--accent);background:var(--accent-soft);font-size:14px;line-height:1.65;color:var(--ink-soft);}
    /* Estimate box */
    .estimate-box{padding:18px 22px;background:var(--hot-soft);border-left:3px solid var(--hot);font-size:13.5px;}
    .estimate-box strong{display:block;font-family:var(--serif);font-weight:400;font-size:24px;letter-spacing:-.02em;color:var(--ink);margin-bottom:6px;line-height:1.1;}
    .estimate-box p{margin:0;color:var(--ink-mid);}
    /* Priority ladder */
    .priorities-list{display:grid;gap:0;border-top:1px solid var(--rule);}
    .priority-item{display:grid;grid-template-columns:32px 1fr auto;gap:18px;align-items:baseline;padding:18px 0;border-bottom:1px solid var(--line);break-inside:avoid;}
    .priority-number{font-family:var(--serif);font-style:italic;font-size:22px;color:var(--muted);letter-spacing:-.01em;}
    .priority-item:first-child .priority-number{color:var(--hot);font-weight:500;}
    .priority-meta{display:grid;gap:5px;color:var(--ink-mid);font-size:12.5px;}
    .priority-meta strong{display:block;color:var(--ink);font-family:var(--serif);font-weight:500;font-size:16px;letter-spacing:-.005em;}
    /* Page cards */
    .page-card{background:var(--paper);border-top:1px solid var(--rule);padding:22px 0 24px;display:block;break-inside:avoid;page-break-inside:avoid;margin-bottom:0;}
    .page-card.has-rank{display:grid;grid-template-columns:28px 1fr;gap:22px;}
    .snippet-card,.appendix-card,.query-card{background:var(--paper);border-top:1px solid var(--line);padding:18px 0;break-inside:avoid;page-break-inside:avoid;margin-bottom:0;}
    .page-card-rank{font-family:var(--serif);font-style:italic;font-size:26px;color:var(--muted);line-height:1;letter-spacing:-.02em;padding-top:2px;}
    .page-card.is-top .page-card-rank{color:var(--hot);}
    .page-card-main{display:grid;gap:14px;}
    .page-card-header,.card-head{display:grid;grid-template-columns:1fr auto;gap:18px;align-items:start;margin-bottom:0;}
    .page-slug{display:block;font-family:var(--serif);font-weight:500;font-size:18px;letter-spacing:-.01em;color:var(--ink);line-height:1.2;overflow-wrap:anywhere;}
    .page-url{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:4px;letter-spacing:.02em;text-decoration:none;}
    .priority-badge{white-space:nowrap;border-radius:999px;padding:4px 12px;font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;}
    .priority-badge--high{color:var(--danger);background:var(--danger-soft);border:1px solid var(--danger-soft);}
    .priority-badge--medium{color:var(--warn);background:var(--warn-soft);border:1px solid var(--warn-soft);}
    .priority-badge--low,.priority-badge--dead{color:var(--gain);background:var(--gain-soft);border:1px solid var(--gain-soft);}
    .page-metrics,.data-grid{display:grid;grid-template-columns:repeat(5,minmax(80px,1fr));border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin:12px 0;}
    .metric,.data-item{padding:12px 14px 12px 0;border-right:1px solid var(--line);display:grid;gap:2px;min-width:0;}
    .metric:nth-child(n+2),.data-item:nth-child(n+2){padding-left:14px;}
    .metric:last-child,.data-item:last-child{border-right:0;padding-right:0;}
    .metric-label,.data-label{font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;display:block;margin-bottom:0;}
    .metric-value{font-family:var(--serif);font-weight:400;font-size:22px;letter-spacing:-.02em;color:var(--ink);line-height:1.1;font-variant-numeric:tabular-nums;display:block;overflow-wrap:break-word;word-break:break-word;}
    .data-value{font-family:var(--serif);font-weight:400;font-size:13px;letter-spacing:-.01em;color:var(--ink);line-height:1.4;display:block;overflow-wrap:break-word;word-break:break-word;}
    .metric.delta .metric-value{color:var(--hot);font-style:italic;}
    .mini-label{font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;display:block;}
    .constat-label,.actions-label{font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;display:block;margin-bottom:4px;}
    /* Position bar */
    .position-bar{display:flex;align-items:center;gap:10px;margin:-2px 0 14px;}
    .position-bar-label{color:var(--muted);font:700 9.5px/1.2 var(--sans);text-transform:uppercase;letter-spacing:.14em;min-width:140px;}
    .position-bar-track{flex:1;height:6px;background:var(--line);border-radius:999px;overflow:hidden;}
    .position-bar-fill{height:100%;border-radius:999px;background:var(--ink);transition:width 600ms ease;}
    .position-bar-value{color:var(--muted);font:600 11px/1 var(--mono);min-width:30px;text-align:right;}
    .actions-list,.actions{margin:0;padding-left:18px;}
    .actions-list li,.actions li{margin-bottom:5px;color:var(--ink-soft);}
    .insight-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;border-top:1px solid var(--line);margin-top:12px;padding-top:12px;}
    /* Tags / chips */
    .tag{display:inline-block;padding:3px 10px;border-radius:999px;font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;font-weight:700;color:var(--ink);border:1px solid var(--line-strong);background:transparent;white-space:nowrap;}
    .tag.hot{background:var(--hot);color:#fff;border-color:var(--hot);}
    .tag.danger{background:var(--danger);color:#fff;border-color:var(--danger);}
    .tag.warn{background:var(--warn-soft);color:var(--warn);border-color:var(--warn-soft);}
    .tag.gain{background:var(--gain-soft);color:var(--gain);border-color:var(--gain-soft);}
    .chip-row{display:flex;flex-wrap:wrap;gap:6px;}
    .type-tag,.chip{display:inline-block;border-radius:999px;padding:3px 10px;background:var(--accent-soft);color:var(--accent);font:700 10.5px/1.3 var(--sans);text-transform:uppercase;letter-spacing:.1em;}
    /* Action chips */
    .action-chip{display:inline-block;padding:3px 9px;font-size:10.5px;text-transform:uppercase;letter-spacing:.12em;font-weight:700;border-radius:999px;white-space:nowrap;font-family:var(--sans);}
    .action-chip.rewrite{background:var(--hot-soft);color:var(--warn);}
    .action-chip.expand{background:var(--accent-soft);color:var(--accent);}
    .action-chip.link{background:var(--gain-soft);color:var(--gain);}
    .action-chip.new{background:var(--paper-warm);color:var(--ink-mid);border:1px solid var(--line-strong);}
    .action-chip.faq{background:var(--warn-soft);color:var(--warn);}
    /* Filter bar */
    .filter-bar,.summary-links{display:flex;flex-wrap:wrap;gap:6px;margin:14px 0;}
    .filter-group{display:flex;align-items:center;flex-wrap:wrap;gap:6px;}
    .filter-label{color:var(--muted);font:700 9.5px/1 var(--sans);text-transform:uppercase;letter-spacing:.14em;margin-right:2px;}
    .filter-btn,.summary-link{appearance:none;border:1px solid var(--line-strong);background:var(--paper);color:var(--ink-mid);border-radius:3px;padding:5px 10px;font:600 11px/1 var(--sans);letter-spacing:.04em;text-decoration:none;cursor:pointer;}
    .filter-btn.is-active{background:var(--ink);border-color:var(--ink);color:var(--paper);}
    .filter-btn:hover{background:var(--paper-warm);}
    .is-filtered-out{display:none!important;}
    /* CTR track */
    .ctr-row{margin-top:4px;display:grid;gap:6px;}
    .ctr-row-stat{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;}
    .ctr-row-stat b{color:var(--ink);font-family:var(--serif);font-size:14px;font-weight:500;letter-spacing:-.01em;}
    .ctr-track{position:relative;height:8px;background:var(--line);border-radius:999px;overflow:hidden;}
    .ctr-band{position:absolute;top:0;bottom:0;background:var(--gain-soft);border-left:1px solid var(--gain);border-right:1px solid var(--gain);}
    .ctr-now{position:absolute;top:0;bottom:0;left:0;background:var(--ink);border-radius:999px;}
    .ctr-axis{display:flex;justify-content:space-between;font-size:10px;color:var(--muted-soft);font-variant-numeric:tabular-nums;margin-top:2px;font-family:var(--mono);}
    .gain-line{margin-top:8px;font-family:var(--serif);font-size:14px;font-style:italic;color:var(--gain);letter-spacing:-.005em;}
    .gain-line b{font-style:normal;font-weight:500;}
    /* Note block */
    .note-block{margin-top:6px;padding:10px 14px;border-left:2px solid var(--hot);background:var(--hot-soft);color:var(--warn);font-size:12px;line-height:1.55;}
    .note-block b{color:var(--ink);}
    /* SERP mockup */
    .serp-pair{display:grid;grid-template-columns:1fr 24px 1fr;gap:18px;align-items:stretch;margin:8px 0 0;}
    .serp{background:#fff;border:1px solid var(--line);border-radius:8px;padding:16px 18px 18px;display:grid;gap:4px;position:relative;}
    .serp.after{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent-soft);}
    .serp-stamp{position:absolute;top:-10px;left:14px;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;font-weight:700;background:var(--paper);color:var(--muted);padding:0 8px;}
    .serp.after .serp-stamp{color:var(--accent);}
    .serp-favicon{display:flex;align-items:center;gap:8px;margin-bottom:4px;}
    .serp-favicon .dot{width:22px;height:22px;border-radius:50%;background:var(--paper-warm);border:1px solid var(--line);}
    .serp-favicon .domain{display:grid;line-height:1.25;}
    .serp-favicon .domain .site{font-size:12.5px;color:#202124;font-weight:500;}
    .serp-favicon .domain .url{font-size:11px;color:#4d5156;font-family:var(--mono);}
    .serp-title{font-family:Arial,sans-serif;color:#1a0dab;font-size:17px;font-weight:400;line-height:1.3;letter-spacing:-.005em;margin:4px 0 2px;}
    .serp.after .serp-title{font-weight:500;}
    .serp-desc{font-family:Arial,sans-serif;color:#4d5156;font-size:12.5px;line-height:1.45;margin:0;}
    .serp-desc mark{background:#fef3c7;color:inherit;padding:0 1px;}
    .serp-arrow{display:grid;place-items:center;color:var(--muted);font-family:var(--serif);font-style:italic;font-size:16px;}
    .serp-notes{margin-top:14px;padding:14px 18px;background:var(--paper-warm);border-radius:4px;display:grid;grid-template-columns:1fr 1fr;gap:18px;}
    .serp-notes .col{display:grid;gap:4px;}
    .serp-notes h5{margin:0;font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;}
    .serp-notes p{margin:0;font-size:12.5px;color:var(--ink-soft);line-height:1.55;}
    .serp-notes p b{color:var(--ink);}
    .snippet-block{margin-top:8px;padding-top:22px;border-top:1px solid var(--rule);}
    .snippet-block:first-of-type{border-top:0;padding-top:0;}
    .snippet-title-row{display:flex;justify-content:space-between;align-items:baseline;gap:18px;margin-bottom:4px;}
    .snippet-title-row h4{margin:0;font-family:var(--serif);font-weight:500;font-size:18px;letter-spacing:-.01em;color:var(--ink);}
    .snippet-meta{font-size:11.5px;color:var(--muted);font-variant-numeric:tabular-nums;}
    .snippet-meta b{color:var(--ink);font-weight:600;}
    /* Tables */
    .table-card{border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin-top:8px;}
    .table-card table{width:100%;border-collapse:collapse;font-size:12px;}
    .table-card thead th{text-align:left;text-transform:uppercase;letter-spacing:.12em;font-size:9.5px;font-weight:700;color:var(--muted);padding:12px 8px 12px 0;border-bottom:1px solid var(--rule);}
    .table-card thead th.r{text-align:right;}
    .table-card td{padding:12px 8px 12px 0;vertical-align:top;border-bottom:1px solid var(--line);color:var(--ink-soft);line-height:1.55;}
    .table-card td.r{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600;font-family:var(--serif);font-size:13.5px;letter-spacing:-.01em;}
    .table-card td.r em{font-style:italic;color:var(--hot);}
    .table-card tr:last-child td{border-bottom:0;}
    .table-card td .qrow{display:grid;gap:3px;}
    .table-card td .qprimary{color:var(--ink);font-weight:500;}
    .table-card td .qsecondary{color:var(--muted);font-size:11.5px;}
    .table-card td .urlcell{font-family:var(--mono);font-size:11.5px;color:var(--ink);word-break:break-all;}
    .table-card td .urlcell em{color:var(--muted);font-style:normal;}
    /* Compact table */
    .compact-table{width:100%;border-collapse:collapse;background:var(--paper);border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);font-size:11.5px;}
    .compact-table th,.compact-table td{border-bottom:1px solid var(--line);padding:10px 8px;text-align:left;vertical-align:top;}
    .compact-table th{background:var(--paper-warm);color:var(--muted);font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;font-weight:700;border-bottom:1px solid var(--rule);}
    .compact-table tr:last-child td{border-bottom:0;}
    .compact-table .url-cell{overflow-wrap:anywhere;max-width:220px;font-family:var(--mono);font-size:11px;}
    /* Cluster cards */
    .cluster-section{display:grid;gap:16px;}
    .cluster-card{border-top:1px solid var(--rule);padding:22px 0 0;display:grid;gap:16px;}
    .cluster-head{display:grid;grid-template-columns:1fr auto;gap:16px;align-items:start;}
    .cluster-head h3{margin:0;font-family:var(--serif);font-weight:500;font-size:19px;letter-spacing:-.01em;color:var(--ink);}
    .cluster-head .id{display:block;font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:4px;letter-spacing:.05em;}
    .cluster-grid{display:grid;grid-template-columns:1fr 1.1fr;gap:28px;}
    .cluster-grid h4{margin:0 0 10px;font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;}
    .query-chips{display:flex;flex-wrap:wrap;gap:6px;}
    .query-chips .chip{display:inline-block;padding:4px 10px;background:var(--paper-warm);color:var(--ink-soft);border-radius:3px;font-size:11.5px;border:1px solid var(--line);}
    .url-list{margin:0;padding:0;list-style:none;display:grid;gap:6px;}
    .url-list li{display:grid;grid-template-columns:18px 1fr;gap:8px;color:var(--ink-soft);font-family:var(--mono);font-size:11.5px;word-break:break-all;align-items:baseline;}
    .url-list li::before{content:"—";color:var(--muted);font-family:var(--serif);font-style:italic;}
    .cluster-action{padding:14px 16px;background:var(--paper-warm);border-left:2px solid var(--ink);font-family:var(--serif);font-style:italic;font-size:14px;color:var(--ink-soft);line-height:1.55;}
    .cluster-action b{font-style:normal;font-weight:600;color:var(--ink);}
    /* Variant pairs */
    .variant-row{border-top:1px solid var(--line);padding:16px 0;display:grid;grid-template-columns:1fr 28px 1fr 180px;gap:16px;align-items:center;}
    .variant-row:first-of-type{border-top:1px solid var(--rule);}
    .variant-row:last-of-type{border-bottom:1px solid var(--rule);}
    .variant-url-cell{font-family:var(--mono);font-size:11.5px;color:var(--ink);word-break:break-all;line-height:1.55;}
    .variant-url-cell .badge{display:block;font-family:var(--sans);font-size:9.5px;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-weight:700;margin-bottom:4px;}
    .variant-url-cell.canonical .badge{color:var(--accent);}
    .variant-arrow{text-align:center;color:var(--muted);font-family:var(--serif);font-style:italic;font-size:22px;}
    .variant-meta{display:grid;grid-template-columns:repeat(3,1fr);text-align:right;gap:8px;}
    .variant-meta dt{font-size:9px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-weight:700;margin:0 0 2px;}
    .variant-meta dd{margin:0;font-family:var(--serif);font-weight:500;color:var(--ink);font-variant-numeric:tabular-nums;font-size:14px;letter-spacing:-.01em;}
    /* 30-day plan */
    .plan-grid{display:grid;grid-template-columns:100px 1fr;gap:0;border-top:1px solid var(--rule);}
    .plan-week{border-bottom:1px solid var(--line);display:contents;}
    .plan-week:last-child .plan-when,.plan-week:last-child .plan-body{border-bottom:1px solid var(--rule);}
    .plan-when,.plan-body{padding:22px 0;border-bottom:1px solid var(--line);}
    .plan-when{padding-right:24px;display:grid;gap:4px;align-content:start;}
    .plan-when .num{font-family:var(--serif);font-style:italic;font-size:32px;line-height:1;letter-spacing:-.02em;color:var(--hot);}
    .plan-when .label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.16em;font-weight:700;}
    .plan-body{padding-left:24px;border-left:1px solid var(--line);display:grid;gap:8px;}
    .plan-body h3{margin:0;font-family:var(--serif);font-weight:500;font-size:18px;letter-spacing:-.01em;color:var(--ink);}
    .plan-body p{margin:0;color:var(--ink-mid);font-size:13px;line-height:1.6;}
    .plan-body .deliverables{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px;}
    .plan-body .deliverables span{font-family:var(--mono);font-size:10.5px;padding:2px 8px;background:var(--paper-warm);border:1px solid var(--line);border-radius:3px;color:var(--ink);letter-spacing:.02em;}
    .plan-week-head{font:700 13px/1.3 var(--sans);margin-bottom:5px;color:var(--ink);}
    .plan-week-focus{display:inline-block;padding:2px 8px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font:700 10px/1.4 var(--sans);margin-left:8px;text-transform:uppercase;letter-spacing:.08em;}
    /* Misc */
    .business-note{margin:10px 0 0;color:var(--ink-mid);font-size:13px;}
    .annex-list,.annex-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;}
    .annex-item{background:var(--paper-warm);border:1px solid var(--line);border-radius:4px;padding:14px;display:flex;flex-direction:column;gap:4px;}
    .annex-name{font-weight:700;font-size:12px;color:var(--ink);}
    .annex-category{font-size:9.5px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--accent);}
    .annex-desc{font-size:11px;color:var(--muted);}
    .empty-state{padding:18px 22px;border:1px dashed var(--line-strong);color:var(--muted);font-size:13px;}
    .target-metric-box{margin-top:10px;padding:10px 14px;background:var(--gain-soft);border-left:2px solid var(--gain);font-size:11.5px;color:var(--gain);}
    .target-metric-label{display:block;font:700 9.5px/1 var(--sans);text-transform:uppercase;letter-spacing:.14em;margin-bottom:4px;}
    .serp-warning{margin-top:10px;padding:10px 14px;background:var(--hot-soft);border-left:2px solid var(--hot);font-size:11.5px;color:var(--warn);}
    .serp-warning-label{display:block;font:700 9.5px/1 var(--sans);text-transform:uppercase;letter-spacing:.14em;margin-bottom:4px;}
    .insight{display:grid;gap:2px;}
    .cards-grid{display:grid;gap:0;}
    /* Closing */
    .closing{margin-top:18px;padding:28px 32px;background:var(--ink);color:rgba(255,255,255,.85);display:grid;grid-template-columns:1fr auto;gap:28px;align-items:center;}
    .closing h3{margin:0 0 6px;font-family:var(--serif);font-weight:400;font-style:italic;font-size:22px;color:#fff;letter-spacing:-.01em;}
    .closing p{margin:0;color:rgba(255,255,255,.75);font-size:13px;line-height:1.6;max-width:50ch;}
    .closing .closing-mark{text-align:right;font-family:var(--serif);color:rgba(255,255,255,.8);font-style:italic;font-size:13px;}
    .closing .closing-mark strong{display:block;color:#fff;font-size:16px;font-weight:500;letter-spacing:-.005em;margin-bottom:4px;}
    /* Print */
    .print-footer{display:none;}
    .no-print{}
    @page{size:A4;margin:0;}
    @media print{
      html,body{background:var(--paper);}
      .doc{padding:0;gap:0;max-width:none;}
      .page{box-shadow:none;border-radius:0;padding:22mm 22mm 24mm;min-height:auto;page-break-after:always;break-after:page;}
      .page.cover{padding:0;}
      .page:last-child{page-break-after:auto;break-after:auto;}
      .runhead{left:22mm;right:22mm;top:12mm;}
      .pagenum{left:22mm;right:22mm;bottom:12mm;}
      *{-webkit-print-color-adjust:exact;print-color-adjust:exact;}
      nav.gsc-nav,.no-print,.filter-bar,.summary-links{display:none!important;}
      .report-toolbar{display:none!important;}
      .print-footer{display:block;position:fixed;left:13mm;right:13mm;bottom:6mm;color:var(--muted);font:600 9px/1.2 var(--sans);text-align:center;}
      .position-bar-fill{width:var(--print-position-width,100%)!important;}
      .page-card,.snippet-card,.appendix-card,.query-card,.priority-item{break-inside:avoid;page-break-inside:avoid;}
      .compact-table tr{break-inside:avoid;page-break-inside:avoid;}
      .kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr));}
    }
    @media(max-width:760px){
      .page{padding:32px 24px 48px;min-height:auto;}
      .cover-mast,.cover-body,.cover-foot{padding-left:24px;padding-right:24px;}
      .kpi-grid,.annex-list,.annex-grid{grid-template-columns:1fr;}
      .page-metrics,.data-grid{grid-template-columns:repeat(2,minmax(0,1fr));}
      .serp-pair{grid-template-columns:1fr;}
      .serp-arrow{display:none;}
      .cluster-grid,.cover-foot{grid-template-columns:1fr 1fr;}
      .variant-row{grid-template-columns:1fr;}
      nav.gsc-nav{padding:10px 24px;}
    }
"""
