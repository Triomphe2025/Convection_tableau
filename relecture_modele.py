"""Relecture (phase 2D) : lit `<nom>_points.json`, suit l'état de chaque point (À voir, Gardé,
Corrigé, Passé) et écrit les corrections dans le classeur — module pur, sans Qt.

Seule l'écriture (sur action de l'utilisateur) modifie un classeur, et d'abord une copie de
sauvegarde `<nom>_avant_relecture.xlsx` est faite une fois. La mise en forme des autres cellules
est conservée (openpyxl relit le classeur). Un classeur verrouillé (ouvert dans Excel) lève
`VerrouError` sans perdre la relecture (l'état est déjà dans le json). La régénération d'une image
de page depuis le PDF est fournie pour l'interface (fil de travail).
"""
import json
import shutil
from datetime import datetime
from pathlib import Path

A_VOIR = "a_voir"
GARDE = "garde"
CORRIGE = "corrige"
PASSE = "passe"
_TRAITES_AVEC_ECRITURE = (GARDE, CORRIGE)   # retirent l'orange + commentaire ; PASSE : tel quel
_SUFFIXE_BACKUP = "_avant_relecture"


class VerrouError(Exception):
    """Le classeur est verrouillé (probablement ouvert dans Excel) : écriture impossible."""


class Relecture:
    """État de relecture d'un document, persisté dans son `<nom>_points.json`."""

    def __init__(self, chemin_points):
        self._chemin = Path(chemin_points)
        self._data = json.loads(self._chemin.read_text(encoding="utf-8"))

    @property
    def enveloppe(self) -> dict:
        return self._data

    def points(self) -> list:
        return self._data.get("points", [])

    def point(self, pid: str) -> dict:
        for p in self.points():
            if p.get("id") == pid:
                return p
        raise KeyError(pid)

    def total(self) -> int:
        return len(self.points())

    def a_voir(self) -> int:
        return sum(1 for p in self.points() if p.get("etat") == A_VOIR)

    def traites(self) -> int:
        return sum(1 for p in self.points() if p.get("etat") != A_VOIR)

    # ── Décisions (persistées à chaque fois) ─────────────────────────
    def garder(self, pid: str) -> None:
        self._maj(pid, GARDE)

    def corriger(self, pid: str, valeur) -> None:
        self._maj(pid, CORRIGE, valeur)

    def passer(self, pid: str) -> None:
        self._maj(pid, PASSE)

    def _maj(self, pid: str, etat: str, valeur=None) -> None:
        p = self.point(pid)
        p["etat"] = etat
        if valeur is not None:
            p["valeur_corrigee"] = valeur
        self._ecrire()

    def _ecrire(self) -> None:
        self._chemin.write_text(json.dumps(self._data, ensure_ascii=False, indent=1),
                                encoding="utf-8")

    # ── Lecture de la ligne complète (contexte de la cellule douteuse) ──
    def colonnes(self) -> list:
        """Colonnes du modèle de tableau (en-têtes de la ligne), ou []."""
        from template import TemplateManager
        try:
            return list(TemplateManager().get(self._data.get("modele")).columns)
        except Exception:
            return []

    def ligne_du_point(self, point: dict, feuille: str = "Borniers"):
        """(colonnes, valeurs) de la ligne entière du point, lue dans l'Excel ; ([], []) sinon."""
        coord = point.get("cellule_excel")
        cols = self.colonnes()
        chemin = self.chemin_excel()
        if not coord or not cols or not chemin.exists():
            return [], []
        from openpyxl import load_workbook
        from openpyxl.utils.cell import coordinate_to_tuple
        rangee = coordinate_to_tuple(coord)[0]
        wb = load_workbook(chemin, read_only=True, data_only=True)
        try:
            ws = wb[feuille] if feuille in wb.sheetnames else wb.active
            valeurs = [ws.cell(row=rangee, column=i + 1).value for i in range(len(cols))]
        finally:
            wb.close()
        return cols, ["" if v is None else str(v) for v in valeurs]

    # ── Écriture dans l'Excel ────────────────────────────────────────
    def chemin_excel(self) -> Path:
        return Path(self._data.get("excel", ""))

    def chemin_backup(self, excel=None) -> Path:
        x = Path(excel) if excel else self.chemin_excel()
        return x.with_name(x.stem + _SUFFIXE_BACKUP + x.suffix)

    def enregistrer_excel(self, excel=None, feuille: str = "Borniers") -> Path:
        """Écrit les points Gardé/Corrigé dans le classeur ; copie de sauvegarde une seule fois."""
        from openpyxl import load_workbook
        from openpyxl.comments import Comment
        from openpyxl.styles import PatternFill
        chemin = Path(excel) if excel else self.chemin_excel()
        if not chemin.exists():
            raise FileNotFoundError(chemin)
        backup = self.chemin_backup(chemin)
        if not backup.exists():
            shutil.copy2(chemin, backup)
        wb = load_workbook(chemin)
        ws = wb[feuille] if feuille in wb.sheetnames else wb.active
        date = datetime.now().strftime("%d/%m/%Y")
        for p in self.points():
            coord = p.get("cellule_excel")
            if not coord or p.get("etat") not in _TRAITES_AVEC_ECRITURE:
                continue
            cellule = ws[coord]
            if p.get("etat") == CORRIGE and p.get("valeur_corrigee") is not None:
                cellule.value = p["valeur_corrigee"]
            cellule.fill = PatternFill(fill_type=None)   # retire l'orange des points traités
            cellule.comment = Comment(f"Relu le {date}", "Relecture")
        try:
            wb.save(chemin)
        except PermissionError as exc:
            raise VerrouError(
                "Le classeur est ouvert dans Excel : ferme-le puis réessaie. "
                "La relecture en cours est conservée.") from exc
        return chemin


def regenerer_image_page(pdf, page, destination, zoom=2.0) -> Path:
    """Rend une page du PDF en PNG (pour l'extrait de scan quand l'image de travail a disparu).
    Rend le chemin produit, ou lève — l'appelant l'exécute dans un fil de travail."""
    import fitz
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open(str(pdf)) as doc:
        if not 0 < page <= len(doc):
            raise ValueError(f"page {page} hors du document ({len(doc)} pages)")
        import fitz as _f
        doc[page - 1].get_pixmap(matrix=_f.Matrix(zoom, zoom)).save(str(destination))
    return destination
