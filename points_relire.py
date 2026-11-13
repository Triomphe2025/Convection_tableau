"""
Points à relire (phase 1B, étape 4) : construit, à partir des structures que le Converter a
déjà (résultats lus + feuille Borniers rendue), la liste des points à vérifier et l'écrit dans
`<nom>_points.json`. Module pur — aucune lecture de fichier, aucune logique métier du Converter.

L'Excel ne change pas : les points REFLÈTENT les cellules déjà colorées et commentées par
`generer_classeur`. La cellule_excel vient de la disposition rendue (sauts de page du classeur +
`generer_classeur.ligne_excel`), jamais d'un calcul à part : chaque point désigne donc exactement
une cellule qui porte le fond et le commentaire de sa sorte.

Chaque point : id stable, etat « a_voir » (la relecture de la phase 2D le mettra à jour dans ce
même fichier), page (numéro PDF) + page_imprimee (numéro du pied), bornier, ligne, colonne,
valeur, suggestion, sorte, raison, confiance, cellule_excel, zone (cellule 0–1 si le Converter a
fourni les positions, sinon boîte de ligne avec l'indicateur, sinon None).
"""
import json
import re
from datetime import datetime
from pathlib import Path

from config import Config

VERSION = 1

# Fond de cellule → sorte (mêmes noms que la légende, sans accents).
_SORTE_PAR_COULEUR = {
    Config.COULEUR_CONFIANCE_BASSE.upper(): 'confiance_basse',
    Config.COULEUR_ILLISIBLE.upper(): 'illisible',
    Config.COULEUR_CORRIGE.upper(): 'corrige',
    Config.COULEUR_CONSERVATION.upper(): 'conservation',
    Config.COULEUR_QUALITE.upper(): 'qualite',
    Config.COULEUR_DEDUIT.upper(): 'deduit',
}
_SORTE_PIED = ('deduit',)
_SUGGESTION_RE = re.compile(r'peut-être\s+«\s*(.+?)\s*»')


def _rgb(cellule):
    return str(cellule.fill.fgColor.rgb)[-6:].upper() if cellule.fill.fill_type == 'solid' else ''


def _debuts_blocs(ws):
    """Début de chaque bloc reconstruit depuis les sauts de page du classeur (1 + id du saut)."""
    sauts = sorted(brk.id for brk in ws.row_breaks.brk)
    return [1] + [identifiant + 1 for identifiant in sauts]


def _bloc_de_ligne(debuts, ligne):
    """Indice du bloc (résultat) qui contient cette ligne de la feuille."""
    indice = 0
    for i, debut in enumerate(debuts):
        if debut <= ligne:
            indice = i
    return indice


def _rang_de_ligne(debut, resultat, ligne):
    """Rang de la ligne lue placée sur cette ligne de la feuille, ou None (pied, rembourrage)."""
    from generer_classeur import ligne_excel
    for rang in range(len(resultat.get('rows') or [])):
        if ligne_excel(debut, resultat, rang) == ligne:
            return rang
    return None


def _bornier(meta):
    """Nom du bornier, depuis le pied livré (BORNIER sinon CABLE)."""
    return (meta.get('BORNIER') or meta.get('CABLE') or '') or None


def _donnees_alerte(resultat, rang, colonne, sorte):
    """(raison, suggestion, confiance) de la cellule, depuis les DONNÉES d'alerte
    (a_verifier, corrections_o, confidence) — jamais le texte du commentaire."""
    rows = resultat.get('rows') or []
    row = rows[rang] if rang is not None and rang < len(rows) else {}
    confs = row.get('confidence') or []
    conf = confs[colonne] if colonne is not None and colonne < len(confs) else None
    if sorte == 'confiance_basse':
        return f"confiance OCR basse ({conf} %)", None, conf
    if sorte == 'illisible':
        return f"caractère illisible ({Config.MARQUEUR_ILLISIBLE})", None, conf
    if sorte == 'corrige':
        origine = (row.get('corrections_o') or {}).get(colonne)
        raison = (f"coquille O/0 corrigée, l'original porte {origine}" if origine
                  else "coquille O/0 corrigée")
        return raison, None, conf
    if sorte in ('conservation', 'qualite'):
        for a in resultat.get('a_verifier') or []:
            if a.get('ligne') == rang and a.get('colonne') == colonne:
                sug = a.get('proposition')
                if not sug:
                    m = _SUGGESTION_RE.search(a.get('message') or '')
                    sug = m.group(1) if m else None
                return a.get('message'), sug, conf
        return None, None, conf
    if sorte == 'deduit':
        return "case de pied déduite des autres pages du document", None, None
    return None, None, conf


def _zone(resultat, rang, colonne, n_cols):
    """Zone de la cellule en 0–1 : boîte de ligne (positions fournies) coupée aux bornes de
    colonnes ; sinon boîte de ligne avec l'indicateur ; sinon None."""
    if rang is None:
        return None
    boites = {z['ligne']: z['boite'] for z in resultat.get('zones') or []}
    boite = boites.get(rang)
    if boite is None:
        return None
    x0, y0, x1, y1 = boite
    bornes = resultat.get('bornes_colonnes')
    if bornes and colonne is not None and colonne + 1 < len(bornes):
        return {'niveau': 'cellule', 'boite': [bornes[colonne], y0, bornes[colonne + 1], y1]}
    return {'niveau': 'ligne', 'boite': [x0, y0, x1, y1]}


def _point_cellule(cellule, sorte, resultat, debut, n_cols):
    meta = resultat.get('metadata') or {}
    headers = resultat.get('headers') or []
    colonne_i = cellule.column - 1
    rang = None if sorte in _SORTE_PIED else _rang_de_ligne(debut, resultat, cellule.row)
    colonne = (headers[colonne_i] if rang is not None and colonne_i < len(headers) else None)
    raison, suggestion, confiance = _donnees_alerte(resultat, rang, colonne_i, sorte)
    return {
        'id': f"{cellule.coordinate}-{sorte}",
        'etat': 'a_voir',
        'sorte': sorte,
        'page': resultat.get('_page_pdf'),
        'page_imprimee': meta.get('PAGE'),
        'bornier': _bornier(meta),
        'ligne': None if rang is None else rang + 1,
        'colonne': colonne,
        'valeur': cellule.value,
        'suggestion': suggestion,
        'raison': raison,
        'confiance': confiance,
        'cellule_excel': cellule.coordinate,
        'zone': _zone(resultat, rang, colonne_i, n_cols),
    }


def _point_page(sorte, page, page_imprimee, bornier, raison, n):
    return {
        'id': f"page-{page}-{sorte}-{n}", 'etat': 'a_voir', 'sorte': sorte,
        'page': page, 'page_imprimee': page_imprimee, 'bornier': bornier,
        'ligne': None, 'colonne': None, 'valeur': None, 'suggestion': None,
        'raison': raison, 'confiance': None, 'cellule_excel': None, 'zone': None,
    }


def _points_pages(valides, verdicts=None):
    """Points de page entière (sans cellule), depuis les DONNÉES : scan dégradé
    (`controle_page['degradee']`) et vérification (`verdicts`)."""
    points = []
    for resultat in valides:
        cp = resultat.get('controle_page') or {}
        if cp.get('degradee'):
            meta = resultat.get('metadata') or {}
            taux = cp.get('taux')
            raison = (f"scan dégradé (divergence {taux:.0%})" if isinstance(taux, (int, float))
                      else "scan dégradé")
            points.append(_point_page('page_degradee', resultat.get('_page_pdf'),
                                      meta.get('PAGE'), _bornier(meta), raison, len(points)))
    for v in verdicts or []:
        points.append(_point_page('verification', v.get('page'), v.get('page_imprimee'),
                                  v.get('bornier'), v.get('message'), len(points)))
    return points


def construire(valides, ws, debuts=None, document='', empreinte='', excel='', type_doc='',
               modele='', arrete=False, verdicts=None):
    """Objet englobant des points à relire, reflet des cellules colorées de la feuille Borniers.

    `debuts` : débuts de bloc de la disposition réelle rendue par generer_classeur ; à défaut,
    reconstruits depuis les sauts de page du classeur (repli, équivalent).
    """
    debuts = debuts if debuts is not None else _debuts_blocs(ws)
    points = []
    for ligne in ws.iter_rows():
        for cellule in ligne:
            sorte = _SORTE_PAR_COULEUR.get(_rgb(cellule))
            if not sorte:
                continue
            i = _bloc_de_ligne(debuts, cellule.row)
            resultat = valides[i] if i < len(valides) else {}
            n_cols = len(resultat.get('headers') or [])
            points.append(_point_cellule(cellule, sorte, resultat, debuts[i], n_cols))
    points += _points_pages(valides, verdicts)
    return {
        'version': VERSION,
        'document': document,
        'empreinte': empreinte,
        'excel': excel,
        'type': type_doc,
        'modele': modele,
        'genere_le': datetime.now().isoformat(timespec='seconds'),
        'arrete': arrete,
        'points': points,
    }


def ecrire(objet, chemin):
    """Écrit l'objet dans <nom>_points.json (UTF-8, lisible)."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(objet, ensure_ascii=False, indent=1), encoding='utf-8')
    return chemin
