from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from urllib.parse import quote, unquote

from audit_report_design import render_premium_audit_report, sanitize_report_language, signal_label_from_key, translate_finding
from config import (
    AUDIT_MODE_CONFIGS,
    DEFAULT_CRAWL_SOURCE,
    DEFAULT_AUDIT_MODE,
    DEFAULT_DELAY,
    DEFAULT_DISCOVER_PROVIDER,
    DEFAULT_QUALIFY_MODE,
    DEFAULT_UI_AUDIT_MAX_PAGES,
    QUALIFY_MODE_CONFIGS,
)

from . import _root_dir
from ._render_helpers import (
    _as_int,
    audit_json_relative_path,
    build_audit_hero_summary,
    build_audit_summary_signal_note,
    build_client_actions,
    build_client_strengths,
    build_client_takeaways,
    build_editorial_opportunities,
    build_impact_effort_matrix,
    build_method_limit_lines,
    build_page_rework_brief,
    build_method_lines,
    build_primary_rationale,
    build_priority_labels,
    build_priority_roadmap,
    build_reusable_summary_text,
    build_score_explanation,
    build_signal_examples,
    client_finding_text,
    client_reason_label,
    client_report_subtitle,
    client_score_label,
    client_score_note,
    client_scope_summary,
    client_signal_label,
    client_urgency_label,
    compute_audit_summary_metrics,
    confidence_label,
    depth_label,
    format_csv_cell,
    format_url_display,
    human_file_size,
    is_audit_report_json,
    priority_score_label,
    read_csv_table,
    root_has_file,
    sanitize_report_variant,
    should_render_secondary_signal_section,
    signal_helper_text,
    top_priority_summary,
)
from .jobs import JOBS, JOB_LOCK, JobRecord, estimate_job_duration, format_duration, get_job, job_elapsed_seconds
from .styles import PAGE_STYLE


def render_dashboard(flash: str = "") -> str:
    recent_jobs = recent_job_cards()
    raw_preview = render_data_preview("data/domains_raw.csv", title="Dernier domains_raw.csv")
    scored_preview = render_data_preview("data/domains_scored.csv", title="Dernier domains_scored.csv")
    audit_preview = render_data_preview("reports/audits/audit_summary.csv", title="Dernier audit_summary.csv")
    gsc_preview = render_data_preview("reports/gsc_report.csv", title="Dernier gsc_report.csv")
    flash_block = f'<div class="flash-banner">{html.escape(unquote(flash))}</div>' if flash else ""

    content = f"""
    {flash_block}
    <div class="hero">
      <div>
        <p class="eyebrow">Prospect Machine</p>
        <h1>ZURG 1337</h1>
        <p class="lede">
          Outil local pour trouver des sites, les trier, puis sortir un angle d'audit exploitable.
        </p>
        <div class="panel-actions hero-actions">
          <form method="post" action="/reset-pipeline" class="inline-form">
            <button class="ghost-button danger" type="submit">Reset pipeline</button>
          </form>
          <span class="muted">Nettoie raw, scored, audits et rapports GSC generes localement.</span>
        </div>
      </div>
      <div class="hero-panel">
        <div class="hero-stat"><strong>4 modules</strong><span>discover, qualify, audit, gsc</span></div>
        <div class="hero-stat"><strong>Guidage integre</strong><span>les cards indiquent quoi remplir et quoi lire ensuite</span></div>
        <div class="hero-stat"><strong>Jobs locaux</strong><span>aucun service externe requis</span></div>
        <div class="hero-stat"><strong>Fichiers simples</strong><span>CSV et JSON reutilisables partout</span></div>
      </div>
    </div>

    <div class="grid onboarding-grid">
      <section class="panel onboarding-panel">
        <div class="panel-head">
          <h2>Commencer Ici</h2>
          <span class="badge">workflow rapide</span>
        </div>
        <div class="quick-start-grid">
          <article class="quick-start-card">
            <p class="eyebrow">Cas 1</p>
            <h3>Je veux analyser un seul site</h3>
            <ol class="flow compact-flow">
              <li>Va dans la card <strong>Audit</strong>.</li>
              <li>Remplis seulement le champ <strong>Site</strong> avec `example.com`.</li>
              <li>Laisse `Max pages` sur `{DEFAULT_UI_AUDIT_MAX_PAGES}` pour couvrir les petits sites.</li>
              <li>Ouvre ensuite `reports/audits/audit_summary.csv` puis le JSON du domaine.</li>
            </ol>
          </article>
          <article class="quick-start-card">
            <p class="eyebrow">Cas 2</p>
            <h3>Je veux faire de la prospection en lot</h3>
            <ol class="flow compact-flow">
              <li><strong>Discover</strong> pour produire une liste brute.</li>
              <li><strong>Qualify</strong> pour garder les bons candidats.</li>
              <li><strong>Audit</strong> sur les meilleurs scores.</li>
              <li><strong>GSC</strong> seulement si tu as des exports client.</li>
            </ol>
          </article>
          <article class="quick-start-card">
            <p class="eyebrow">A savoir</p>
            <h3>Ce que tu dois lire dans un rapport</h3>
            <ul class="clean-list compact-list">
              <li><strong>Points à corriger d'abord</strong>: les sujets à regarder en priorité.</li>
              <li><strong>Opportunités détectées</strong>: ce qui est le plus simple à valoriser commercialement.</li>
              <li><strong>Pages à revoir en premier</strong>: les exemples concrets à citer dans un message ou une courte vidéo.</li>
            </ul>
          </article>
        </div>
      </section>
    </div>

    <div class="grid two">
      {render_discover_card()}
      {render_qualify_card()}
    </div>

    <div class="grid two">
      {render_audit_card()}
      {render_gsc_card()}
    </div>

    <div class="grid two">
      <section class="panel">
        <div class="panel-head">
          <h2>Jobs recents</h2>
          <div class="panel-tools">
            <form method="post" action="/clear-jobs" class="inline-form">
              <button class="ghost-button" type="submit">Nettoyer</button>
            </form>
            <a class="subtle-link" href="/">Rafraichir</a>
          </div>
        </div>
        {recent_job_cards()}
      </section>
      <section class="panel">
        <div class="panel-head">
          <h2>Pipeline conseille</h2>
        </div>
        <ol class="flow">
          <li>Discover: genere une liste de domaines.</li>
          <li>Qualify: garde les sites qui ressemblent a de bons candidats editoriaux.</li>
          <li>Audit: creuse les meilleurs pour sortir des arguments concrets.</li>
          <li>GSC: ajoute cette brique seulement si tu as des exports client.</li>
        </ol>
      </section>
    </div>

    <div class="grid two">
      {raw_preview}
      {scored_preview}
    </div>

    <div class="grid two">
      {audit_preview}
      {gsc_preview}
    </div>
    """
    return page_shell("Prospect Machine UI", content)


def render_job_page(job_id: str) -> str:
    try:
        job = get_job(job_id)
    except Exception:
        return page_shell("Job introuvable", '<section class="panel"><h2>Job introuvable</h2></section>')

    refresh = '<meta http-equiv="refresh" content="2">' if job.status == "running" else ""
    status_copy = {
        "queued": "En attente de demarrage",
        "running": "En cours d'execution",
        "done": "Termine",
        "cancelled": "Job annule",
        "failed": "Echec du job",
    }.get(job.status, job.status)
    elapsed = format_duration(job_elapsed_seconds(job))
    runtime_hint = estimate_job_duration(job)
    display_outputs = prioritize_job_outputs(job)
    outputs = "".join(
        f'<li><a href="/files?path={quote(path)}">{html.escape(path)}</a></li>'
        for path in display_outputs
    ) or "<li>Aucune sortie declaree</li>"
    previews = render_job_output_previews(job, display_outputs)
    summary = "".join(f"<li>{html.escape(line)}</li>" for line in job.summary_lines) or "<li>Pas de resume.</li>"
    log_block = html.escape(job.log.strip() or "Aucun log capture.")
    error_block = f'<div class="error-box">{html.escape(job.error)}</div>' if job.error else ""
    next_steps = render_job_next_steps(job)
    cancel_action = (
        f"""
        <form method="post" action="/cancel-job" class="inline-form">
          <input type="hidden" name="job_id" value="{html.escape(job.job_id)}">
          <input type="hidden" name="redirect_to" value="/jobs/{html.escape(job.job_id)}">
          <button class="ghost-button danger" type="submit">Annuler le job</button>
        </form>
        """
        if job.status == "running"
        else ""
    )
    running_help = (
        "<p class='field-help running-help'>Le job tourne encore. Cette page se rafraichit automatiquement, les logs se remplissent en direct, et tu peux maintenant l'annuler proprement sans couper le serveur.</p>"
        if job.status == "running"
        else ""
    )
    runtime_block = (
        f"<div><strong>Rythme attendu</strong><span>{html.escape(runtime_hint)}</span></div>"
        if runtime_hint
        else ""
    )

    content = f"""
    {refresh}
    <section class="panel">
      <div class="panel-head">
        <div>
          <p class="eyebrow">Job {html.escape(job.job_id)}</p>
          <h1>{html.escape(job.kind.title())}</h1>
          <p class="lede">{status_copy}</p>
          {running_help}
        </div>
        <div class="status-pill status-{html.escape(job.status)}">{html.escape(job.status)}</div>
      </div>
      <div class="meta-grid">
        <div><strong>Cree le</strong><span>{html.escape(job.created_at)}</span></div>
        <div><strong>Demarre le</strong><span>{html.escape(job.started_at or '-')}</span></div>
        <div><strong>Fini le</strong><span>{html.escape(job.finished_at or '-')}</span></div>
        <div><strong>Duree</strong><span>{html.escape(elapsed)}</span></div>
        {runtime_block}
      </div>
      {error_block}
      <div class="grid two">
        <section class="subpanel">
          <h2>Resume</h2>
          <ul class="clean-list">{summary}</ul>
        </section>
        <section class="subpanel">
          <h2>Sorties</h2>
          <ul class="clean-list">{outputs}</ul>
        </section>
      </div>
      <section class="subpanel">
        <h2>Que faire ensuite</h2>
        {next_steps}
      </section>
      <section class="subpanel">
        <h2>Logs</h2>
        <pre class="log-box">{log_block}</pre>
      </section>
      <div class="panel-actions">
        <a class="button secondary" href="/">Retour dashboard</a>
        {cancel_action}
      </div>
    </section>
    <div class="grid two">{previews}</div>
    """
    return page_shell(f"Job {job.job_id}", content)


def prioritize_job_outputs(job: JobRecord) -> list[str]:
    if job.kind != "gsc":
        return job.outputs
    ordered: list[str] = []
    for suffix in (".html", ".csv", ".json"):
        path = first_output_matching(job.outputs, suffix)
        if path and path not in ordered:
            ordered.append(path)
    ordered.extend(path for path in job.outputs if path not in ordered)
    return ordered


def render_job_output_previews(job: JobRecord, display_outputs: list[str]) -> str:
    if job.kind == "gsc":
        html_report = first_output_matching(display_outputs, ".html")
        csv_report = first_output_matching(display_outputs, ".csv")
        cards: list[str] = []
        if html_report:
            cards.append(render_gsc_report_callout(html_report))
        if csv_report:
            cards.append(render_data_preview(csv_report, title=csv_report))
        return "".join(cards)
    return "".join(render_data_preview(path, title=path) for path in display_outputs[:2])


def render_gsc_report_callout(relative_path: str) -> str:
    exists_note = ""
    if not (_root_dir() / relative_path).exists():
        exists_note = f"<p class='muted'>Le fichier {html.escape(relative_path)} n'existe pas encore.</p>"
    return f"""
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Rapport SEO GSC</h2>
          <p class="section-intro">C’est la sortie principale du job: elle regroupe les opportunités prioritaires, les résultats Google à améliorer, les pages proches d'une percée et les conflits de mots-clés potentiels.</p>
        </div>
        <div class="panel-tools">
          <a class="button" href="/files?path={quote(relative_path)}">Ouvrir le rapport</a>
        </div>
      </div>
      {exists_note}
    </section>
    """


def render_job_next_steps(job: JobRecord) -> str:
    items = build_job_next_steps(job)
    if not items:
        return "<p class='muted'>Aucune suite suggérée pour ce job.</p>"
    body = "".join(f"<li>{item}</li>" for item in items)
    return f"<ul class='clean-list'>{body}</ul>"


def build_job_next_steps(job: JobRecord) -> list[str]:
    if job.status == "running":
        return [
            "Laisse cette page ouverte: elle se met a jour automatiquement avec les logs, la duree et les sorties.",
            "Dès que le job se termine, ouvre le premier fichier de sortie pour verifier rapidement le resultat.",
        ]
    if job.status == "cancelled":
        return [
            "Relis les derniers logs pour voir jusqu'ou le job a pu aller avant l'arret.",
            "Relance ensuite avec des parametres plus legers, par exemple moins de pages ou sans sitemap pour un premier passage.",
        ]
    if job.status == "failed":
        return [
            "Relis le bloc d'erreur et les logs pour voir si le probleme vient d'un chemin de fichier, d'un domaine ou d'un timeout.",
            "Corrige les paramètres du job puis relance-le depuis le dashboard.",
        ]

    if job.kind == "discover":
        output_csv = first_output_matching(job.outputs, ".csv")
        return [
            f"Ouvre {file_anchor(output_csv, 'le CSV de decouverte')} pour verifier si la liste est bien dans la bonne niche."
            if output_csv
            else "Ouvre le CSV de sortie pour verifier si la liste est bien dans la bonne niche.",
            "Enchaine ensuite avec Qualify pour filtrer les sites qui ressemblent vraiment a de bons candidats editoriaux.",
        ]
    if job.kind == "qualify":
        scored_csv = first_output_matching(job.outputs, ".csv")
        scored_json = first_output_matching(job.outputs, ".json")
        items = [
            f"Ouvre {file_anchor(scored_csv, 'le CSV score')} pour repérer les meilleurs candidats."
            if scored_csv
            else "Ouvre le CSV score pour repérer les meilleurs candidats.",
            "Regarde en priorité les champs de fit éditorial, puis lance Audit sur les domaines les plus prometteurs.",
        ]
        if scored_json:
            items.append(f"{file_anchor(scored_json, 'Le JSON détaillé')} est plus pratique si tu veux relire tous les signaux domaine par domaine.")
        return items
    if job.kind == "audit":
        summary_csv = first_output_containing(job.outputs, "audit_summary.csv")
        first_report = first_output_matching(job.outputs, ".json")
        return [
            f"Commence par {file_anchor(summary_csv, 'ouvrir le recap des audits')} pour voir quels domaines ressortent le plus."
            if summary_csv
            else "Commence par ouvrir le recap des audits pour voir quels domaines ressortent le plus.",
            f"Ensuite, ouvre {file_anchor(first_report, 'le rapport complet du domaine')} pour lire les pages a retravailler et les signaux prioritaires."
            if first_report
            else "Ensuite, ouvre le rapport complet du domaine pour lire les pages a retravailler et les signaux prioritaires.",
            "Si le rapport est convaincant, reprends le resume et les pages citees pour preparer une courte video ou un message de prospection.",
        ]
    if job.kind == "gsc":
        html_report = first_output_matching(job.outputs, ".html")
        csv_report = first_output_matching(job.outputs, ".csv")
        return [
            f"Ouvre {file_anchor(html_report, 'le rapport HTML')} pour une lecture plus simple."
            if html_report
            else "Ouvre le rapport HTML pour une lecture plus simple.",
            f"Utilise ensuite {file_anchor(csv_report, 'le CSV')} si tu veux retravailler les priorites ailleurs."
            if csv_report
            else "Utilise ensuite le CSV si tu veux retravailler les priorites ailleurs.",
        ]
    return ["Retourne au dashboard pour lancer l'etape suivante du pipeline."]


def first_output_matching(paths: list[str], suffix: str) -> str | None:
    for path in paths:
        if path.endswith(suffix):
            return path
    return None


def first_output_containing(paths: list[str], fragment: str) -> str | None:
    for path in paths:
        if fragment in path:
            return path
    return None


def file_anchor(path: str | None, label: str) -> str:
    if not path:
        return html.escape(label)
    return f"<a class='subtle-link' href='/files?path={quote(path)}'>{html.escape(label)}</a>"


def render_discover_card() -> str:
    return f"""
    <section class="panel accent-clay">
      <div class="panel-head"><h2>Discover</h2><span class="badge">live ou fichier</span></div>
      <p class="card-lede">Utilise cette card pour construire une premiere liste de domaines. Si tu veux juste analyser un seul site, saute directement a <strong>Audit</strong>.</p>
      <div class="card-tip">Remplis <strong>Niches</strong> si tu cherches de nouveaux sites, ou <strong>Domains file</strong> si tu as deja une liste.</div>
      <form method="post" action="/run/discover" class="stack">
        <label>Niches
          <input type="text" name="niches" value="blog yoga" placeholder="padel,yoga,velo">
        </label>
        <p class="field-help">Exemples: `padel`, `blog yoga`, `comparatif mutuelle`. Separe plusieurs sujets par des virgules.</p>
        <label>Domains file
          <input type="text" name="domains_file" value="" placeholder="data/mes_sites.txt">
        </label>
        <p class="field-help">Fichier texte avec un domaine ou une URL par ligne. Pratique si tu as deja une shortlist.</p>
        <div class="inline-fields">
          <label>Limit
            <input type="number" name="limit" value="30" min="1">
          </label>
          <label>Delay
            <input type="number" step="0.1" name="delay" value="{DEFAULT_DELAY}">
          </label>
        </div>
        <p class="field-help">`Limit` controle combien de domaines tu veux sortir. `Delay` ralentit legerement la collecte pour rester plus propre.</p>
        <div class="inline-fields">
          <label>Provider
            <input type="text" name="provider" value="{DEFAULT_DISCOVER_PROVIDER}">
          </label>
          <label>Query mode
            <input type="text" name="query_mode" value="auto" placeholder="auto | exact | expand">
          </label>
        </div>
        <div class="inline-fields">
          <label>Output
            <input type="text" name="output" value="data/domains_raw.csv">
          </label>
        </div>
        <p class="field-help">La sortie cree en general `data/domains_raw.csv`, qui devient l'entree naturelle de <strong>Qualify</strong>.</p>
        <button class="button" type="submit">1. Generer Une Liste De Domaines</button>
      </form>
    </section>
    """


def render_qualify_card() -> str:
    mode_options = "".join(
        f'<option value="{name}" {"selected" if name == DEFAULT_QUALIFY_MODE else ""}>{name}</option>'
        for name in sorted(QUALIFY_MODE_CONFIGS)
    )
    return f"""
    <section class="panel accent-sage">
      <div class="panel-head"><h2>Qualify</h2><span class="badge">scoring rapide</span></div>
      <p class="card-lede">Cette card trie les domaines et aide a separer les bons candidats editoriaux des profils app, docs ou marketplace.</p>
      <div class="card-tip">Dans la plupart des cas, tu peux garder les valeurs par defaut et lancer le job.</div>
      <form method="post" action="/run/qualify" class="stack">
        <label>Input CSV
          <input type="text" name="input_csv" value="data/domains_raw.csv">
        </label>
        <p class="field-help">Mets ici le fichier cree par <strong>Discover</strong>, en general `data/domains_raw.csv`.</p>
        <div class="inline-fields">
          <label>Output CSV
            <input type="text" name="output" value="data/domains_scored.csv">
          </label>
          <label>Output JSON
            <input type="text" name="json_output" value="data/domains_scored.json">
          </label>
        </div>
        <p class="field-help">Le CSV sert pour la suite du pipeline. Le JSON est plus agreable a relire si tu veux inspecter les details.</p>
        <div class="inline-fields">
          <label>Mode
            <select name="mode">{mode_options}</select>
          </label>
          <label>Delay
            <input type="number" step="0.1" name="delay" value="{DEFAULT_DELAY}">
          </label>
        </div>
        <p class="field-help">`qualify_fast` limite fortement le cout machine. `qualify_full` creuse un peu plus le domaine, notamment via le sitemap.</p>
        <button class="button" type="submit">2. Trier Les Domaines Prometteurs</button>
      </form>
    </section>
    """


def render_audit_card() -> str:
    mode_options = "".join(
        f'<option value="{name}" {"selected" if name == DEFAULT_AUDIT_MODE else ""}>{name}</option>'
        for name in sorted(AUDIT_MODE_CONFIGS)
    )
    return f"""
    <section class="panel accent-ink">
      <div class="panel-head"><h2>Audit</h2><span class="badge">triage ou deep dive</span></div>
      <p class="card-lede">La card la plus utile si tu veux comprendre un site vite. Tu peux l'utiliser directement sur un seul domaine, sans passer par le CSV.</p>
      <div class="card-tip">Pour un test simple, remplis seulement <strong>Site</strong>, garde `audit_light`, laisse `Max pages` a `{DEFAULT_UI_AUDIT_MAX_PAGES}`, puis lance l'audit.</div>
      <form method="post" action="/run/audit" class="stack">
        <label>Input CSV
          <input type="text" name="input_csv" value="data/domains_scored.csv">
        </label>
        <p class="field-help">Utilise ce champ si tu veux auditer plusieurs domaines deja qualifies.</p>
        <label>Site
          <input type="text" name="site" value="" placeholder="example.com ou https://example.com">
        </label>
        <p class="field-help">Si ce champ est rempli, l'audit part directement sur ce domaine et ignore l'Input CSV.</p>
        <div class="inline-fields">
          <label>Mode
            <select name="mode">{mode_options}</select>
          </label>
          <label>Crawl source
            <select name="crawl_source">
              <option value="home" {"selected" if DEFAULT_CRAWL_SOURCE == "home" else ""}>home</option>
              <option value="sitemap" {"selected" if DEFAULT_CRAWL_SOURCE == "sitemap" else ""}>sitemap</option>
              <option value="mixed" {"selected" if DEFAULT_CRAWL_SOURCE == "mixed" else ""}>mixed</option>
            </select>
          </label>
          <label>Top
            <input type="number" name="top" value="3" min="1">
          </label>
          <label>Min score
            <input type="number" name="min_score" value="50" min="0" max="100">
          </label>
        </div>
        <p class="field-help">`audit_light` privilegie un audit rapide et peu gourmand. `audit_full` est reserve aux quelques domaines qui meritent plus de profondeur.</p>
        <div class="inline-fields">
          <label>Max pages
            <input type="number" name="max_pages" value="{DEFAULT_UI_AUDIT_MAX_PAGES}" min="1">
          </label>
          <label>Temps max / site
            <input type="number" name="max_total_seconds_per_domain" value="300" min="1">
          </label>
          <label>Delay
            <input type="number" step="0.1" name="delay" value="0.2">
          </label>
        </div>
        <p class="field-help">`Max pages` est une limite dure. Mets `100` pour couvrir un sitemap d'environ 100 URLs; baisse a `30` seulement pour un triage rapide.</p>
        <label>Output dir
          <input type="text" name="output_dir" value="reports/audits">
        </label>
        <label>Output HTML
          <input type="text" name="html_output" value="" placeholder="reports/audits/audit.html">
        </label>
        <label>Langue du rapport
          <select name="lang">
            <option value="fr" selected>FR</option>
            <option value="en">EN</option>
          </select>
        </label>
        <div class="inline-fields">
          <label class="checkbox-line"><input type="checkbox" name="cache_enabled"> Cache HTTP</label>
          <label class="checkbox-line"><input type="checkbox" name="skip_robots"> Ignorer robots.txt</label>
        </div>
        <p class="field-help">`mixed` part de la home et du sitemap pour mieux couvrir les sites WordPress. Le HTML autonome est pratique pour relire un audit sans passer par l'UI. Le cache aide surtout quand tu itères plusieurs fois sur le même site.</p>
        <p class="field-help">Regarde ensuite `reports/audits/audit_summary.csv`, le JSON du domaine, le HTML si demandé, et `reports/audits/audit_index.sqlite` pour l'historique local.</p>
        <button class="button" type="submit">3. Sortir Un Mini Audit Exploitable</button>
      </form>
    </section>
    """


def render_gsc_card() -> str:
    return """
    <section class="panel accent-gold">
      <div class="panel-head"><h2>Audit GSC</h2><span class="badge">plan d’action</span></div>
      <p class="card-lede">Transforme un export Google Search Console en rapport client: opportunités, pages à surveiller, résultats Google à améliorer et conflits de mots-clés potentiels.</p>
      <div class="card-tip">Tu peux uploader directement le ZIP complet exporté par GSC. Le tool trouvera automatiquement <strong>Pages.csv</strong>, <strong>Requêtes.csv</strong>, <strong>Pays.csv</strong>, <strong>Appareils.csv</strong> et <strong>Graphique.csv</strong> quand ils sont présents.</div>
      <form method="post" action="/run/gsc" class="stack" enctype="multipart/form-data">
        <label>1. Export GSC récent
          <input type="text" name="current_csv" value="" placeholder="exports/performance-search.zip ou exports/pages_recent.csv">
        </label>
        <label>Uploader l’export GSC récent
          <input type="file" name="current_upload" accept=".zip,.csv,.tsv,.txt,text/csv,application/zip">
        </label>
        <p class="field-help">Obligatoire. Le plus simple: upload le ZIP complet de Search Console. Sinon, mets seulement le CSV Pages.</p>
        <label>2. Export Pages précédent
          <input type="text" name="previous_csv" value="" placeholder="exports/pages_old.csv">
        </label>
        <label>Uploader l’export Pages précédent
          <input type="file" name="previous_upload" accept=".zip,.csv,.tsv,.txt,text/csv,application/zip">
        </label>
        <p class="field-help">Optionnel. Mets un export Pages ancien, ou un ancien ZIP GSC, seulement si tu veux comparer deux périodes.</p>
        <label>3. Export Requêtes
          <input type="text" name="queries_csv" value="" placeholder="exports/queries.csv">
        </label>
        <label>Uploader l’export Requêtes
          <input type="file" name="queries_upload" accept=".csv,.tsv,.txt,text/csv">
        </label>
        <p class="field-help">Optionnel. Si tu as uploadé un ZIP complet en 1, tu peux laisser ce champ vide: les requêtes seront lues automatiquement.</p>
        <div class="inline-fields">
          <label>Graphique CSV
            <input type="text" name="graphique_csv" value="" placeholder="exports/Graphique.csv">
          </label>
          <label>Pays CSV
            <input type="text" name="pays_csv" value="" placeholder="exports/Pays.csv">
          </label>
          <label>Appareils CSV
            <input type="text" name="appareils_csv" value="" placeholder="exports/Appareils.csv">
          </label>
        </div>
        <div class="inline-fields">
          <label>Uploader Graphique
            <input type="file" name="graphique_upload" accept=".csv,.tsv,.txt,text/csv">
          </label>
          <label>Uploader Pays
            <input type="file" name="pays_upload" accept=".csv,.tsv,.txt,text/csv">
          </label>
          <label>Uploader Appareils
            <input type="file" name="appareils_upload" accept=".csv,.tsv,.txt,text/csv">
          </label>
        </div>
        <p class="field-help">Optionnel. Ces fichiers alimentent le graphique 90 jours et la section Origine du trafic. Un ZIP complet suffit souvent.</p>
        <label>Site label
          <input type="text" name="site_name" value="">
        </label>
        <p class="field-help">Nom lisible du site ou du client, juste pour rendre les sorties plus propres.</p>
        <label>Mode rapport
          <select name="mode">
            <option value="executive" selected>Executive</option>
            <option value="full">Full</option>
          </select>
        </label>
        <p class="field-help">Executive garde le PDF court et sort les tableaux complets en annexes CSV. Full inclut les annexes dans le HTML.</p>
        <label>Langue du rapport
          <select name="lang">
            <option value="fr" selected>FR</option>
            <option value="en">EN</option>
          </select>
        </label>
        <p class="field-help">Le job génère aussi la version jumelle pour basculer FR/EN depuis le rapport.</p>
        <label>Niche stopwords
          <input type="text" name="niche_stopwords" value="" placeholder="padel,tennis,mutuelle">
        </label>
        <p class="field-help">Ajoute ici les mots de niche que tu veux ignorer dans la détection de chevauchement page / requête.</p>
        <label class="checkbox-line"><input type="checkbox" name="auto_niche_stopwords"> Auto niche stopwords</label>
        <p class="field-help">Ajoute automatiquement les mots présents dans au moins 60% des URLs analysées.</p>
        <div class="inline-fields">
          <label>Output CSV
            <input type="text" name="output_csv" value="reports/gsc_report.csv">
          </label>
          <label>Output JSON
            <input type="text" name="output_json" value="reports/gsc_report.json">
          </label>
        </div>
        <label>Output HTML
          <input type="text" name="output_html" value="reports/gsc_report.html">
        </label>
        <p class="field-help">Ouvre d’abord le HTML: il est maintenant pensé comme un rapport client. Le CSV et le JSON restent là pour retraiter les données.</p>
        <button class="button" type="submit">4. Créer Le Rapport SEO GSC</button>
      </form>
    </section>
    """


def recent_job_cards() -> str:
    with JOB_LOCK:
        jobs = sorted(JOBS.values(), key=lambda item: item.created_at, reverse=True)[:8]
    if not jobs:
        return "<p class='muted'>Aucun job lance pour l'instant. Commence par la card Audit si tu veux juste tester un domaine.</p>"
    cards = []
    for job in jobs:
        elapsed = format_duration(job_elapsed_seconds(job))
        runtime_hint = estimate_job_duration(job)
        cancel_action = (
            f"""
            <form method="post" action="/cancel-job" class="inline-form">
              <input type="hidden" name="job_id" value="{html.escape(job.job_id)}">
              <input type="hidden" name="redirect_to" value="/">
              <button class="ghost-button danger" type="submit">Annuler</button>
            </form>
            """
            if job.status == "running"
            else ""
        )
        cards.append(
            f"""
            <div class="job-card">
              <div class="job-top">
                <a class="job-main-link" href="/jobs/{job.job_id}">
                  <strong>{html.escape(job.kind.title())}</strong>
                </a>
                <span class="status-pill status-{html.escape(job.status)}">{html.escape(job.status)}</span>
              </div>
              <a class="job-main-link" href="/jobs/{job.job_id}">
                <p>{html.escape(job.job_id)} · {html.escape(job.created_at)}</p>
                <p class="job-meta">Duree: {html.escape(elapsed)}</p>
                <p class="job-meta">{html.escape(runtime_hint or 'Temps variable selon le reseau et les fichiers fournis.')}</p>
              </a>
              <div class="job-actions">
                {cancel_action}
                <form method="post" action="/delete-job" class="inline-form">
                  <input type="hidden" name="job_id" value="{html.escape(job.job_id)}">
                  <input type="hidden" name="redirect_to" value="/">
                  <button class="ghost-button job-delete" type="submit">Supprimer</button>
                </form>
              </div>
            </div>
            """
        )
    return "".join(cards)


def render_data_preview(relative_path: str, title: str) -> str:
    path = _root_dir() / relative_path
    if not path.exists():
        return (
            f'<section class="panel"><div class="panel-head"><h2>{html.escape(title)}</h2></div>'
            f'<p class="muted">Aucun fichier trouve pour {html.escape(relative_path)}.</p></section>'
        )
    link = f"/files?path={quote(relative_path)}"
    actions = ""
    if relative_path in {"data/domains_raw.csv", "data/domains_scored.csv"}:
        cascade_input = '<input type="hidden" name="cascade" value="on">' if relative_path == "data/domains_scored.csv" else ""
        actions = (
            '<form method="post" action="/delete-file" class="inline-form">'
            f'<input type="hidden" name="path" value="{html.escape(relative_path)}">'
            '<input type="hidden" name="redirect_to" value="/">'
            f"{cascade_input}"
            '<button class="ghost-button danger" type="submit">Supprimer</button>'
            "</form>"
        )
    try:
        if path.suffix == ".csv":
            table = render_csv_preview(path)
        elif path.suffix == ".json":
            payload = html.escape(json.dumps(json.loads(path.read_text("utf-8")), ensure_ascii=False, indent=2)[:3000])
            table = f"<pre class='log-box'>{payload}</pre>"
        else:
            payload = html.escape(path.read_text("utf-8", errors="ignore")[:3000])
            table = f"<pre class='log-box'>{payload}</pre>"
    except Exception as exc:  # noqa: BLE001
        table = f"<p class='muted'>Preview indisponible: {html.escape(str(exc))}</p>"
    return (
        f'<section class="panel"><div class="panel-head"><h2>{html.escape(title)}</h2>'
        f'<div class="panel-tools"><a class="subtle-link" href="{link}">Ouvrir</a>{actions}</div></div>{table}</section>'
    )


def render_csv_preview(path: Path, max_rows: int = 8) -> str:
    if path.name == "audit_summary.csv":
        return render_audit_summary_preview(path, max_rows=max_rows)

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = []
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append(row)
    if not fieldnames:
        return "<p class='muted'>CSV vide.</p>"
    headers = "".join(f"<th>{html.escape(name)}</th>" for name in fieldnames)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape((row.get(name) or '')[:140])}</td>" for name in fieldnames)
        body_rows.append(f"<tr>{cells}</tr>")
    body = "".join(body_rows) or f"<tr><td colspan='{len(fieldnames)}'>Aucune ligne.</td></tr>"
    return f"<div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{body}</tbody></table></div>"


def render_file_page(path: Path, variant: str = "full", lang: str = "fr") -> str:
    root_dir = _root_dir()
    relative_path = path.relative_to(root_dir)
    file_size = human_file_size(path.stat().st_size)
    delete_action = ""
    if str(relative_path) in {"data/domains_raw.csv", "data/domains_scored.csv"}:
        cascade_input = '<input type="hidden" name="cascade" value="on">' if str(relative_path) == "data/domains_scored.csv" else ""
        delete_action = (
            '<form method="post" action="/delete-file" class="inline-form">'
            f'<input type="hidden" name="path" value="{html.escape(str(relative_path))}">'
            '<input type="hidden" name="redirect_to" value="/">'
            f"{cascade_input}"
            '<button class="ghost-button danger" type="submit">Supprimer ce fichier</button>'
            "</form>"
        )
    if path.suffix == ".csv":
        if str(relative_path) == "reports/audits/audit_summary.csv":
            return render_audit_summary_page(path, file_size=file_size)
        stats, table = render_full_csv_table(path)
        content = f"""
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">CSV Viewer</p>
              <h1>{html.escape(str(relative_path))}</h1>
              <p class="lede">Vue tabulaire complete, plus agreable pour relire rapidement les exports de prospection.</p>
            </div>
            <div class="panel-actions">
              {delete_action}
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
          <div class="meta-grid file-meta">
            <div><strong>Type</strong><span>CSV</span></div>
            <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
            <div><strong>Lignes</strong><span>{stats['rows']}</span></div>
            <div><strong>Colonnes</strong><span>{stats['columns']}</span></div>
          </div>
          <section class="subpanel">
            <h2>Apercu complet</h2>
            {table}
          </section>
        </section>
        """
        return page_shell(f"CSV - {relative_path}", content)

    if path.suffix == ".json":
        if is_audit_report_json(relative_path):
            return render_audit_report_page(path, relative_path=relative_path, file_size=file_size, variant=variant, lang=lang)
        pretty_json = html.escape(json.dumps(json.loads(path.read_text("utf-8")), ensure_ascii=False, indent=2))
        content = f"""
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">JSON Viewer</p>
              <h1>{html.escape(str(relative_path))}</h1>
              <p class="lede">Lecture rapide du JSON genere par le pipeline.</p>
            </div>
            <div class="panel-actions">
              {delete_action}
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
          <div class="meta-grid file-meta">
            <div><strong>Type</strong><span>JSON</span></div>
            <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
          </div>
          <pre class="log-box">{pretty_json}</pre>
        </section>
        """
        return page_shell(f"JSON - {relative_path}", content)

    if path.suffix in {".sqlite", ".db"}:
        content = f"""
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">SQLite Index</p>
              <h1>{html.escape(str(relative_path))}</h1>
              <p class="lede">Base locale d'historique des audits. Elle est prévue pour les scripts, exports et comparaisons futures.</p>
            </div>
            <div class="panel-actions">
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
          <div class="meta-grid file-meta">
            <div><strong>Type</strong><span>SQLite</span></div>
            <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
          </div>
        </section>
        """
        return page_shell(f"SQLite - {relative_path}", content)

    payload = html.escape(path.read_text("utf-8", errors="ignore"))
    content = f"""
    <section class="panel file-shell">
      <div class="panel-head">
        <div>
          <p class="eyebrow">File Viewer</p>
          <h1>{html.escape(str(relative_path))}</h1>
          <p class="lede">Apercu texte du fichier.</p>
        </div>
        <div class="panel-actions">
          {delete_action}
          <a class="button secondary" href="/">Retour home</a>
        </div>
      </div>
      <div class="meta-grid file-meta">
        <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
      </div>
      <pre class="log-box">{payload}</pre>
    </section>
    """
    return page_shell(f"File - {relative_path}", content)


def render_audit_html_as_toggleable_report(path: Path, variant: str = "full", lang: str = "fr") -> str | None:
    audit_json = find_audit_json_for_html(path)
    if not audit_json:
        return None
    root_dir = _root_dir()
    relative_path = audit_json.relative_to(root_dir)
    return render_audit_report_page(
        audit_json,
        relative_path=relative_path,
        file_size=human_file_size(audit_json.stat().st_size),
        variant=variant,
        lang=lang,
    )


def find_audit_json_for_html(path: Path) -> Path | None:
    root_dir = _root_dir()
    try:
        relative_path = path.relative_to(root_dir)
    except ValueError:
        return None
    if path.suffix.lower() != ".html" or not str(relative_path).startswith("reports/audits/"):
        return None

    candidates = [path.with_suffix(".json")]
    history_dir = path.with_suffix("")
    if history_dir.is_dir():
        candidates.extend(sorted(history_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True))
    if path.parent.name != path.stem:
        sibling_history_dir = path.parent / path.stem
        if sibling_history_dir.is_dir():
            candidates.extend(sorted(sibling_history_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True))

    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and looks_like_audit_report_json(candidate):
            return candidate
    return None


def looks_like_audit_report_json(path: Path) -> bool:
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and bool(payload.get("domain")) and (
        "pages_crawled" in payload or "observed_health_score" in payload or "summary" in payload
    )


def file_view_link(path: str, variant: str, lang: str = "fr") -> str:
    return f"/files?path={quote(path)}&variant={quote(variant)}&lang={quote(sanitize_report_language(lang))}"


def render_report_intro_cards(
    summary: dict[str, object],
    pages_crawled: int,
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> str:
    signal_label = (
        client_signal_label(str(business_signals[0].get("key") or ""), str(business_signals[0].get("signal") or ""))
        if business_signals
        else "Aucune priorité nette"
    )
    return (
        "<div class='report-intro-grid'>"
        f"<article class='report-summary-card'><span class='report-summary-label'>Ce qui a été analysé</span><strong>{html.escape(client_scope_summary(summary, pages_crawled))}</strong></article>"
        f"<article class='report-summary-card'><span class='report-summary-label'>Ce qui ressort d'abord</span><strong>{html.escape(signal_label)}</strong></article>"
        f"<article class='report-summary-card'><span class='report-summary-label'>Pages à revoir d'abord</span><strong>{html.escape(top_priority_summary(top_pages))}</strong></article>"
        "</div>"
    )


def render_client_decision_block(actions: list[str]) -> str:
    return (
        "<section class='subpanel report-action-panel'>"
        "<h2>Ce que ce rapport permet de décider</h2>"
        f"{render_string_list(actions, empty_label='Aucune action simple n’a été isolée.')}"
        "</section>"
    )


def render_score_donut(observed_score: int, pages_crawled: int, lang: str = "fr") -> str:
    active_lang = sanitize_report_language(lang)
    score = max(0, min(100, observed_score))
    tone = "score-donut-low"
    label = "Needs work" if active_lang == "en" else "À renforcer"
    if score >= 75:
        tone = "score-donut-high"
        label = "Solid" if active_lang == "en" else "Solide"
    elif score >= 60:
        tone = "score-donut-mid"
        label = "To watch" if active_lang == "en" else "À surveiller"
    note = (
        f"Read based on {pages_crawled} public page(s) visited. The {score}/100 indicator helps prioritize the site without claiming to summarize its full quality."
        if active_lang == "en"
        else client_score_note(score, pages_crawled)
    )
    return (
        f"<div class='score-donut-widget {tone}'>"
        f"<div class='score-donut' style='--score-pct: {score}%;' aria-label='Score observé {score} sur 100'>"
        "<div class='score-donut-inner'>"
        f"<strong>{score}</strong>"
        "<span>/100</span>"
        "</div>"
        "</div>"
        "<div class='score-donut-copy'>"
        f"<span class='report-status-label'>{html.escape(label)}</span>"
        f"<p>{html.escape(note)}</p>"
        "</div>"
        "</div>"
    )


def priority_tone_from_score(value: object) -> str:
    score = _as_int(value)
    if score >= 7:
        return "high"
    if score >= 4:
        return "moderate"
    return "healthy"


def priority_tone_from_label(label: str) -> str:
    normalized = label.strip().lower()
    if "haute" in normalized or "élev" in normalized or "eleve" in normalized:
        return "high"
    if "moy" in normalized or "mod" in normalized:
        return "moderate"
    return "healthy"


def render_priority_badge(label: str, tone: str = "moderate") -> str:
    safe_tone = tone if tone in {"high", "moderate", "healthy"} else "moderate"
    return f"<span class='priority-chip priority-badge priority-{safe_tone}'>{html.escape(label)}</span>"


def signal_distribution(summary: dict[str, object]) -> list[dict[str, object]]:
    groups = [
        (
            "Indexation",
            "Ce qui peut empêcher une page d’être prise en compte",
            "signal-indexing",
            (
                "noindex_pages",
                "canonical_to_other_url_pages",
                "canonical_cross_domain_pages",
                "robots_blocked_pages",
                "pages_with_errors",
            ),
        ),
        (
            "Contenu",
            "Ce qui demande une reprise éditoriale visible",
            "signal-content",
            (
                "thin_content_pages",
                "missing_titles",
                "missing_meta_descriptions",
                "missing_h1",
                "duplicate_title_groups",
                "duplicate_meta_description_groups",
                "dated_content_signals",
            ),
        ),
        (
            "Structure",
            "Ce qui limite la circulation entre les pages",
            "signal-structure",
            (
                "weak_internal_linking_pages",
                "probable_orphan_pages",
                "deep_pages_detected",
                "possible_content_overlap_pairs",
            ),
        ),
    ]
    return [
        {"label": label, "note": note, "tone": tone, "value": sum(_as_int(summary.get(key)) for key in keys)}
        for label, note, tone, keys in groups
    ]


def render_signal_distribution_chart(summary: dict[str, object]) -> str:
    groups = signal_distribution(summary)
    total = sum(int(item["value"]) for item in groups)
    colors = {
        "signal-indexing": "#2563eb",
        "signal-content": "#f97316",
        "signal-structure": "#0f766e",
        "signal-clear": "#16a34a",
    }
    if total <= 0:
        chart_style = "background: conic-gradient(#16a34a 0 100%);"
        legend_items = [
            "<li><span class='chart-dot signal-clear'></span><span>Aucun signal majeur</span><strong>0</strong></li>"
        ]
        total_label = "0 signal prioritaire"
    else:
        cursor = 0.0
        segments: list[str] = []
        for item in groups:
            value = int(item["value"])
            if value <= 0:
                continue
            start = cursor
            cursor += value / total * 100
            color = colors[str(item["tone"])]
            segments.append(f"{color} {start:.2f}% {cursor:.2f}%")
        chart_style = f"background: conic-gradient({', '.join(segments)});"
        legend_items = [
            (
                f"<li><span class='chart-dot {html.escape(str(item['tone']))}'></span>"
                f"<span>{html.escape(str(item['label']))}<small>{html.escape(str(item['note']))}</small></span>"
                f"<strong>{int(item['value'])}</strong></li>"
            )
            for item in groups
        ]
        total_label = f"{total} signaux classés"
    return (
        "<section class='subpanel report-chart-card'>"
        "<div class='report-chart-head'>"
        "<div>"
        "<h2>Répartition des signaux</h2>"
        f"<p class='section-intro'>{html.escape(total_label)} par famille, pour distinguer technique, contenu et structure.</p>"
        "</div>"
        "</div>"
        "<div class='signal-chart-layout'>"
        f"<div class='signal-pie' style='{html.escape(chart_style)}'><div><strong>{total}</strong><span>signaux</span></div></div>"
        f"<ul class='chart-legend'>{''.join(legend_items)}</ul>"
        "</div>"
        "</section>"
    )


def render_client_strengths_block(strengths: list[str]) -> str:
    return (
        "<section class='subpanel positive-panel'>"
        "<h2>Ce qui fonctionne déjà</h2>"
        f"{render_string_list(strengths, empty_label='Aucun point positif net n’a été isolé automatiquement.')}"
        "</section>"
    )


def render_score_explanation_block(lines: list[str]) -> str:
    return (
        "<section class='subpanel score-explanation-panel'>"
        "<h2>Lecture du score</h2>"
        f"{render_string_list(lines, empty_label='Le score demande une relecture manuelle.')}"
        "</section>"
    )


def render_roadmap_block(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class='muted'>Aucun plan d’action n’a pu être généré.</p>"
    cards = "".join(
        "<article class='roadmap-card'>"
        f"<span>{html.escape(item.get('period', '-'))}</span>"
        f"<strong>{html.escape(item.get('focus', '-'))}</strong>"
        f"<p>{html.escape(item.get('actions', '-'))}</p>"
        "</article>"
        for item in items
    )
    return f"<div class='roadmap-grid'>{cards}</div>"


def render_impact_effort_matrix(items: list[dict[str, str]]) -> str:
    if not items:
        return "<p class='muted'>Aucune action prioritaire n’a été isolée.</p>"
    quadrants = [
        ("quick-wins", "Quick Wins", "Impact fort / effort faible", "À lancer en premier"),
        ("projects", "Projets structurants", "Impact fort / effort élevé", "À cadrer"),
        ("fill-ins", "Optimisations simples", "Impact modéré / effort faible", "À traiter si le temps le permet"),
        ("later", "À planifier", "Impact modéré / effort élevé", "À garder en backlog"),
    ]
    grouped: dict[str, list[dict[str, str]]] = {key: [] for key, *_ in quadrants}
    for item in items:
        impact = str(item.get("impact") or "").lower()
        effort = str(item.get("effort") or "").lower()
        high_impact = "élev" in impact or "eleve" in impact or "fort" in impact
        low_effort = "faible" in effort
        if high_impact and low_effort:
            bucket = "quick-wins"
        elif high_impact:
            bucket = "projects"
        elif low_effort:
            bucket = "fill-ins"
        else:
            bucket = "later"
        grouped[bucket].append(item)

    cards = []
    for key, title, axis, note in quadrants:
        entries = grouped[key]
        if entries:
            body = "".join(
                "<article class='impact-action-card'>"
                f"{render_priority_badge(str(entry.get('priority') or 'Priorité'), priority_tone_from_label(str(entry.get('priority') or '')))}"
                f"<strong>{html.escape(entry.get('action', '-'))}</strong>"
                "<div class='impact-action-meta'>"
                f"<span>Impact : {html.escape(entry.get('impact', '-'))}</span>"
                f"<span>Effort : {html.escape(entry.get('effort', '-'))}</span>"
                "</div>"
                "</article>"
                for entry in entries
            )
        else:
            body = "<p class='muted'>Aucune action classée ici.</p>"
        cards.append(
            f"<section class='impact-quadrant impact-{key}' aria-label='{html.escape(title)}'>"
            "<div class='impact-quadrant-head'>"
            f"<span>{html.escape(note)}</span>"
            f"<h3>{html.escape(title)}</h3>"
            f"<p>{html.escape(axis)}</p>"
            "</div>"
            f"<div class='impact-quadrant-body'>{body}</div>"
            "</section>"
        )
    return (
        "<div class='impact-matrix-shell' role='group' aria-label='Matrice impact effort'>"
        f"<div class='impact-quadrant-grid'>{''.join(cards)}</div>"
        "</div>"
    )


def render_editorial_opportunities_block(lines: list[str]) -> str:
    return (
        "<section class='subpanel editorial-opportunities-panel'>"
        "<h2>Opportunités éditoriales</h2>"
        f"{render_string_list(lines, empty_label='Aucune opportunité éditoriale nette n’a été isolée.')}"
        "</section>"
    )


def render_method_limits_block(lines: list[str]) -> str:
    return (
        "<section class='subpanel method-limits-panel'>"
        "<h2>Méthode et limites de l’analyse</h2>"
        f"{render_string_list(lines, empty_label='Aucune limite spécifique n’a été fournie.')}"
        "</section>"
    )


def render_cover_brief_grid(
    observed_score: int,
    pages_crawled: int,
    summary: dict[str, object],
    top_pages: list[dict[str, object]],
) -> str:
    pages_to_review = min(len(top_pages), 3)
    cards = [
        ("Base observée", client_score_label(observed_score).replace("Base observée : ", "")),
        ("Pages analysées", f"{pages_crawled} pages analysées"),
        ("Contenus utiles", f"{_as_int(summary.get('content_like_pages'))} contenus utiles"),
        ("Pages à revoir d’abord", f"{pages_to_review} pages à revoir d’abord"),
    ]
    body = "".join(
        "<article class='report-summary-card cover-brief-card'>"
        f"<span class='report-summary-label'>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        "</article>"
        for label, value in cards
    )
    return f"<div class='cover-brief-grid'>{body}</div>"


def render_cover_signal_block(business_signals: list[dict[str, object]]) -> str:
    if business_signals:
        signal_label = client_signal_label(
            str(business_signals[0].get("key") or ""),
            str(business_signals[0].get("signal") or ""),
        )
    else:
        signal_label = "Aucun signal prioritaire net n’a été isolé à ce stade."
    return (
        "<section class='subpanel cover-side-card'>"
        "<h2>Signal principal</h2>"
        f"<p class='cover-strong-line'>{html.escape(signal_label)}</p>"
        "</section>"
    )


def render_cover_top_pages_block(top_pages: list[dict[str, object]]) -> str:
    if not top_pages:
        body = "<p class='muted'>Aucune page prioritaire n’a été isolée.</p>"
    else:
        items = "".join(
            "<li>"
            f"<a class='cover-url-link' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(format_url_display(str(item.get('url') or ''), max_length=78))}</a>"
            "</li>"
            for item in top_pages[:3]
        )
        body = f"<ul class='clean-list cover-url-list'>{items}</ul>"
    return (
        "<section class='subpanel cover-side-card'>"
        "<h2>Premières pages à regarder</h2>"
        f"{body}"
        "</section>"
    )


def render_cover_decision_block(actions: list[str]) -> str:
    lines = actions[:3]
    return (
        "<section class='subpanel cover-side-card'>"
        "<h2>Ce que ce rapport aide à décider</h2>"
        f"{render_string_list(lines, empty_label='Aucune décision simple n’a été isolée.')}"
        "</section>"
    )


def render_portfolio_method_strip(lines: list[str]) -> str:
    items = "".join(f"<li>{html.escape(line)}</li>" for line in lines)
    return (
        "<section class='subpanel portfolio-method-strip'>"
        "<h2>Méthode de lecture</h2>"
        f"<ul class='clean-list'>{items}</ul>"
        "</section>"
    )


def render_portfolio_priority_grid(top_pages: list[dict[str, object]], pages_by_url: dict[str, dict[str, object]]) -> str:
    if not top_pages:
        return "<p class='muted'>Aucune page prioritaire n’a été isolée pour cette version courte.</p>"
    return render_top_pages_to_rework(top_pages[:3], pages_by_url)


def render_technical_appendix(
    summary: dict[str, object],
    crawl_metadata: dict[str, object],
    pages_by_url: dict[str, dict[str, object]],
) -> str:
    return f"""
    <section class="report-page report-page-appendix">
      <section class="subpanel">
        <h2>Annexe technique</h2>
        <p class="section-intro">Cette partie garde les données utiles pour relire le crawl sans alourdir la synthèse client.</p>
        <div class="grid two audit-report-grid appendix-grid">
          <section class="subpanel appendix-inner-panel">
            <h2>Chiffres clés</h2>
            {render_summary_key_figures(summary)}
          </section>
          <section class="subpanel appendix-inner-panel">
            <h2>Paramètres du crawl</h2>
            {render_crawl_metadata(crawl_metadata)}
          </section>
        </div>
        <section class="subpanel appendix-inner-panel">
          <h2>URLs observées</h2>
          {render_technical_page_table(list(pages_by_url.values()))}
        </section>
      </section>
    </section>
    """


def render_crawl_metadata(crawl_metadata: dict[str, object]) -> str:
    if not crawl_metadata:
        return "<p class='muted'>Métadonnées de crawl non disponibles.</p>"
    preferred_keys = [
        ("crawl_source", "Source"),
        ("seed_urls_count", "URLs de départ"),
        ("sitemap_urls_found", "URLs sitemap trouvées"),
        ("pages_collected", "Pages collectées"),
        ("urls_attempted", "Requêtes tentées"),
        ("urls_skipped", "URLs ignorées"),
        ("queued_urls_remaining", "URLs restantes"),
        ("stop_reason", "Raison d’arrêt"),
        ("max_pages", "Limite de pages"),
        ("max_total_seconds_per_domain", "Limite de temps"),
        ("robots_txt_available", "Robots.txt détecté"),
        ("robots_txt_status", "Statut robots.txt"),
    ]
    rows = []
    for key, label in preferred_keys:
        if key not in crawl_metadata:
            continue
        value = crawl_metadata.get(key)
        rows.append(
            "<div>"
            f"<dt>{html.escape(label)}</dt>"
            f"<dd>{html.escape(str(value))}</dd>"
            "</div>"
        )
    if not rows:
        return "<p class='muted'>Métadonnées de crawl non disponibles.</p>"
    return f"<dl class='audit-fact-list technical-fact-list'>{''.join(rows)}</dl>"


def render_technical_page_table(pages: list[dict[str, object]]) -> str:
    if not pages:
        return "<p class='muted'>Aucune URL détaillée disponible.</p>"
    rows = []
    for page in pages[:80]:
        issues = " | ".join(str(item) for item in (page.get("issues") or [])[:3]) or "-"
        rows.append(
            "<tr>"
            f"<td><a class='subtle-link' href='{html.escape(str(page.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(format_url_display(str(page.get('url') or ''), max_length=72))}</a></td>"
            f"<td>{html.escape(str(page.get('page_type') or '-'))}</td>"
            f"<td>{html.escape(str(page.get('page_health_score') or '-'))}/100</td>"
            f"<td>{html.escape(str(page.get('word_count') or 0))}</td>"
            f"<td>{html.escape(issues)}</td>"
            "</tr>"
        )
    more_note = ""
    if len(pages) > 80:
        more_note = f"<p class='field-help'>{len(pages) - 80} URL(s) supplémentaires restent disponibles dans le JSON source.</p>"
    return (
        "<div class='table-wrap technical-page-table-wrap'>"
        "<table class='technical-page-table'>"
        "<thead><tr><th>URL</th><th>Type</th><th>Score</th><th>Mots</th><th>Points relevés</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        "</div>"
        f"{more_note}"
    )


def render_full_report_layout(
    domain: str,
    observed_score: int,
    pages_crawled: int,
    subtitle: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    critical_findings: list[str],
    confidence_notes: list[str],
    overlaps: list[dict[str, object]],
    dated_content: list[dict[str, object]],
    pages_by_url: dict[str, dict[str, object]],
    crawl_metadata: dict[str, object],
) -> str:
    takeaways = build_client_takeaways(summary, business_signals, top_pages)
    actions = build_client_actions(summary, business_signals, top_pages)
    rationale = build_primary_rationale(summary, business_signals)
    strengths = build_client_strengths(summary, observed_score)
    score_lines = build_score_explanation(observed_score, summary)
    roadmap = build_priority_roadmap(summary, business_signals, top_pages)
    impact_effort = build_impact_effort_matrix(summary, business_signals, top_pages)
    editorial_opportunities = build_editorial_opportunities(summary, top_pages)
    method_limits = build_method_limit_lines(summary, pages_crawled, crawl_metadata, confidence_notes)
    urgency = client_urgency_label(observed_score, summary, business_signals)
    client_findings = [client_finding_text(str(item)) for item in critical_findings]
    secondary_sections = ""
    if should_render_secondary_signal_section(overlaps, dated_content, business_signals):
        secondary_sections = f"""
        <section class="report-page report-page-secondary">
          <section class="subpanel">
            <h2>Repères complémentaires</h2>
            <p class="section-intro">Cette page complète la synthèse avec les chiffres utiles et les signaux qui demandent une vérification plus fine.</p>
            {render_summary_key_figures(summary)}
          </section>
          <div class="grid two audit-report-grid">
            <section class="subpanel">
              <h2>Signaux secondaires</h2>
              {render_business_signals(business_signals, {"possible_content_overlap": overlaps, "dated_content_signals": dated_content, "top_pages_to_rework": top_pages, "duplicate_titles": {}, "duplicate_meta_descriptions": {}, "probable_orphan_pages": []})}
            </section>
            <section class="subpanel">
              <h2>Éléments à vérifier</h2>
              {render_dated_signals(dated_content) if dated_content else render_overlap_pairs(overlaps)}
            </section>
          </div>
        </section>
        """
    return f"""
    <section class="report-page report-page-cover">
      <div class="audit-report-topbar">
        <div class="audit-report-heading">
          <p class="eyebrow">Audit SEO</p>
          <h1>{html.escape(domain)}</h1>
          <p class="lede">{html.escape(subtitle)}</p>
        </div>
      </div>
      <div class="cover-layout-grid">
        <section class="audit-hero-card audit-hero-primary cover-main-card">
          <div class="audit-cover-main">
            <div>
              <p class="audit-hero-surtitle">Synthèse client</p>
              <h2>{html.escape(client_score_label(observed_score))}</h2>
              <p class="audit-hero-copy">{html.escape(build_audit_hero_summary(observed_score, summary, business_signals))}</p>
              <p class="audit-score-explainer">Cette première page aide à repérer rapidement l’état général du site, le point qui ressort en premier et les pages à regarder d’abord.</p>
              <p class="audit-urgency-line">{html.escape(urgency)}</p>
            </div>
            {render_score_donut(observed_score, pages_crawled)}
          </div>
        </section>
        <aside class="cover-side-stack">
          {render_cover_signal_block(business_signals)}
          {render_cover_top_pages_block(top_pages)}
          {render_cover_decision_block(actions)}
        </aside>
      </div>
      <div class="report-dashboard-row">
        {render_cover_brief_grid(observed_score, pages_crawled, summary, top_pages)}
        {render_signal_distribution_chart(summary)}
      </div>
    </section>

    <section class="report-page report-page-reading">
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Lecture rapide</h2>
          {render_string_list(takeaways, empty_label="Pas assez d’éléments pour sortir une lecture claire.")}
        </section>
        {render_client_strengths_block(strengths)}
      </div>
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Pourquoi ce point compte</h2>
          {render_string_list(rationale, empty_label="Aucun point secondaire notable à signaler.")}
        </section>
        {render_score_explanation_block(score_lines)}
      </div>
      {render_client_decision_block(actions)}
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Points à corriger d’abord</h2>
          {render_string_list(client_findings, empty_label="Aucun point prioritaire n’a été remonté.")}
        </section>
        <section class="subpanel">
          <h2>À garder en tête</h2>
          {render_string_list(confidence_notes, empty_label="Aucune précision complémentaire.")}
        </section>
      </div>
    </section>

    <section class="report-page report-page-plan">
      <section class="subpanel">
        <h2>Plan d’action 30 / 60 / 90 jours</h2>
        <p class="section-intro">Cette priorisation transforme le crawl en séquence de travail lisible côté client.</p>
        {render_roadmap_block(roadmap)}
      </section>
      <section class="subpanel">
        <h2>Matrice impact / effort</h2>
        {render_impact_effort_matrix(impact_effort)}
      </section>
    </section>

    <section class="report-page report-page-priority">
      <section class="subpanel">
        <h2>Pages à revoir en priorité</h2>
        <p class="section-intro">Ces pages donnent les exemples les plus concrets pour décider d’une reprise ciblée.</p>
        {render_top_pages_to_rework(top_pages, pages_by_url)}
      </section>
    </section>

    {secondary_sections}
    <section class="report-page report-page-opportunities">
      {render_editorial_opportunities_block(editorial_opportunities)}
      {render_method_limits_block(method_limits)}
    </section>
    {render_technical_appendix(summary, crawl_metadata, pages_by_url)}
    """


def render_portfolio_report_layout(
    domain: str,
    observed_score: int,
    pages_crawled: int,
    subtitle: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    critical_findings: list[str],
    pages_by_url: dict[str, dict[str, object]],
    lang: str = "fr",
) -> str:
    active_lang = sanitize_report_language(lang)
    is_en = active_lang == "en"
    actions = build_client_actions(summary, business_signals, top_pages)
    method_lines = build_method_lines(summary, pages_crawled)
    client_findings = [client_finding_text(str(item)) for item in critical_findings]
    if business_signals:
        signal_label = (
            signal_label_from_key(str(business_signals[0].get("key") or ""), active_lang)
            or str(business_signals[0].get("signal") or "")
            if is_en
            else client_signal_label(str(business_signals[0].get("key") or ""), str(business_signals[0].get("signal") or ""))
        )
    else:
        signal_label = "No clear priority" if is_en else "Aucune priorité nette"
    if is_en:
        actions = localize_portfolio_lines(actions)
        method_lines = [
            f"Read based on {pages_crawled} public pages visited.",
            f"{_as_int(summary.get('content_like_pages'))} content page(s) were kept to define priorities."
            if _as_int(summary.get("content_like_pages"))
            else "The report is based on pages that were actually reachable during the analysis.",
            "The goal is to prioritize useful rework, not produce an exhaustive site audit.",
        ]
        client_findings = [translate_finding(item, active_lang) for item in client_findings]
    score_label = (
        "Observed base: rather healthy"
        if observed_score >= 75 and is_en
        else "Observed base: healthy, with several useful improvements"
        if observed_score >= 60 and is_en
        else "Observed base: first signals to correct"
        if is_en
        else client_score_label(observed_score)
    )
    hero_summary = (
        portfolio_hero_summary(observed_score, summary, business_signals, active_lang)
        if is_en
        else build_audit_hero_summary(observed_score, summary, business_signals)
    )
    labels = {
        "eyebrow": "Portfolio extract" if is_en else "Extrait portfolio",
        "first_signal": "First signal" if is_en else "Ce qui ressort en premier",
        "main_signal": "Main signal" if is_en else "Signal principal",
        "pages_visited": "Pages visited" if is_en else "Pages visitées",
        "useful_content": "Useful content" if is_en else "Contenus utiles",
        "marker": "Marker" if is_en else "Repère",
        "analysis": "What the analysis reveals" if is_en else "Ce que l’analyse fait apparaître",
        "actions": "First suggested actions" if is_en else "Premières actions suggérées",
        "priority_pages": "Pages to review first" if is_en else "Pages à revoir en premier",
        "empty_findings": "No clear priority point was isolated." if is_en else "Aucun point prioritaire net n’a été isolé.",
        "empty_actions": "No simple action was isolated." if is_en else "Aucune action simple n’a été isolée.",
    }
    return f"""
    <section class="report-page portfolio-page portfolio-cover">
      <div class="audit-report-topbar">
        <div class="audit-report-heading">
          <p class="eyebrow">{html.escape(labels["eyebrow"])}</p>
          <h1>{html.escape(domain)}</h1>
          <p class="lede">{html.escape(subtitle)}</p>
        </div>
      </div>
      <div class="audit-hero-grid portfolio-hero-grid">
        <section class="audit-hero-card audit-hero-primary">
          <p class="audit-hero-surtitle">{html.escape(labels["first_signal"])}</p>
          <h2>{html.escape(score_label)}</h2>
          <p class="audit-hero-copy">{html.escape(hero_summary)}</p>
          <div class="portfolio-kpi-grid">
            <article class="report-summary-card"><span class="report-summary-label">{html.escape(labels["main_signal"])}</span><strong>{html.escape(signal_label)}</strong></article>
            <article class="report-summary-card"><span class="report-summary-label">{html.escape(labels["pages_visited"])}</span><strong>{pages_crawled}</strong></article>
            <article class="report-summary-card"><span class="report-summary-label">{html.escape(labels["useful_content"])}</span><strong>{summary.get("content_like_pages", 0)}</strong></article>
          </div>
        </section>
        <aside class="audit-hero-card audit-hero-secondary">
          <p class="audit-side-label">{html.escape(labels["marker"])}</p>
          {render_score_donut(observed_score, pages_crawled, lang=active_lang)}
          {render_portfolio_method_strip(method_lines)}
        </aside>
      </div>
    </section>

    <section class="report-page portfolio-page portfolio-details">
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>{html.escape(labels["analysis"])}</h2>
          {render_string_list(client_findings[:4], empty_label=labels["empty_findings"])}
        </section>
        <section class="subpanel">
          <h2>{html.escape(labels["actions"])}</h2>
          {render_string_list(actions, empty_label=labels["empty_actions"])}
        </section>
      </div>
      <section class="subpanel">
        <h2>{html.escape(labels["priority_pages"])}</h2>
        {render_portfolio_priority_grid(top_pages, pages_by_url)}
      </section>
    </section>
    """


def render_audit_report_page(path: Path, relative_path: Path, file_size: str, variant: str = "full", lang: str = "fr") -> str:
    active_variant = sanitize_report_variant(variant)
    active_lang = sanitize_report_language(lang)
    payload = json.loads(path.read_text("utf-8"))
    domain = str(payload.get("domain") or relative_path.stem)
    summary = payload.get("summary") or {}
    business_signals = payload.get("business_priority_signals") or []
    top_pages = payload.get("top_pages_to_rework") or []
    overlaps = payload.get("possible_content_overlap") or []
    confidence_notes = payload.get("confidence_notes") or []
    critical_findings = payload.get("critical_findings") or []
    dated_content = payload.get("dated_content_signals") or []
    observed_score = _as_int(payload.get("observed_health_score"))
    subtitle = (
        "Quick content-site analysis to identify the pages to rework first."
        if active_lang == "en"
        else client_report_subtitle()
    )
    pages_by_url = {
        str(page.get("url")): page
        for page in (payload.get("pages") or [])
        if isinstance(page, dict) and page.get("url")
    }
    switch_variant = "portfolio" if active_variant == "full" else "full"
    switch_label = (
        "Portfolio version"
        if active_lang == "en" and active_variant == "full"
        else "Full version"
        if active_lang == "en"
        else "Version portfolio"
        if active_variant == "full"
        else "Version complète"
    )
    language_switch = render_report_language_switch(str(relative_path), active_variant, active_lang)
    print_label = "Export PDF" if active_lang == "en" else "Exporter en PDF"
    home_label = "Back home" if active_lang == "en" else "Retour home"
    variant_content = (
        render_premium_audit_report(
            payload,
            standalone=False,
            lang=active_lang,
        )
        if active_variant == "full"
        else render_portfolio_report_layout(
            domain=domain,
            observed_score=observed_score,
            pages_crawled=_as_int(payload.get("pages_crawled")),
            subtitle=subtitle,
            summary=summary,
            business_signals=business_signals,
            top_pages=top_pages,
            critical_findings=critical_findings,
            pages_by_url=pages_by_url,
            lang=active_lang,
        )
    )
    content = f"""
    <section class="panel file-shell audit-report-shell audit-report-variant-{html.escape(active_variant)}">
      <div class="panel-actions audit-report-actions no-print report-toolbar">
        <button class="button print-button" type="button" onclick="printClientReport(false)">{html.escape(print_label)}</button>
        {language_switch}
        <a class="button secondary" href="{file_view_link(str(relative_path), switch_variant, active_lang)}">{switch_label}</a>
        <a class="button secondary" href="/">{html.escape(home_label)}</a>
      </div>
      {variant_content}
    </section>
    """
    return page_shell(f"Audit - {domain}", content)


def render_report_language_switch(path: str, variant: str, active_lang: str) -> str:
    items = []
    for lang, label in (("fr", "FR"), ("en", "EN")):
        active_class = " is-active" if lang == active_lang else ""
        aria_current = ' aria-current="true"' if lang == active_lang else ""
        items.append(
            f'<a class="button secondary language-toggle{active_class}" href="{file_view_link(path, variant, lang)}"{aria_current}>{label}</a>'
        )
    return "<span class='language-toggle-group'>" + "".join(items) + "</span>"


def portfolio_hero_summary(
    score: int,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    lang: str,
) -> str:
    if sanitize_report_language(lang) != "en":
        return build_audit_hero_summary(score, summary, business_signals)
    if score >= 75:
        intro = "The site gives a rather reassuring first impression."
    elif score >= 60:
        intro = "The site has a credible base, with several improvements that are easy to illustrate."
    else:
        intro = "The site shows several visible points that can support an outreach angle."
    if business_signals:
        top_signal = signal_label_from_key(str(business_signals[0].get("key") or ""), lang)
        if top_signal:
            intro += f" The clearest topic today is {top_signal.lower()}."
    content_pages = _as_int(summary.get("content_like_pages"))
    if content_pages:
        intro += f" The analysis is based on {content_pages} content pieces identified on the site."
    return intro


def localize_portfolio_lines(items: list[str]) -> list[str]:
    replacements = [
        ("Vérifier les pages de contenu marquées noindex avant toute reprise éditoriale.", "Check noindex content pages before any editorial rework."),
        ("Contrôler les canonicals qui pointent vers une autre URL.", "Check canonicals that point to another URL."),
        ("Vérifier que les dates visibles correspondent bien à l’état réel des contenus importants.", "Check that visible dates still match the real state of important content."),
        ("Retravailler d’abord les pages les plus légères avant d’ouvrir de nouveaux sujets.", "Rework the thinnest pages before opening new topics."),
        ("Clarifier l’angle des contenus qui semblent répondre au même besoin.", "Clarify the angle of content that seems to answer the same need."),
        ("Renforcer le maillage interne depuis les pages déjà visibles ou déjà bien positionnées.", "Strengthen internal linking from pages that are already visible or well positioned."),
        ("Prioriser 2 à 3 pages à reprendre en premier pour montrer rapidement un avant / après.", "Prioritize 2 to 3 pages to rework first so a before/after can be shown quickly."),
        ("Vérifier manuellement les pages les plus visibles avant de décider d’un plan de reprise.", "Manually check the most visible pages before deciding on a rework plan."),
    ]
    localized: list[str] = []
    for item in items:
        translated = item
        for source, target in replacements:
            translated = translated.replace(source, target)
        localized.append(translated)
    return localized


def render_string_list(items: list[str], empty_label: str) -> str:
    if not items:
        return f"<p class='muted'>{html.escape(empty_label)}</p>"
    body = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<ul class='clean-list'>{body}</ul>"


def render_business_signals(items: list[dict[str, object]], payload: dict[str, object]) -> str:
    if not items:
        return "<p class='muted'>Aucune opportunité prioritaire n'a été repérée.</p>"
    cards: list[str] = []
    for item in items[:8]:
        severity = str(item.get("severity") or "")
        signal_key = str(item.get("key") or "")
        signal_label = client_signal_label(signal_key, str(item.get("signal") or "Signal"))
        tone = "signal-medium"
        severity_label = "À surveiller"
        if severity == "HIGH":
            tone = "signal-high"
            severity_label = "Priorité forte"
        examples_html = render_signal_examples(signal_key, payload)
        cards.append(
            "<div class='signal-row-card'>"
            "<div class='signal-row'>"
            f"<span class='pill signal-pill {tone}'>{html.escape(severity_label)}</span>"
            f"<strong>{html.escape(signal_label)}</strong>"
            f"<span>{html.escape(str(item.get('count') or 0))}</span>"
            "</div>"
            f"<p class='signal-help'>{html.escape(signal_helper_text(signal_key))}</p>"
            f"{examples_html}"
            "</div>"
        )
    return "<div class='signal-list'>" + "".join(cards) + "</div>"


def render_signal_examples(signal_key: str, payload: dict[str, object]) -> str:
    examples = build_signal_examples(signal_key, payload)
    if not examples:
        return ""
    body = "".join(f"<li>{html.escape(example)}</li>" for example in examples[:5])
    return (
        "<details class='signal-details'>"
        "<summary>Voir des exemples concrets</summary>"
        f"<ul class='clean-list signal-example-list'>{body}</ul>"
        "</details>"
    )


def render_top_pages_to_rework(items: list[dict[str, object]], pages_by_url: dict[str, dict[str, object]]) -> str:
    if not items:
        return "<p class='muted'>Aucune page prioritaire n'a été remontée.</p>"
    cards: list[str] = []
    for item in items[:6]:
        reasons = item.get("reasons") or []
        page_details = pages_by_url.get(str(item.get("url") or ""), {})
        confidence = confidence_label(str(item.get("confidence") or ""))
        priority_label = priority_score_label(item.get("priority_score"))
        priority_tone = priority_tone_from_score(item.get("priority_score"))
        page_depth_label = depth_label(item.get("depth"))
        display_url = format_url_display(str(item.get("url") or ""), max_length=72)
        health_score = str(item.get("page_health_score") or page_details.get("page_health_score") or "-")
        page_type = str(item.get("page_type") or page_details.get("page_type") or "-")
        brief = build_page_rework_brief(item, page_details)
        chips = "".join(
            f"<span class='priority-chip'>{html.escape(client_reason_label(str(reason)))}</span>"
            for reason in reasons
        )
        client_brief = (
            "<div class='page-context-note'>"
            f"<span class='page-card-label'>Pourquoi elle ressort</span><strong>{html.escape(brief['why'])}</strong>"
            "</div>"
            "<div class='page-client-brief'>"
            "<section class='page-brief-column'>"
            f"<div class='page-brief-block'><span class='page-card-label'>Observation</span><strong>{html.escape(brief['observation'])}</strong></div>"
            f"<div class='page-brief-block is-action'><span class='page-card-label'>Action recommandée</span><strong>{html.escape(brief['recommended_action'])}</strong></div>"
            "</section>"
            "<section class='page-brief-column'>"
            f"<div class='page-brief-block is-impact'><span class='page-card-label'>Impact potentiel</span><strong>{html.escape(brief['impact'])}</strong></div>"
            f"<div class='page-brief-block'><span class='page-card-label'>Effort estimé</span><strong>{html.escape(brief['effort'])}</strong></div>"
            f"<div class='page-brief-block is-angle'><span class='page-card-label'>Angle possible</span><strong>{html.escape(brief['rewrite_angle'])}</strong></div>"
            "</section>"
            "</div>"
        )
        cards.append(
            f"<article class='page-priority-card priority-card-{html.escape(priority_tone)}'>"
            f"<a class='page-url' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(display_url)}</a>"
            f"<div class='page-priority-meta'>{render_priority_badge(priority_label, priority_tone)}"
            f"<span class='audit-pages-pill'>score page {html.escape(health_score)}/100</span>"
            f"<span class='audit-pages-pill'>{html.escape(page_type)}</span>"
            f"<span class='audit-pages-pill'>{html.escape(str(item.get('word_count') or 0))} mots</span>"
            f"<span class='audit-pages-pill'>{html.escape(page_depth_label)}</span>"
            f"<span class='audit-pages-pill'>{html.escape(confidence)}</span></div>"
            f"<div class='audit-compact-body'>{chips or '<span class=\"muted\">Aucune raison spécifiée.</span>'}</div>"
            f"{client_brief}"
            f"{render_page_issue_details(page_details)}"
            "</article>"
        )
    return "<div class='page-priority-list'>" + "".join(cards) + "</div>"


def render_commercial_read(
    domain: str,
    summary: dict[str, object],
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
) -> str:
    from ._render_helpers import build_commercial_read_lines

    return render_string_list(
        build_commercial_read_lines(domain, summary, business_signals, top_pages),
        empty_label="Pas assez d'elements pour sortir une lecture commerciale.",
    )


def render_reusable_summary(
    domain: str,
    business_signals: list[dict[str, object]],
    top_pages: list[dict[str, object]],
    summary: dict[str, object],
) -> str:
    pitch = build_reusable_summary_text(domain, business_signals, top_pages, summary)
    return (
        f"<div class='copy-block'><p>{html.escape(pitch)}</p></div>"
        "<p class='field-help'>Ce texte reste volontairement prudent. Tu peux le reprendre dans un message, une courte vidéo ou un autre outil. Le JSON téléchargé reste la version structurée la plus exploitable.</p>"
    )


def render_audit_report_next_steps(relative_path: Path, top_pages: list[dict[str, object]]) -> str:
    download_link = f"/download?path={quote(str(relative_path))}"
    steps = [
        "Ouvre 2 ou 3 URLs prioritaires dans le navigateur pour verifier rapidement si les constats se confirment visuellement.",
        f"<a class='subtle-link' href='{download_link}'>Télécharge le JSON</a> si tu veux le réutiliser dans un autre outil, un script ou une automatisation.",
    ]
    if top_pages:
        first_target = str(top_pages[0].get("url") or "")
        if first_target:
            steps.append(
                f"Commence par {external_anchor(first_target, 'ouvrir la page la plus prioritaire')} pour préparer un exemple concret."
            )
    body = "".join(f"<li>{step}</li>" for step in steps)
    return f"<ul class='clean-list'>{body}</ul>"


def external_anchor(url: str, label: str) -> str:
    return f"<a class='subtle-link' href='{html.escape(url)}' target='_blank' rel='noreferrer'>{html.escape(label)}</a>"


def render_page_issue_details(page: dict[str, object]) -> str:
    issues = [str(issue) for issue in (page.get("issues") or [])[:6]]
    dated_refs = [str(ref) for ref in (page.get("dated_references") or [])[:4]]
    if not issues and not dated_refs:
        return ""
    items = "".join(f"<li>{html.escape(issue)}</li>" for issue in issues)
    items += "".join(f"<li>{html.escape(ref)}</li>" for ref in dated_refs)
    return (
        "<details class='signal-details'>"
        "<summary>Voir les éléments relevés sur cette page</summary>"
        f"<ul class='clean-list signal-example-list'>{items}</ul>"
        "</details>"
    )


def render_overlap_pairs(items: list[dict[str, object]]) -> str:
    if not items:
        return "<p class='muted'>Aucun sujet trop proche n'a été repéré parmi les pages analysées.</p>"
    rows = [
        "<article class='pair-card'>"
        f"<strong>{html.escape(str(item.get('similarity') or 0))}% de similarité</strong>"
        f"<p>{html.escape(str(item.get('title_1') or '-'))}</p>"
        f"<p>{html.escape(str(item.get('title_2') or '-'))}</p>"
        "</article>"
        for item in items[:6]
    ]
    return "<div class='pair-list'>" + "".join(rows) + "</div>"


def render_dated_signals(items: list[dict[str, object]]) -> str:
    if not items:
        return "<p class='muted'>Aucune date à actualiser n'a été repérée sur les pages analysées.</p>"
    rows = []
    for item in items[:6]:
        references = item.get("references") or []
        refs = "".join(f"<span class='priority-chip'>{html.escape(str(ref))}</span>" for ref in references[:3])
        display_url = format_url_display(str(item.get("url") or ""), max_length=72)
        rows.append(
            "<article class='pair-card'>"
            f"<a class='page-url' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(display_url)}</a>"
            f"<div class='audit-compact-body'>{refs}</div>"
            "</article>"
        )
    return "<div class='pair-list'>" + "".join(rows) + "</div>"


def render_summary_key_figures(summary: dict[str, object]) -> str:
    if not summary:
        return "<p class='muted'>Aucun résumé chiffré disponible.</p>"
    preferred_keys = [
        ("pages_ok", "Pages saines"),
        ("pages_with_errors", "Pages en erreur"),
        ("missing_meta_descriptions", "Descriptions Google manquantes"),
        ("missing_h1", "Titres principaux manquants"),
        ("avg_page_health_score", "Score moyen page"),
        ("noindex_pages", "Pages noindex"),
        ("canonical_to_other_url_pages", "Canonicals à vérifier"),
        ("weak_internal_linking_pages", "Pages peu reliées"),
        ("possible_content_overlap_pairs", "Sujets trop proches"),
        ("dated_content_signals", "Dates visibles à vérifier"),
    ]
    return "<div class='audit-metric-grid'>" + "".join(
        render_metric_card(label, str(summary.get(key, 0)), "")
        for key, label in preferred_keys
    ) + "</div>"


def render_audit_summary_preview(path: Path, max_rows: int = 8) -> str:
    _, rows = read_csv_table(path)
    if not rows:
        return "<p class='muted'>CSV vide.</p>"
    return f"<div class='audit-summary-preview'>{''.join(render_audit_summary_compact_card(row) for row in rows[:max_rows])}</div>"


def render_audit_summary_page(path: Path, file_size: str) -> str:
    _, rows = read_csv_table(path)
    if not rows:
        empty = """
        <section class="panel file-shell">
          <div class="panel-head">
            <div>
              <p class="eyebrow">Vue d'ensemble des audits</p>
              <h1>reports/audits/audit_summary.csv</h1>
              <p class="lede">Aucun audit disponible pour l'instant.</p>
            </div>
            <div class="panel-actions">
              <a class="button secondary" href="/">Retour home</a>
            </div>
          </div>
        </section>
        """
        return page_shell("Audit Summary", empty)

    metrics = compute_audit_summary_metrics(rows)
    metric_cards = "".join(
        [
            render_metric_card("Sites analysés", str(metrics["domains"]), "audits présents dans ce récapitulatif"),
            render_metric_card("Note moyenne", str(metrics["avg_score"]), "état moyen observé"),
            render_metric_card("Sites à surveiller", str(metrics["watch_domains"]), "sites avec une note observée < 70"),
            render_metric_card("Dates à actualiser", str(metrics["dated_signals"]), "occurrences repérées"),
        ]
    )
    content = f"""
    <section class="panel file-shell audit-shell">
      <div class="panel-head">
        <div>
          <p class="eyebrow">Vue d'ensemble des audits</p>
          <h1>reports/audits/audit_summary.csv</h1>
          <p class="lede">Vue simple pour repérer rapidement les sites qui montrent le plus d'opportunités d'amélioration.</p>
        </div>
        <div class="panel-actions">
          <a class="button secondary" href="/">Retour home</a>
        </div>
      </div>
      <div class="meta-grid file-meta">
        <div><strong>Type</strong><span>Tableau récapitulatif</span></div>
        <div><strong>Taille</strong><span>{html.escape(file_size)}</span></div>
        <div><strong>Lignes</strong><span>{metrics["domains"]}</span></div>
        <div><strong>Colonnes</strong><span>{metrics["columns"]}</span></div>
      </div>
      <section class="subpanel">
        <h2>Vue rapide</h2>
        <div class="audit-metric-grid">{metric_cards}</div>
      </section>
      <section class="subpanel">
        <h2>Sites analysés</h2>
        {render_audit_summary_table(rows)}
      </section>
    </section>
    """
    return page_shell("Audit Summary", content)


def render_metric_card(title: str, value: str, note: str) -> str:
    return (
        "<div class='audit-metric-card'>"
        f"<strong>{html.escape(value)}</strong>"
        f"<span>{html.escape(title)}</span>"
        f"<p>{html.escape(note)}</p>"
        "</div>"
    )


def render_audit_summary_compact_card(row: dict[str, str]) -> str:
    domain = row.get("domain", "").strip() or "n/a"
    score = _as_int(row.get("observed_health_score"))
    priorities = render_priority_chips_html(build_priority_labels(row, limit=2))
    json_path = audit_json_relative_path(domain)
    link = f"<a class='subtle-link' href='/files?path={quote(json_path)}'>Voir rapport complet</a>" if root_has_file(json_path) else ""
    return (
        "<article class='audit-compact-card'>"
        f"<div class='audit-compact-head'><span class='pill domain-pill'>{html.escape(domain)}</span>{render_health_score_badge(score)}</div>"
        f"<div class='audit-compact-body'>{priorities or '<span class=\"muted\">Peu de signaux prioritaires dans ce summary.</span>'}</div>"
        f"<div class='audit-compact-foot'>{link}</div>"
        "</article>"
    )


def render_audit_summary_table(rows: list[dict[str, str]]) -> str:
    body_rows: list[str] = []
    for row in rows:
        domain = row.get("domain", "").strip()
        pages = _as_int(row.get("pages_crawled"))
        score = _as_int(row.get("observed_health_score"))
        priorities = build_priority_labels(row, limit=4)
        json_path = audit_json_relative_path(domain)
        json_link = (
            f"<a class='subtle-link' href='/files?path={quote(json_path)}'>Voir rapport complet</a>"
            if root_has_file(json_path)
            else "<span class='muted'>JSON non trouve</span>"
        )
        body_rows.append(
            "<tr>"
            f"<td><div class='audit-domain-cell'><span class='pill domain-pill'>{html.escape(domain)}</span>{json_link}</div></td>"
            f"<td>{render_health_score_badge(score)}</td>"
            f"<td><span class='audit-pages-pill'>{pages} pages</span></td>"
            f"<td>{render_priority_chips_html(priorities)}</td>"
            f"<td>{html.escape(build_audit_summary_signal_note(row))}</td>"
            "</tr>"
        )
    return (
        "<div class='table-wrap file-table audit-summary-table'>"
        "<table>"
        "<thead><tr>"
        "<th>Domaine</th>"
        "<th>État observé</th>"
        "<th>Pages analysées</th>"
        "<th>Opportunités prioritaires</th>"
        "<th>Lecture rapide</th>"
        "</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table>"
        "</div>"
    )


def render_health_score_badge(score: int) -> str:
    tone = "health-bad"
    label = "à renforcer"
    if score >= 75:
        tone = "health-good"
        label = "plutôt solide"
    elif score >= 60:
        tone = "health-watch"
        label = "a surveiller"
    return f"<span class='pill health-pill {tone}'>{score}/100 · {label}</span>"


def render_priority_chips_html(labels: list[str]) -> str:
    if not labels:
        return "<span class='muted'>Rien de saillant ici.</span>"
    return "".join(f"<span class='priority-chip'>{html.escape(label)}</span>" for label in labels)


def render_full_csv_table(path: Path) -> tuple[dict[str, int], str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = [row for row in reader]
    if not fieldnames:
        return {"rows": 0, "columns": 0}, "<p class='muted'>CSV vide.</p>"
    headers = "".join(f"<th><span class='col-name'>{html.escape(name)}</span></th>" for name in fieldnames)
    body_rows = []
    for row in rows:
        cells = []
        for name in fieldnames:
            value = (row.get(name) or "").strip()
            cell_class = "cell-empty" if not value else ""
            cells.append(f"<td class='{cell_class}'>{format_csv_cell(name, value)}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    body = "".join(body_rows) or f"<tr><td colspan='{len(fieldnames)}'>Aucune ligne.</td></tr>"
    table = (
        "<div class='table-filter-row'>"
        "<input class='table-filter-input' type='search' placeholder='Filtrer ce tableau' "
        "oninput='filterCsvTable(this)'>"
        "</div>"
        "<div class='table-wrap file-table'>"
        "<table>"
        f"<thead><tr>{headers}</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</div>"
    )
    return {"rows": len(rows), "columns": len(fieldnames)}, table


def page_shell(title: str, content: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
{PAGE_STYLE}
  </style>
</head>
<body>
  <main class="page">
    {content}
  </main>
  <script>
    function printClientReport(includeAnnexe) {{
      if (typeof window.printClientReportFromReport === 'function') {{
        window.printClientReportFromReport(includeAnnexe);
        return;
      }}
      const report = document.querySelector('.premium-report') || document.querySelector('.audit-report-shell') || document.body;
      const printWindow = window.open('', '_blank', 'noopener,noreferrer');
      if (!printWindow) {{
        window.print();
        return;
      }}
      const styles = Array.from(document.querySelectorAll('style')).map((node) => node.outerHTML).join('\\n');
      printWindow.document.open();
      printWindow.document.write('<!doctype html><html><head><meta charset="utf-8"><title>Pré-audit SEO public</title>' + styles + '</head><body>' + report.outerHTML + '</body></html>');
      printWindow.document.close();
      printWindow.focus();
      setTimeout(() => printWindow.print(), 300);
    }}

    function filterCsvTable(input) {{
      const wrapper = input.closest('.table-filter-row').nextElementSibling;
      if (!wrapper) return;
      const query = input.value.toLowerCase();
      wrapper.querySelectorAll('tbody tr').forEach((row) => {{
        row.style.display = row.innerText.toLowerCase().includes(query) ? '' : 'none';
      }});
    }}
  </script>
</body>
</html>"""
