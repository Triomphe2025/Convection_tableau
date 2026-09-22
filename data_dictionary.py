"""
Dictionnaire OCR à deux niveaux pour TriosSeconverter.

Architecture :
  DataDictionary (data_dictionary.json)
      Dictionnaire FINAL — lecture seule pour l'utilisateur.
      Contient les valeurs validées et fiables.
      Jamais modifié directement : uniquement via validation du pending.
      Utilisé par correct() pour corriger les erreurs OCR.

  PendingDictionary (data_dictionary_pending.json)
      Dictionnaire EN ATTENTE — modifiable par l'utilisateur.
      Alimenté par :
        - import depuis fichier Excel (update_from_excel)
        - phase de validation manuelle (ValidationPageDialog)
      Validé par l'utilisateur avant insertion dans le dictionnaire final.

Flux typique :
    # Apprentissage depuis un Excel corrigé → vers pending
    stats = get_pending_dictionary().update_from_excel(Path("corrigé.xlsx"))
    # L'utilisateur review les valeurs dans l'interface, puis valide
    n = get_pending_dictionary().validate_values(get_dictionary())
    # Correction OCR (utilise uniquement le final)
    valeur, modifiee = get_dictionary().correct("SIGNAL", "RESERVE CABLFE")
"""

import json
import re
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional, Tuple

DICT_FILE         = Path(__file__).parent / "data_dictionary.json"
DICT_FILE_PENDING = Path(__file__).parent / "data_dictionary_pending.json"

# Valeurs à ne jamais enregistrer
_BLACKLIST = frozenset({
    '', 'NONE', 'NONE NONE', 'N/A', 'NA', '-', '--', '0', 'O', '.',
})

# Mots-clés structurels à ignorer (lignes de footer/header)
_SKIP_KEYWORDS = (
    'NOM DU CABLE', 'NO PLAN', 'P.E.T', 'M  T  I',
    'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES',
    'INDICE', 'PAGE :', 'EPEULE', 'METROPOLE',
)

# Validation stricte par colonne (utilisée par le dictionnaire FINAL)
_VALIDATORS: Dict[str, re.Pattern] = {
    'BORNE':       re.compile(r'^[A-Z0-9][A-Z0-9 \-]{0,14}$'),
    'COULEUR':     re.compile(r'^[A-Z0-9][A-Z0-9 /+\-]{0,17}$'),
    'SIGNAL':      re.compile(r'^[A-Za-z0-9 .+\-/()\'"/:_*#]{2,80}$'),
    'JARRETIERES': re.compile(r'^[A-Za-z0-9][A-Za-z0-9 .+\-/()*#]{0,28}$'),
}


# ══════════════════════════════════════════════════════════════════════
# Dictionnaire FINAL (lecture seule pour l'utilisateur)
# ══════════════════════════════════════════════════════════════════════

class DataDictionary:
    """
    Dictionnaire validé — protégé contre les modifications directes.
    Alimenté uniquement via PendingDictionary.validate_values().
    Utilisé en lecture seule pour la correction OCR.
    """

    def __init__(self, path: Path = DICT_FILE):
        self.path = path
        self._data: Dict[str, set] = {}
        self._load()

    # ── Persistance ────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, encoding='utf-8') as f:
                    raw = json.load(f)
                self._data = {k: set(v) for k, v in raw.items()}
            except Exception:
                self._data = {}

    def save(self) -> None:
        """Sauvegarde le dictionnaire (valeurs triées pour lisibilité)."""
        try:
            data = {k: sorted(v) for k, v in self._data.items() if v}
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Sauvegarde dictionnaire final échouée: {e}")

    # ── Validation ─────────────────────────────────────────────────────

    def _is_valid(self, column: str, value: str) -> bool:
        """Vérifie qu'une valeur est candidate pour le dictionnaire final."""
        stripped = value.strip()
        if not stripped or stripped.upper() in _BLACKLIST:
            return False
        if any(kw in stripped.upper() for kw in _SKIP_KEYWORDS):
            return False
        noise = sum(
            1 for c in stripped
            if not (c.isalnum() or c in " .-_/:+()'\"")
        )
        if noise > max(1, len(stripped) * 0.3):
            return False
        validator = _VALIDATORS.get(column.upper())
        return bool(validator.match(stripped)) if validator else len(stripped) >= 2

    # ── API interne (appelée par PendingDictionary.validate_values) ────

    def add_value(self, column: str, value: str) -> bool:
        """Ajoute une valeur si valide et nouvelle. Retourne True si ajoutée."""
        col, val = column.upper(), value.strip()
        if not self._is_valid(col, val):
            return False
        bucket = self._data.setdefault(col, set())
        if val not in bucket:
            bucket.add(val)
            return True
        return False

    def clear(self) -> None:
        """Vide complètement le dictionnaire final (admin seulement)."""
        self._data.clear()
        self.save()

    # ── Correction OCR ─────────────────────────────────────────────────

    def correct(
        self, column: str, ocr_value: str, cutoff: float = 0.82
    ) -> Tuple[str, bool]:
        """
        Corrige une valeur OCR par correspondance floue au dictionnaire final.

        Returns:
            (valeur_finale, True si corrigée / False si inchangée)
        """
        if not ocr_value:
            return ocr_value, False
        col = column.upper()
        known = list(self._data.get(col, set()))
        if not known:
            return ocr_value, False
        clean = ocr_value.strip()
        if clean in known:
            return clean, False
        matches = get_close_matches(clean, known, n=1, cutoff=cutoff)
        return (matches[0], True) if matches else (ocr_value, False)

    # ── Utilitaires ────────────────────────────────────────────────────

    def get_all(self, column: str) -> List[str]:
        """Retourne toutes les valeurs validées pour une colonne (triées)."""
        return sorted(self._data.get(column.upper(), set()))

    def stats(self) -> Dict[str, int]:
        """Retourne le nombre de valeurs connues par colonne."""
        return {k: len(v) for k, v in self._data.items() if v}

    def __repr__(self) -> str:
        s = ', '.join(f'{k}:{len(v)}' for k, v in self._data.items())
        return f"DataDictionary(final, {s or 'vide'})"


# ══════════════════════════════════════════════════════════════════════
# Dictionnaire EN ATTENTE (modifiable par l'utilisateur)
# ══════════════════════════════════════════════════════════════════════

class PendingDictionary:
    """
    Dictionnaire en attente de validation.

    Modifiable librement par l'utilisateur via l'interface (ajout,
    modification, suppression). Les valeurs ne sont utilisées pour les
    corrections OCR qu'après validation explicite via validate_values(),
    qui les déplace dans DataDictionary.
    """

    def __init__(self, path: Path = DICT_FILE_PENDING):
        self.path = path
        self._data: Dict[str, set] = {}
        self._load()

    # ── Persistance ────────────────────────────────────────────────────

    def _load(self) -> None:
        if self.path.exists():
            try:
                with open(self.path, encoding='utf-8') as f:
                    raw = json.load(f)
                self._data = {k: set(v) for k, v in raw.items()}
            except Exception:
                self._data = {}

    def save(self) -> None:
        try:
            data = {k: sorted(v) for k, v in self._data.items() if v}
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Sauvegarde dictionnaire en attente échouée: {e}")

    # ── CRUD (modifiable par l'utilisateur) ────────────────────────────

    def add_value(self, column: str, value: str) -> bool:
        """
        Ajoute une valeur. Validation souple (blacklist + bruit de base) :
        l'utilisateur reviewera avant validation finale.
        """
        col, val = column.upper(), value.strip()
        if not val or val.upper() in _BLACKLIST:
            return False
        # Refus si trop de caractères parasites
        noise = sum(
            1 for c in val
            if not (c.isalnum() or c in " .-_/:+()'\"")
        )
        if noise > max(1, len(val) * 0.4):
            return False
        bucket = self._data.setdefault(col, set())
        if val not in bucket:
            bucket.add(val)
            return True
        return False

    def remove_value(self, column: str, value: str) -> bool:
        """Supprime une valeur du dictionnaire en attente."""
        col = column.upper()
        bucket = self._data.get(col)
        if bucket and value in bucket:
            bucket.discard(value)
            return True
        return False

    def update_value(self, column: str, old_value: str, new_value: str) -> bool:
        """Modifie une valeur existante."""
        if self.remove_value(column, old_value):
            return self.add_value(column, new_value)
        return False

    # ── Import depuis Excel ────────────────────────────────────────────

    def update_from_excel(self, excel_path: Path) -> Dict[str, int]:
        """
        Extrait les valeurs uniques par colonne depuis un fichier Excel
        et les place dans le dictionnaire EN ATTENTE (pas dans le final).

        Retourne {colonne: nb_nouvelles_valeurs_ajoutées}.
        """
        import openpyxl
        wb = openpyxl.load_workbook(str(excel_path), read_only=True)
        counts: Dict[str, int] = {}

        try:
            for ws in wb.worksheets:
                col_map: Dict[str, int] = {}

                for row in ws.iter_rows(values_only=True):
                    vals = [str(v or '').strip() for v in row]
                    if not any(vals):
                        continue

                    full_upper = ' '.join(vals).upper()
                    vals_upper = [v.upper() for v in vals]

                    # Détecter ligne d'en-tête
                    if 'BORNE' in vals_upper and 'SIGNAL' in vals_upper:
                        col_map = {
                            v.upper(): i
                            for i, v in enumerate(vals)
                            if v.upper() in (
                                'BORNE', 'COULEUR', 'SIGNAL', 'JARRETIERES',
                                'TENANT', 'JAR', 'ABOUTISSANT',
                            )
                        }
                        continue

                    if not col_map:
                        continue

                    # Ignorer lignes spéciales
                    if any(kw in full_upper for kw in (
                        'NOM DU CABLE', 'NO PLAN', 'P.E.T', 'M  T  I',
                        'INDICE', 'PAGE :', 'BORNIER :',
                    )):
                        continue

                    for col_name, idx in col_map.items():
                        if idx < len(vals) and vals[idx]:
                            if self.add_value(col_name, vals[idx]):
                                counts[col_name] = counts.get(col_name, 0) + 1
        finally:
            wb.close()

        self.save()
        return counts

    # ── Validation vers le dictionnaire final ──────────────────────────

    def validate_values(
        self,
        final_dict: DataDictionary,
        col_name: Optional[str] = None,
        values: Optional[List[str]] = None,
    ) -> int:
        """
        Déplace des valeurs validées vers le dictionnaire FINAL.

        Modes :
          validate_values(final)                → valide TOUT le pending
          validate_values(final, 'SIGNAL')      → valide toute la colonne SIGNAL
          validate_values(final, 'SIGNAL', [...]) → valide les valeurs sélectionnées

        Retourne le nombre de nouvelles valeurs ajoutées au dictionnaire final.
        """
        count = 0

        if col_name is None:
            # Tout valider
            for col, bucket in list(self._data.items()):
                for v in list(bucket):
                    if final_dict.add_value(col, v):
                        count += 1
            self._data.clear()

        elif values is None:
            # Valider toute une colonne
            col = col_name.upper()
            for v in list(self._data.get(col, set())):
                if final_dict.add_value(col, v):
                    count += 1
            self._data[col] = set()

        else:
            # Valider une sélection
            col = col_name.upper()
            bucket = self._data.get(col, set())
            for v in values:
                if v in bucket:
                    if final_dict.add_value(col, v):
                        count += 1
                    bucket.discard(v)

        if count:
            final_dict.save()
        self.save()
        return count

    def reject_values(
        self,
        col_name: Optional[str] = None,
        values: Optional[List[str]] = None,
    ) -> int:
        """
        Supprime des valeurs du pending sans les valider.
        Même signature que validate_values.
        """
        count = 0
        if col_name is None:
            count = sum(len(v) for v in self._data.values())
            self._data.clear()
        elif values is None:
            col = col_name.upper()
            count = len(self._data.get(col, set()))
            self._data[col] = set()
        else:
            col = col_name.upper()
            bucket = self._data.get(col, set())
            for v in values:
                if v in bucket:
                    bucket.discard(v)
                    count += 1
        self.save()
        return count

    # ── Utilitaires ────────────────────────────────────────────────────

    def get_all(self, column: str) -> List[str]:
        return sorted(self._data.get(column.upper(), set()))

    def stats(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._data.items() if v}

    def total(self) -> int:
        return sum(len(v) for v in self._data.values())

    def __repr__(self) -> str:
        s = ', '.join(f'{k}:{len(v)}' for k, v in self._data.items())
        return f"PendingDictionary({s or 'vide'})"


# ══════════════════════════════════════════════════════════════════════
# Singletons module-level
# ══════════════════════════════════════════════════════════════════════

_global_dict: Optional[DataDictionary] = None
_global_pending: Optional[PendingDictionary] = None


def get_dictionary() -> DataDictionary:
    """Retourne l'instance globale du dictionnaire FINAL."""
    global _global_dict
    if _global_dict is None:
        _global_dict = DataDictionary()
    return _global_dict


def get_pending_dictionary() -> PendingDictionary:
    """Retourne l'instance globale du dictionnaire EN ATTENTE."""
    global _global_pending
    if _global_pending is None:
        _global_pending = PendingDictionary()
    return _global_pending
