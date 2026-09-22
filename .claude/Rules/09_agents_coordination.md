# Règle 09 — Coordination des agents IA

## Point d'entrée unique : /manager

Pour toute demande, utiliser `/manager` en premier.
L'agent manager analyse la demande et sélectionne automatiquement le bon agent.

```
Demande utilisateur → /manager → Analyse → Agent optimal → Exécution → Rapport
```

## Tableau de décision rapide

| Symptôme | Agent recommandé |
|----------|-----------------|
| OCR mal lu / image floue | `/debug-bornier` ou `/analyser-image-profonde` |
| Toutes les images à évaluer | `/analyser-qualite-ocr` |
| Colonnes mal détectées | `/visualiser-colonnes` |
| Claude Vision fait des erreurs | `/optimiser-prompt-claude` |
| Ajouter correction OCR | `/corriger-ocr` |
| Excel incohérent | `/valider-classeur` + `/audit-borniers` |
| Interface à améliorer | `/ameliorer-interface` ou `/implementer-workflow-ux` |
| Nouvelle fonctionnalité | `/implementer-feature` |
| Code désorganisé | `/revoir-architecture` |
| Trop lent | `/profiler-extraction` |
| Python/Tesseract cassé | `/diagnostiquer-env` |
| Préparer la livraison | `/tester` → `/nouvelle-version` → `/build-exe` |
| Dessins CAD problématiques | `/implementer-cad-vectoriel` |
| Blocs AutoCAD manquants | `/implementer-cad-blocs` |
| Mémoriser les leçons UX | `/apprendre-interface` |

## Groupes d'agents par domaine

### Groupe OCR (8 agents)
`/analyser-qualite-ocr`, `/debug-bornier`, `/analyser-image-profonde`,
`/visualiser-colonnes`, `/optimiser-tesseract`, `/optimiser-prompt-claude`,
`/corriger-ocr`, `/alimenter-dictionnaire`

### Groupe Données (3 agents)
`/valider-classeur`, `/audit-borniers`, `/comparer-versions`

### Groupe Interface UX (4 agents)
`/implementer-workflow-ux`, `/ameliorer-interface`, `/ajouter-apercu`, `/apprendre-interface`

### Groupe Architecture (7 agents)
`/implementer-feature`, `/revoir-architecture`, `/auditer-code-mort`,
`/profiler-extraction`, `/isoler-modes-ocr`, `/tracer-valeur`, `/valider-fidelite-log`

### Groupe CAD (2 agents)
`/implementer-cad-vectoriel`, `/implementer-cad-blocs`

### Groupe Environnement (3 agents)
`/diagnostiquer-env`, `/changer-config`, `/nouveau-template`

### Groupe Livraison (5 agents)
`/tester`, `/nouvelle-version`, `/build-exe`, `/rapport-livraison`, `/nettoyer-projet`

## Règles pour les agents

1. **Lire la mémoire avant d'intervenir** : `memory/ux_ui_expertise.md`, `memory/cad_expertise.md`
2. **Ne jamais modifier le moteur** sans demande explicite de l'utilisateur
3. **Après une session UX/CAD** : appeler `/apprendre-interface` pour capitaliser
4. **Avant une nouvelle feature** : appeler `/revoir-architecture` pour vérifier l'impact
5. **Tester visuellement** les changements CAD par comparaison PDF vs reconstruction

## Création d'un nouvel agent

Si aucun agent existant ne couvre le besoin :
1. Créer `.claude/commands/[nom-kebab-case].md`
2. Première ligne = description courte (affichée dans l'autocomplete)
3. Structure : description + étapes numérotées + exemples de code
4. Ajouter dans le tableau CLAUDE.md
5. Ajouter dans memory/manager_agent.md

## Capitalisation des leçons

Après chaque session significative :
```
/apprendre-interface  → capitalise les leçons UX/Tkinter
```

Les leçons sont stockées dans :
- `memory/ux_ui_expertise.md` — UX, Tkinter, workflow
- `memory/cad_expertise.md` — pipeline CAD, formules de rotation
- `memory/project_triosseconverter.md` — état général du projet
