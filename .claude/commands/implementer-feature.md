Atelier d'implémentation d'une nouvelle fonctionnalité dans TriosSeconverter, de la spécification au code testé.

Tu es un ingénieur logiciel senior qui guide le développement d'une nouvelle feature de A à Z,
en respectant strictement l'architecture et les conventions du projet.

## Étape 1 — Recueil des besoins

Pose les questions suivantes à l'utilisateur :

1. **Quoi :** Décris la fonctionnalité en une phrase (ce que l'utilisateur peut faire qu'il ne peut pas faire aujourd'hui).
2. **Pourquoi :** Quel problème concret cela résout-il ? (gain de temps, réduction d'erreur, etc.)
3. **Où :** Dans quel contexte l'utilise-t-on ? (avant/pendant/après la conversion, dans l'interface, en ligne de commande)
4. **Critères :** Comment sait-on que c'est terminé et correct ?

Reformule la feature en une user story :
> "En tant qu'électricien, je veux [action] afin de [bénéfice]."

## Étape 2 — Analyse d'impact sur l'architecture

Lis les fichiers concernés et détermine lesquels sont impactés :

```
interface.py      → affichage uniquement, JAMAIS de logique métier
converter.py      → orchestration, callbacks on_progress/on_log
ocr_processor.py  → BornierTableExtractor : tout ce qui touche à l'OCR
generer_classeur.py → génération Excel/Word
word_table_importer.py → import tableaux Word
template.py       → modèles de tableau
config.py         → TOUS les paramètres configurables
data_dictionary.py → corrections OCR
```

Pour chaque fichier impacté, note :
- **Quelle méthode** est modifiée ou ajoutée
- **Quel paramètre** est ajouté (doit être optionnel avec valeur par défaut)
- **Quel risque** de régression sur le code existant

## Étape 3 — Plan d'implémentation

Présente le plan à l'utilisateur avant de coder :

```
PLAN D'IMPLÉMENTATION — [NOM DE LA FEATURE]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Fichiers modifiés :
  1. config.py          → Ajouter paramètre [NOM] = [valeur défaut]
  2. [fichier_metier].py → Ajouter méthode [nom_methode(args)]
  3. interface.py       → Ajouter bouton/widget [description]

Paramètres ajoutés (optionnels, rétrocompatibles) :
  → [parametre]: [type] = [defaut]  # Impact: [description]

Tests à écrire :
  → tests/test_[feature].py : [cas nominaux + cas limites]

Durée estimée : [N] modifications
```

Attends la validation de l'utilisateur avant de passer à l'étape 4.

## Étape 4 — Vérification des contraintes absolues

Avant de coder, vérifie chaque règle du projet :

**Règle 1 — Pas de logique dans l'interface**
Tout calcul ou traitement doit être dans `converter.py` ou dans le module métier.
`interface.py` ne contient que des appels à ces modules et la mise à jour des widgets.

**Règle 2 — Paramètres dans config.py**
Toute valeur configurable (seuil, chemin, taille) doit être dans `config.py`.
Vérifier : `grep -r "TODO\|FIXME\|hardcod" [fichier]` avant de livrer.

**Règle 3 — Thread safety Tkinter**
Si la feature modifie un widget depuis un callback de conversion :
→ passer par `self._queue.put({...})` dans le thread de travail
→ traiter dans `_poll_queue()` dans le thread UI

**Règle 4 — Rétrocompatibilité**
Tout nouveau paramètre de fonction doit avoir une valeur par défaut.
Les appels existants ne doivent pas être modifiés.

**Règle 5 — Erreur récupérable**
Si la feature peut échouer (fichier absent, OCR raté), l'erreur ne doit pas stopper
le traitement global. Logger l'erreur et continuer.

## Étape 5 — Implémentation fichier par fichier

Pour chaque fichier :
1. Lire la section exacte à modifier
2. Effectuer l'edit minimal (pas de réécriture complète)
3. Indiquer la ligne : `fichier.py:XXX`
4. Ne pas ajouter de commentaires sur le QUOI — seulement le POURQUOI si non évident

## Étape 6 — Test immédiat

```powershell
# Test rapide en ligne de commande
env\Scripts\python.exe -c "
from [module] import [Classe]
# Test minimal de la nouvelle feature
obj = [Classe]()
result = obj.[nouvelle_methode]([args_test])
print('OK:', result)
"
```

Si la feature touche l'interface :
```powershell
env\Scripts\python.exe interface.py
```

Si des tests unitaires existent :
```powershell
env\Scripts\python.exe -m pytest tests\ -v -k [nom_test]
```

## Étape 7 — Mise à jour de la documentation

Si la feature ajoute un paramètre dans `config.py` :
→ Mettre à jour le tableau Configuration dans `CLAUDE.md`

Si la feature ajoute une méthode publique importante :
→ Mettre à jour `Contexte\PROCESSUS_OCR.md` si c'est dans le pipeline OCR

Résume les changements effectués :
```
FEATURE IMPLÉMENTÉE : [nom]
  ✓ [fichier1.py:ligne] — [ce qui a changé]
  ✓ [fichier2.py:ligne] — [ce qui a changé]
  ✓ Test passé : [description du test]
```
