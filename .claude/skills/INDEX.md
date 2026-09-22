# Index des Skills TriosSeconverter

Les skills sont des commandes slash utilisables dans Claude Code.
Fichiers source : `.claude/commands/[nom].md`
Usage : `/nom-du-skill` dans Claude Code

---

## Point d'entrée : /manager

**`/manager [demande en français]`** — Coordinateur central. Analyse toute demande
et sélectionne automatiquement le bon agent. Utiliser en priorité.

---

## Groupe OCR — Qualité et corrections

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/analyser-qualite-ocr` | analyser-qualite-ocr.md | Évalue toutes les images, classe les problèmes |
| `/debug-bornier` | debug-bornier.md | Analyse une image spécifique mal lue |
| `/analyser-image-profonde` | analyser-image-profonde.md | Histogramme, 5 chaînes prétraitement, PSM |
| `/visualiser-colonnes` | visualiser-colonnes.md | Image annotée des frontières de colonnes |
| `/optimiser-tesseract` | optimiser-tesseract.md | Ajustements Tesseract basés sur métriques image |
| `/optimiser-prompt-claude` | optimiser-prompt-claude.md | Itère le prompt Claude Vision sur image réelle |
| `/corriger-ocr` | corriger-ocr.md | Ajoute une valeur à data_dictionary.json |
| `/alimenter-dictionnaire` | alimenter-dictionnaire.md | Charge depuis un Excel corrigé manuellement |

---

## Groupe Données — Excel et classeur

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/valider-classeur` | valider-classeur.md | Intégrité Excel (pagination, pieds de page) |
| `/audit-borniers` | audit-borniers.md | Cohérence métier des données borniers |
| `/comparer-versions` | comparer-versions.md | Avant/après modification — détecte régressions |

---

## Groupe Interface UX

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/implementer-workflow-ux` | implementer-workflow-ux.md | 5 phases de refonte UX (1=cartes, 2=toolbar, 3=stepper, 4=dashboard, 5=dessins) |
| `/ameliorer-interface` | ameliorer-interface.md | Audit UX complet 6 critères |
| `/ajouter-apercu` | ajouter-apercu.md | Panneau aperçu avant sauvegarde |
| `/apprendre-interface` | apprendre-interface.md | Capitalise leçons UX dans la mémoire |

---

## Groupe Architecture

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/implementer-feature` | implementer-feature.md | Nouvelle fonctionnalité A→Z avec impact/plan/code/test |
| `/revoir-architecture` | revoir-architecture.md | Vérifie 8 règles fondamentales du projet |
| `/auditer-code-mort` | auditer-code-mort.md | Détecte fonctions/imports inutilisés |
| `/profiler-extraction` | profiler-extraction.md | Mesure performances pipeline OCR |
| `/isoler-modes-ocr` | isoler-modes-ocr.md | Vérifie isolation entre modes OCR |
| `/tracer-valeur` | tracer-valeur.md | Trace une valeur de la réponse brute → Excel |
| `/valider-fidelite-log` | valider-fidelite-log.md | Vérifie complétude d'un .jsonl pour replay |

---

## Groupe CAD — Pipeline PDF→DXF

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/implementer-cad-vectoriel` | implementer-cad-vectoriel.md | Pipeline extraction géométrie PDF→DXF |
| `/implementer-cad-blocs` | implementer-cad-blocs.md | Blocs AutoCAD depuis tableaux de légende |

---

## Groupe Environnement

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/diagnostiquer-env` | diagnostiquer-env.md | Python, Tesseract, dépendances, fichiers critiques |
| `/changer-config` | changer-config.md | Modifie un paramètre dans config.py |
| `/nouveau-template` | nouveau-template.md | Crée un modèle de tableau dans templates.json |

---

## Groupe Livraison

| Skill | Fichier | Usage |
|-------|---------|-------|
| `/tester` | tester.md | Lance pytest et analyse les échecs |
| `/nouvelle-version` | nouvelle-version.md | Badge, CLAUDE.md, tag Git, compilation exe |
| `/build-exe` | build-exe.md | Compile .exe PyInstaller autonome |
| `/rapport-livraison` | rapport-livraison.md | Rapport complet de livraison |
| `/nettoyer-projet` | nettoyer-projet.md | Supprime fichiers temporaires |

---

## Mémoire persistante des agents

Les agents accumulent leur expertise dans :
```
memory/
  user_profile.md          → Profil utilisateur (Triomphe, électrotechnicien)
  project_triosseconverter.md → État du projet
  ocr_engines_comparison.md → Comparaison moteurs OCR
  ux_ui_expertise.md        → Expertise UX/Tkinter (18+ leçons)
  cad_expertise.md          → Expertise pipeline CAD/DXF
  manager_agent.md          → Logique de sélection du manager
```
