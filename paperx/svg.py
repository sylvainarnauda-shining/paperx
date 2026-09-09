"""Aperçu SVG lisible d'une page.

Deux couches nettement séparées :

- la couche « écriture » : les traits de l'écriture générique synthétique ;
- la couche « annotations » : cadre de page, marges, zones inaccessibles,
  emplacements des caractères non pris en charge, en-tête et légende. Ces
  annotations sont écrites avec une police système du visualiseur : ce n'est
  pas de l'écriture, c'est du commentaire d'aperçu.

La sortie est déterministe : mêmes entrées -> mêmes octets (coordonnées
arrondies, aucune date, aucun identifiant aléatoire).
"""

from __future__ import annotations

from . import numeric as num
from .layout import LayoutResult
from .machine import ReachabilityReport
from .strokes import PageTrajectory

_COORD_DIGITS = 3


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _fmt(value: float) -> str:
    rounded = round(float(value), _COORD_DIGITS)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:g}"


def render_page(layout: LayoutResult, traj: PageTrajectory,
                reach: ReachabilityReport | None,
                machine_ready: bool) -> str:
    paper = layout.paper
    W, H = paper.width_mm, paper.height_mm
    m = layout.metrics
    out: list[str] = []
    add = out.append

    add('<?xml version="1.0" encoding="UTF-8"?>')
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmt(W)}mm" '
        f'height="{_fmt(H)}mm" viewBox="0 0 {_fmt(W)} {_fmt(H)}" '
        f'role="img" aria-label="Aperçu page {traj.page_number}">')
    add(f'  <title>paperx — aperçu page {traj.page_number} '
        f'({_esc(traj.paper_ref)})</title>')
    add('  <desc>Écriture générique synthétique, non personnalisée. '
        'Aperçu non exécutable : ce fichier n\'est ni du G-code ni une tâche machine.</desc>')
    add('  <defs>')
    add('    <pattern id="hors-course" width="4" height="4" '
        'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">')
    add('      <rect width="4" height="4" fill="#fdecec"/>')
    add('      <line x1="0" y1="0" x2="0" y2="4" stroke="#d94141" stroke-width="0.7"/>')
    add('    </pattern>')
    add('  </defs>')
    add(f'  <rect x="0" y="0" width="{_fmt(W)}" height="{_fmt(H)}" fill="#ffffff" '
        'stroke="#9aa0a6" stroke-width="0.2"/>')

    # --- Annotations : marges et bande utile ---------------------------------
    add('  <g id="annotations-repere" fill="none" stroke="#c8ccd1" '
        'stroke-width="0.15" stroke-dasharray="1.6 1.6">')
    add(f'    <rect x="{_fmt(paper.margin_left_mm)}" y="{_fmt(paper.margin_top_mm)}" '
        f'width="{_fmt(paper.width_mm - paper.margin_left_mm - paper.margin_right_mm)}" '
        f'height="{_fmt(paper.height_mm - paper.margin_top_mm - paper.margin_bottom_mm)}"/>')
    add(f'    <line x1="{_fmt(m.left_mm)}" y1="{_fmt(paper.margin_top_mm)}" '
        f'x2="{_fmt(m.left_mm)}" y2="{_fmt(H - paper.margin_bottom_mm)}" stroke="#e2e5e9"/>')
    add(f'    <line x1="{_fmt(m.right_limit_mm)}" y1="{_fmt(paper.margin_top_mm)}" '
        f'x2="{_fmt(m.right_limit_mm)}" y2="{_fmt(H - paper.margin_bottom_mm)}" '
        'stroke="#e2e5e9"/>')
    add('  </g>')

    # --- Annotations : zones hors course machine -----------------------------
    if reach is not None and reach.unreachable:
        add('  <g id="annotations-hors-course">')
        for rect in reach.unreachable:
            add(f'    <rect x="{_fmt(rect.x0)}" y="{_fmt(rect.y0)}" '
                f'width="{_fmt(rect.x1 - rect.x0)}" height="{_fmt(rect.y1 - rect.y0)}" '
                'fill="url(#hors-course)" stroke="#d94141" stroke-width="0.25"/>')
            label_y = rect.y0 + min(5.0, (rect.y1 - rect.y0) / 2)
            add(f'    <text x="{_fmt(rect.x0 + 3)}" y="{_fmt(label_y)}" '
                'font-family="sans-serif" font-size="3.2" fill="#a02020">'
                'ZONE HORS COURSE MACHINE — aucun texte n\'est réduit pour y échapper'
                '</text>')
        add('  </g>')

    # --- Couche écriture -----------------------------------------------------
    add(f'  <g id="ecriture-generique-synthetique" fill="none" stroke="#1b1f2a" '
        f'stroke-width="{_fmt(paper.pen_width_mm)}" stroke-linecap="round" '
        'stroke-linejoin="round">')
    for stroke in traj.strokes:
        pts = " ".join(
            f"{_fmt(x)},{_fmt(y)}" for (x, y) in stroke.points
            if num.is_finite(x) and num.is_finite(y)
        )
        if pts:
            add(f'    <polyline points="{pts}"/>')
    add('  </g>')

    # --- Annotations : caractères non pris en charge -------------------------
    if traj.unsupported_marks:
        add('  <g id="annotations-caracteres-non-pris-en-charge">')
        for mark in traj.unsupported_marks:
            x, y = mark.x_mm, mark.baseline_y_mm - mark.height_mm
            add(f'    <rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(mark.width_mm)}" '
                f'height="{_fmt(mark.height_mm)}" fill="none" stroke="#d94141" '
                'stroke-width="0.25" stroke-dasharray="0.8 0.8"/>')
            add(f'    <text x="{_fmt(x)}" y="{_fmt(y - 0.6)}" font-family="sans-serif" '
                f'font-size="1.8" fill="#d94141">{_esc(mark.codepoint)}</text>')
        add('  </g>')

    # --- En-tête et légende --------------------------------------------------
    total_pages = len(layout.pages)
    unsupported = layout.coverage.unsupported_count
    header = (
        f"paperx — APERÇU (non exécutable) · page {traj.page_number}/{total_pages} · "
        f"papier {traj.paper_ref} · écriture {traj.hand_ref}"
    )
    warn = (
        "ÉCRITURE GÉNÉRIQUE SYNTHÉTIQUE — non personnalisée, aucune ressemblance "
        "revendiquée · machine non calibrée : prêt machine = "
        f"{'oui' if machine_ready else 'NON'}"
    )
    legend = (
        f"caractères non pris en charge : {unsupported} (encadrés en rouge, "
        "conservés dans le texte, jamais remplacés)"
    )
    if reach is not None and reach.unreachable:
        legend += (
            f" · hors course : {reach.unreachable_area_mm2:.0f} mm² "
            f"({reach.unreachable_ratio * 100:.1f} % de la page)"
        )
    add('  <g id="annotations-texte" font-family="sans-serif" fill="#5f6673">')
    add(f'    <text x="6" y="6.5" font-size="2.6">{_esc(header)}</text>')
    add(f'    <text x="6" y="10" font-size="2.6" fill="#a02020">{_esc(warn)}</text>')
    add(f'    <text x="6" y="{_fmt(H - 5)}" font-size="2.4">{_esc(legend)}</text>')
    add('  </g>')
    add('</svg>')
    return "\n".join(out) + "\n"
