Audit de cohérence des données de borniers dans le classeur Excel généré.

Tu es un ingénieur électricien qui vérifie la cohérence métier des données extraites avant de les utiliser dans la gestion de projet.

## Contexte métier

Un classeur de borniers électriques doit respecter ces règles :
- Les numéros de PAGE doivent être séquentiels et sans doublons
- Chaque bornier a un code BORNIER unique (ex: B702A)
- La station P.E.T. doit être la même sur tous les borniers d'un même projet
- Les données de colonnes doivent respecter les formats attendus

## Étape 1 — Extraction des métadonnées de tous les borniers

```powershell
env\Scripts\python.exe -c "
import openpyxl, re
from config import Config

wb = openpyxl.load_workbook('tous_les_borniers.xlsx', read_only=True)
ws = wb['Borniers']
page_size = Config.PAGE_SIZE
borniers = []

# Lire le pied de page de chaque bornier (avant-dernière ligne de chaque bloc)
for i in range(0, ws.max_row, page_size):
    pied1 = str(ws.cell(row=i + page_size - 1, column=2).value or '')
    pied2 = str(ws.cell(row=i + page_size, column=2).value or '')
    
    m_bornier = re.search(r'BORNIER\s*:\s*([A-Z0-9\-]+)', pied1, re.IGNORECASE)
    m_page    = re.search(r'PAGE\s*:\s*(\d+)', pied2, re.IGNORECASE)
    m_pet     = re.search(r'P\.E\.T[.\s]*:\s*([A-Z\s]+?)(?=BORNIER|$)', pied1, re.IGNORECASE)
    m_plan    = re.search(r'NO PLAN\s*:\s*([\w\s]+?)(?=\||INDICE|\$)', pied2, re.IGNORECASE)
    
    borniers.append({
        'index': i // page_size + 1,
        'bornier': m_bornier.group(1).strip() if m_bornier else '?',
        'page': int(m_page.group(1)) if m_page else None,
        'pet': m_pet.group(1).strip() if m_pet else '?',
        'plan': m_plan.group(1).strip() if m_plan else '?',
    })

import json
print(json.dumps(borniers, ensure_ascii=False, indent=2))
"
```

## Étape 2 — Contrôles de cohérence

Analyse les données extraites et signale :

**Contrôle 1 — Doublons de PAGE**
Y a-t-il plusieurs borniers avec le même numéro de PAGE ?
→ Anomalie : deux extractions du même plan physique

**Contrôle 2 — Séquence des pages**
Les numéros de page sont-ils croissants et sans trous importants (> 5 pages d'écart) ?
→ Anomalie : pages manquantes dans l'extraction

**Contrôle 3 — Codes BORNIER**
Y a-t-il des codes BORNIER inconnus (= "?") ou en doublon ?
→ Anomalie : pied de page non détecté par l'OCR

**Contrôle 4 — Uniformité P.E.T. et NO PLAN**
La station P.E.T. et le numéro de plan sont-ils identiques sur tous les borniers ?
→ Anomalie : images de projets différents mélangées

## Étape 3 — Tableau de synthèse

```
N° | Bornier | Page | P.E.T.  | NO PLAN       | Statut
 1 | B702A   |  92  | EPEULE  | VD23111 PE162 | ✓ OK
 2 | B703A   |  93  | EPEULE  | VD23111 PE162 | ✓ OK
 5 | ?       |  97  | ?       | ?             | ⚠ OCR MANQUÉ
```

## Étape 4 — Rapport et recommandations

Pour chaque anomalie détectée, propose une action concrète :
- Page manquante → "Vérifier si l'image bornier_XX.jpg a bien été extraite"
- Code bornier ? → "Utiliser /corriger-ocr pour ajouter la correction"
- Doublons → "Supprimer l'image en double dans images_borniers/"
- P.E.T. différents → "Vérifier si des images d'un autre projet sont mélangées"

Conclus par : "Audit terminé. X borniers vérifiés. X anomalies détectées."
