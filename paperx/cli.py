"""Banc d'essai en ligne de commande.

    python3 -m paperx demo --text samples/texte_demo_fr.txt --out out

Produit, dans `--out` : un aperçu SVG par page, une fiche de revue humaine non
exécutable par page, et un rapport JSON déterministe. N'écrit rien d'autre,
n'ouvre aucun accès réseau, ne contacte aucun service.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import charset, emit, paper, report, strokes, svg, synthetic_hand, textsource
from . import validator
from . import machine as machine_mod
from .errors import PaperxError
from .layout import paginate


def run_demo(text_path: str, out_dir: str, paper_id: str = "demo-a4") -> dict:
    paper_profile = paper.get(paper_id)
    machine_profile = machine_mod.P1S_UNCALIBRATED
    speeds = strokes.DEMO_SPEEDS
    limits = validator.DEFAULT_LIMITS

    source = textsource.load(text_path)
    layout = paginate(source, paper_profile)
    trajectories = strokes.build_all(layout, speeds)
    validations = tuple(
        validator.validate_page(traj, paper_profile, machine_profile, speeds, limits)
        for traj in trajectories
    )

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for traj, val in zip(trajectories, validations):
        (out / f"page-{traj.page_number:02d}.svg").write_text(
            svg.render_page(layout, traj, val.reach, val.machine_ready), encoding="utf-8")
        (out / f"revue-page-{traj.page_number:02d}.txt").write_text(
            emit.review_sheet(traj, machine_profile, val), encoding="utf-8")

    data = report.build(layout, trajectories, validations, machine_profile, speeds, limits)
    (out / "rapport.json").write_text(report.to_json(data), encoding="utf-8")
    return data


# --- Expérience falsifiable --------------------------------------------------
#
# Chaque hypothèse est accompagnée de son critère de réfutation. Une hypothèse
# sans critère de réfutation n'est pas testée ici : en particulier, AUCUNE
# hypothèse ne porte sur la ressemblance de l'écriture avec une main humaine.

def run_experiment(text_path: str) -> tuple[list[dict], bool]:
    source = textsource.load(text_path)
    layout_result = paginate(source, paper.get("demo-a4"))
    trajectories = strokes.build_all(layout_result, strokes.DEMO_SPEEDS)
    validations = tuple(
        validator.validate_page(t, layout_result.paper, machine_mod.P1S_UNCALIBRATED,
                                strokes.DEMO_SPEEDS)
        for t in trajectories
    )
    coverage = layout_result.coverage
    reconstruit = layout_result.reconstruct()

    # Un accentué doit AJOUTER des traits à sa base ; une ligature doit être
    # plus large que sa partie gauche seule. Sinon l'accent a été perdu.
    accents_ok = True
    accents_verifies = 0
    for accentue, (base, _marque) in synthetic_hand.COMPOSED_BASES.items():
        accents_verifies += 1
        glyphe = synthetic_hand.GLYPHS.get(accentue)
        socle = synthetic_hand.GLYPHS.get(base if base != "i.dotless" else "i")
        if glyphe is None or socle is None or len(glyphe.strokes) <= len(socle.strokes) - 1:
            accents_ok = False
    for ligature, (gauche, _droite, _recouvrement) in synthetic_hand.LIGATURES.items():
        accents_verifies += 1
        glyphe = synthetic_hand.GLYPHS.get(ligature)
        if glyphe is None or glyphe.advance <= synthetic_hand.GLYPHS[gauche].advance:
            accents_ok = False
    absents_conserves = all(
        reconstruit.count(u.char) == u.count for u in coverage.unsupported)
    aucun_trace_invente = all(
        m.char not in {s.char for t in trajectories for s in t.strokes}
        for t in trajectories for m in t.unsupported_marks)

    refus_machine = False
    try:
        emit.machine_output(trajectories[0], machine_mod.P1S_UNCALIBRATED, validations[0])
    except Exception:
        refus_machine = True

    resultats = [
        {
            "hypothese": "H1 — le texte inédit ressort exactement identique",
            "refute_si": "reconstruct() != source, ou sha256 du texte modifié",
            "mesure": f"{source.char_length} caractères, sha256 {source.sha256[:12]}…",
            "verdict": reconstruit == source.text,
        },
        {
            "hypothese": "H2 — chaque caractère accentué a un tracé propre",
            "refute_si": "un accentué partage exactement les traits de sa base",
            "mesure": f"{accents_verifies} caractères composés vérifiés, "
                      f"socle français manquant : "
                      f"{list(charset.missing_from_french_baseline()) or 'aucun'}",
            "verdict": accents_ok and not charset.missing_from_french_baseline(),
        },
        {
            "hypothese": "H3 — les caractères absents sont signalés et conservés",
            "refute_si": "un caractère absent disparaît, est remplacé, ou un tracé "
                         "est inventé à sa place",
            "mesure": f"{coverage.unsupported_count} occurrence(s) : "
                      + ", ".join(u.codepoint for u in coverage.unsupported),
            "verdict": absents_conserves and aucun_trace_invente,
        },
        {
            "hypothese": "H4 — aucune sortie machine n'est produite",
            "refute_si": "machine_output() renvoie quoi que ce soit",
            "mesure": "profil " + machine_mod.P1S_UNCALIBRATED.ref(),
            "verdict": refus_machine and not any(v.machine_ready for v in validations),
        },
    ]
    return resultats, all(r["verdict"] for r in resultats)


def _summary(data: dict, out_dir: str) -> str:
    src = data["source"]
    mep = data["mise_en_page"]
    lines = [
        f"texte          : {src['origine']} ({src['caracteres']} caractères, "
        f"sha256 {src['sha256'][:12]}…)",
        f"préservation   : {'EXACTE' if src['preservation_exacte'] else 'ÉCHEC'}",
        f"pagination     : {mep['pages']} page(s), {mep['lignes']} lignes, "
        f"profil {data['profils']['papier']['profil']}",
        f"écriture       : {data['ecriture']['reference']} — personnalisée : "
        f"{data['ecriture']['personnalisee']}",
        f"non pris en ch.: {mep['couverture']['caracteres_non_pris_en_charge']} "
        "caractère(s) signalé(s), 0 supprimé, 0 remplacé",
    ]
    for page in data["pages"]:
        val = page["validation"]
        reach = val["atteignabilite"]
        part = f"{reach['part_page_inaccessible'] * 100:.1f} %" if reach else "n/c"
        lines.append(
            f"  page {page['page']:>2}     : {page['traits']} traits, "
            f"{page['levees_plume']} levées | trajectoire valide : "
            f"{val['trajectoire_valide']} | prêt machine : {val['pret_machine']} "
            f"| hors course : {part}")
    lines += [
        f"sortie machine : refusée ({data['sortie_machine']['code_verrou']}) — "
        "aucun G-code, aucun accès imprimante",
        f"tarif indicatif: {data['tarif']['total_centimes']} centimes "
        f"({data['tarif']['pages']} × {data['tarif']['prix_unitaire_centimes']}) — "
        f"{data['tarif']['zone']}, remise {data['tarif']['remise']}, "
        f"paiement {'activé' if data['tarif']['paiement_active'] else 'désactivé'}",
        f"sorties        : {out_dir}/page-NN.svg, revue-page-NN.txt, rapport.json",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paperx", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="paginer un texte et produire l'aperçu")
    demo.add_argument("--text", default="samples/texte_demo_fr.txt")
    demo.add_argument("--out", default="out")
    demo.add_argument("--paper", default="demo-a4")
    exp = sub.add_parser("experience", help="expérience falsifiable sur un texte inédit")
    exp.add_argument("--text", default="samples/texte_experience_fr.txt")

    args = parser.parse_args(argv)
    try:
        if args.command == "experience":
            resultats, tout_ok = run_experiment(args.text)
            print(f"Expérience falsifiable — texte : {args.text}\n")
            for r in resultats:
                print(f"[{'OK   ' if r['verdict'] else 'ÉCHEC'}] {r['hypothese']}")
                print(f"          réfutée si : {r['refute_si']}")
                print(f"          mesure     : {r['mesure']}")
            print("\nAucune hypothèse ne porte sur la ressemblance avec une écriture "
                  "humaine : rien n'est mesurable à ce sujet ici.")
            return 0 if tout_ok else 1
        data = run_demo(args.text, args.out, args.paper)
    except PaperxError as exc:
        print(f"paperx : {type(exc).__name__} — {exc}", file=sys.stderr)
        return 2
    print(_summary(data, args.out))
    return 0
