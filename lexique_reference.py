"""
Lexique de référence de la règle de cohérence (étape 9) : codes tirés des Excel déjà
corrigés par l'utilisateur (QUALITE_LEXIQUE_DOSSIER, feuille QUALITE_LEXIQUE_FEUILLE).

Ces Excel contiennent eux-mêmes des erreurs : le lexique ne sert qu'à signaler et proposer,
jamais à modifier. Pour mesurer sans tricher, un document peut être exclu (`exclure`).
"""
from pathlib import Path
from typing import Optional, Set

from config import Config
from controle_qualite import formes


def _entetes_connus() -> Set[str]:
    from template import TemplateManager
    gestion = TemplateManager()
    return {c.upper() for nom in gestion.names() for c in gestion.get(nom).columns}


def charger_lexique(dossier: Path, exclure: Optional[str] = None,
                    feuille: Optional[str] = None) -> Set[str]:
    """Formes des cellules des feuilles « Listing » (en-têtes et pieds de page écartés)."""
    import openpyxl
    dossier = Path(dossier)
    if not dossier.is_dir():
        return set()
    feuille = feuille or Config.QUALITE_LEXIQUE_FEUILLE
    entetes = _entetes_connus()
    lexique: Set[str] = set()
    for chemin in sorted(dossier.glob('*.xlsx')):
        if exclure and exclure.upper() in chemin.stem.upper().replace(' ', ''):
            continue
        wb = openpyxl.load_workbook(chemin, read_only=True, data_only=True)
        try:
            if feuille not in wb.sheetnames:
                continue
            for ligne in wb[feuille].iter_rows(values_only=True):
                valeurs = [str(v) for v in ligne if v is not None and str(v).strip()]
                if valeurs and all(v.strip().upper() in entetes for v in valeurs):
                    continue
                for v in valeurs:
                    # Pied de page (« P.E.T. : … », « NO PLAN : … ») : pas un code du tableau.
                    if ':' not in v:
                        lexique.update(formes(v))
        finally:
            wb.close()
    return lexique
