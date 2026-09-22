# Skills — Guide d'utilisation

## Comment utiliser un skill

Dans Claude Code, tapez `/nom-du-skill` dans la zone de texte.
Exemple : `/manager` ou `/debug-bornier`.

Le skill est chargé et ses instructions guident l'agent IA pour accomplir la tâche.

## Point d'entrée recommandé

Pour toute demande, commencer par :
```
/manager [décrivez votre problème ou besoin en français]
```

Le manager analyse et dispatch automatiquement vers le bon skill.

## Référence

Voir `INDEX.md` pour la liste complète des skills avec leur description.
Les fichiers sources des skills sont dans `.claude/commands/`.

## Créer un nouveau skill

1. Créer `.claude/commands/[nom-kebab].md`
2. Première ligne = description courte (visible dans l'autocomplete)
3. Corps = instructions pour l'agent (en markdown)
4. Ajouter dans INDEX.md et dans CLAUDE.md (section Skills)

## Skills automatiques

Le `/manager` peut créer de nouveaux skills si aucun existant ne convient.
Le nouveau skill est automatiquement sauvegardé dans `.claude/commands/`.
