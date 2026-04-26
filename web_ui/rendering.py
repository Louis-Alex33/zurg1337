from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from urllib.parse import quote, unquote

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
    outputs = "".join(
        f'<li><a href="/files?path={quote(path)}">{html.escape(path)}</a></li>'
        for path in job.outputs
    ) or "<li>Aucune sortie declaree</li>"
    previews = "".join(render_data_preview(path, title=path) for path in job.outputs[:2])
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
      <div class="panel-head"><h2>GSC</h2><span class="badge">exports client</span></div>
      <p class="card-lede">Cette card sert surtout si tu travailles deja avec un client et que tu as ses exports Google Search Console.</p>
      <div class="card-tip">Si tu n'as pas de fichiers GSC, tu peux ignorer cette card pour l'instant.</div>
      <form method="post" action="/run/gsc" class="stack">
        <label>Current CSV
          <input type="text" name="current_csv" value="exports/pages_recent.csv">
        </label>
        <p class="field-help">Export recent des pages depuis GSC. C'est le fichier principal.</p>
        <label>Previous CSV
          <input type="text" name="previous_csv" value="exports/pages_old.csv">
        </label>
        <p class="field-help">Export plus ancien pour comparer les baisses. Tu peux le laisser vide si tu n'en as pas.</p>
        <label>Queries CSV
          <input type="text" name="queries_csv" value="exports/queries.csv">
        </label>
        <p class="field-help">Export des requetes. Il enrichit l'analyse, mais reste optionnel.</p>
        <label>Site label
          <input type="text" name="site_name" value="">
        </label>
        <p class="field-help">Nom lisible du site ou du client, juste pour rendre les sorties plus propres.</p>
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
        <p class="field-help">Le HTML est souvent le plus simple a relire ensuite. Le CSV et le JSON servent surtout a retravailler la sortie.</p>
        <button class="button" type="submit">4. Analyser Des Exports GSC</button>
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


def render_file_page(path: Path, variant: str = "full") -> str:
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
            return render_audit_report_page(path, relative_path=relative_path, file_size=file_size, variant=variant)
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


def file_view_link(path: str, variant: str) -> str:
    return f"/files?path={quote(path)}&variant={quote(variant)}"


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
    rows = "".join(
        "<tr>"
        f"<td><span class='priority-chip'>{html.escape(item.get('priority', '-'))}</span></td>"
        f"<td>{html.escape(item.get('action', '-'))}</td>"
        f"<td>{html.escape(item.get('impact', '-'))}</td>"
        f"<td>{html.escape(item.get('effort', '-'))}</td>"
        "</tr>"
        for item in items
    )
    return (
        "<div class='table-wrap impact-table-wrap'>"
        "<table class='impact-table'>"
        "<thead><tr><th>Priorité</th><th>Action</th><th>Impact</th><th>Effort</th></tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
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
          <p class="audit-hero-surtitle">En bref</p>
          <h2>{html.escape(client_score_label(observed_score))}</h2>
          <p class="audit-hero-copy">{html.escape(build_audit_hero_summary(observed_score, summary, business_signals))}</p>
          <p class="audit-score-explainer">Cette première page aide à repérer rapidement l’état général du site, le point qui ressort en premier et les pages à regarder d’abord.</p>
          {render_cover_brief_grid(observed_score, pages_crawled, summary, top_pages)}
          <p class="audit-urgency-line">{html.escape(urgency)}</p>
        </section>
        <aside class="cover-side-stack">
          {render_cover_signal_block(business_signals)}
          {render_cover_top_pages_block(top_pages)}
          {render_cover_decision_block(actions)}
        </aside>
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
) -> str:
    actions = build_client_actions(summary, business_signals, top_pages)
    method_lines = build_method_lines(summary, pages_crawled)
    client_findings = [client_finding_text(str(item)) for item in critical_findings]
    signal_label = (
        client_signal_label(str(business_signals[0].get("key") or ""), str(business_signals[0].get("signal") or ""))
        if business_signals
        else "Aucune priorité nette"
    )
    return f"""
    <section class="report-page portfolio-page portfolio-cover">
      <div class="audit-report-topbar">
        <div class="audit-report-heading">
          <p class="eyebrow">Extrait portfolio</p>
          <h1>{html.escape(domain)}</h1>
          <p class="lede">{html.escape(subtitle)}</p>
        </div>
      </div>
      <div class="audit-hero-grid portfolio-hero-grid">
        <section class="audit-hero-card audit-hero-primary">
          <p class="audit-hero-surtitle">Ce qui ressort en premier</p>
          <h2>{html.escape(client_score_label(observed_score))}</h2>
          <p class="audit-hero-copy">{html.escape(build_audit_hero_summary(observed_score, summary, business_signals))}</p>
          <div class="portfolio-kpi-grid">
            <article class="report-summary-card"><span class="report-summary-label">Signal principal</span><strong>{html.escape(signal_label)}</strong></article>
            <article class="report-summary-card"><span class="report-summary-label">Pages visitées</span><strong>{pages_crawled}</strong></article>
            <article class="report-summary-card"><span class="report-summary-label">Contenus utiles</span><strong>{summary.get("content_like_pages", 0)}</strong></article>
          </div>
        </section>
        <aside class="audit-hero-card audit-hero-secondary">
          <p class="audit-side-label">Repère</p>
          <div class="audit-hero-stat-block">
            <span class="audit-status-chip">{html.escape(client_score_label(observed_score))}</span>
            <strong>{observed_score}/100</strong>
            <p>{html.escape(client_score_note(observed_score, pages_crawled))}</p>
          </div>
          {render_portfolio_method_strip(method_lines)}
        </aside>
      </div>
    </section>

    <section class="report-page portfolio-page portfolio-details">
      <div class="grid two audit-report-grid">
        <section class="subpanel">
          <h2>Ce que l’analyse fait apparaître</h2>
          {render_string_list(client_findings[:4], empty_label="Aucun point prioritaire net n’a été isolé.")}
        </section>
        <section class="subpanel">
          <h2>Premières actions suggérées</h2>
          {render_string_list(actions, empty_label="Aucune action simple n’a été isolée.")}
        </section>
      </div>
      <section class="subpanel">
        <h2>Pages à revoir en premier</h2>
        {render_portfolio_priority_grid(top_pages, pages_by_url)}
      </section>
    </section>
    """


def render_audit_report_page(path: Path, relative_path: Path, file_size: str, variant: str = "full") -> str:
    active_variant = sanitize_report_variant(variant)
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
    subtitle = client_report_subtitle()
    pages_by_url = {
        str(page.get("url")): page
        for page in (payload.get("pages") or [])
        if isinstance(page, dict) and page.get("url")
    }
    switch_variant = "portfolio" if active_variant == "full" else "full"
    switch_label = "Version portfolio" if active_variant == "full" else "Version complète"
    variant_content = (
        render_full_report_layout(
            domain=domain,
            observed_score=observed_score,
            pages_crawled=_as_int(payload.get("pages_crawled")),
            subtitle=subtitle,
            summary=summary,
            business_signals=business_signals,
            top_pages=top_pages,
            critical_findings=critical_findings,
            confidence_notes=confidence_notes or payload.get("notes") or [],
            overlaps=overlaps,
            dated_content=dated_content,
            pages_by_url=pages_by_url,
            crawl_metadata=payload.get("crawl_metadata") or {},
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
        )
    )
    content = f"""
    <section class="panel file-shell audit-report-shell audit-report-variant-{html.escape(active_variant)}">
      <div class="panel-actions audit-report-actions no-print report-toolbar">
        <button class="button print-button" type="button" onclick="window.print()">Exporter en PDF</button>
        <a class="button secondary" href="{file_view_link(str(relative_path), switch_variant)}">{switch_label}</a>
        <a class="button secondary" href="/">Retour home</a>
      </div>
      {variant_content}
    </section>
    """
    return page_shell(f"Audit - {domain}", content)


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
            "<div class='page-client-brief'>"
            f"<div><span>Pourquoi elle ressort</span><strong>{html.escape(brief['why'])}</strong></div>"
            f"<div><span>Observation</span><strong>{html.escape(brief['observation'])}</strong></div>"
            f"<div><span>Action recommandée</span><strong>{html.escape(brief['recommended_action'])}</strong></div>"
            f"<div><span>Effort estimé</span><strong>{html.escape(brief['effort'])}</strong></div>"
            f"<div><span>Impact potentiel</span><strong>{html.escape(brief['impact'])}</strong></div>"
            f"<div><span>Angle possible</span><strong>{html.escape(brief['rewrite_angle'])}</strong></div>"
            "</div>"
        )
        cards.append(
            "<article class='page-priority-card'>"
            f"<a class='page-url' href='{html.escape(str(item.get('url') or '#'))}' target='_blank' rel='noreferrer'>{html.escape(display_url)}</a>"
            f"<div class='page-priority-meta'><span class='audit-pages-pill'>{html.escape(priority_label)}</span>"
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
