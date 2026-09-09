# Expérience falsifiable

Objet : vérifier, sur un **texte inédit** que le banc d'essai n'a jamais servi à
régler, que la chaîne préserve exactement le français, signale ce qu'elle ne sait
pas faire, et refuse toute sortie machine.

Ce que l'expérience **ne teste pas**, faute de modèle : toute ressemblance de
l'écriture avec une main humaine. Il n'existe ici aucune hypothèse à ce sujet,
donc aucun résultat à ce sujet.

## Matériel

- Texte inédit : `samples/texte_experience_fr.txt` (1 192 caractères, sha256
  `bd900777f9f9…`), écrit pour cette expérience, contenant l'ensemble des accents
  français, cédilles, ligature `œ`, guillemets `« »`, tiret cadratin, espaces
  insécables, chiffres, capitales accentuées — et trois signes volontairement
  absents de l'écriture : `Ã` (U+00C3), `€` (U+20AC), `漢` (U+6F22).
- Profils : `demo-a4@1.0.0`, `synthetic-generic@1.0.0`, `demo-speeds@1.0.0`,
  `bambu-p1s@0.0.0+non-calibre`, `demo-limits@1.1.0`.

## Protocole

```bash
python3 -m paperx experience --text samples/texte_experience_fr.txt
```

Code de sortie `0` si les quatre hypothèses tiennent, `1` si l'une est réfutée.

## Hypothèses et critères de réfutation

| # | Hypothèse | Réfutée si |
|---|---|---|
| H1 | Le texte inédit ressort exactement identique | `reconstruct() != source` |
| H2 | Chaque caractère composé a un tracé propre | un accentué a le même nombre de traits que sa base, ou une ligature n'est pas plus large que sa partie gauche |
| H3 | Les caractères absents sont signalés et conservés | un caractère absent disparaît, est remplacé, ou un tracé est inventé à sa place |
| H4 | Aucune sortie machine n'est produite | `machine_output()` renvoie quoi que ce soit, ou une page passe `pret_machine = True` |

## Résultats observés (exécution du 2026-09-09)

| # | Verdict | Mesure |
|---|---|---|
| H1 | OK | 1 192 caractères, sha256 `bd900777f9f9…`, reconstruction identique |
| H2 | OK | 35 caractères composés vérifiés ; socle français manquant : aucun |
| H3 | OK | 3 occurrences signalées : U+00C3, U+20AC, U+6F22 ; 0 supprimée, 0 remplacée, 0 tracé inventé |
| H4 | OK | `CalibrationRequired` levée ; `pret_machine = False` sur toutes les pages |

Corpus complémentaire (`tests/test_preservation_texte.py`) : 300 corpus
pseudo-aléatoires déterministes (graine 20260909) mêlant accents, ligature,
guillemets, tabulation, `€`, `漢`, espaces multiples et lignes vides — tous
reconstruits à l'identique, chaque index du source apparaissant une fois et une
seule.

## Contrôle négatif

L'expérience doit pouvoir échouer. `tests/test_demonstration.py::
TestExperienceFalsifiable::test_experience_detecte_une_perte_de_texte` remplace
la reconstruction par une version qui écrase `é` en `e` : H1 est alors réfutée et
le code de sortie passe à `1`. Sans ce contrôle, un « OK » ne prouverait rien.

## Ce qu'un résultat OK ne prouve pas

Que le texte serait fidèlement **écrit sur du papier**. Aucune feuille n'a été
écrite, aucune machine n'a été calibrée, aucune encre n'a été observée. Le jour
où une plume touchera réellement le papier, tout est à revérifier : géométrie
mesurée, pose de la feuille, hauteurs, lisibilité réelle.
