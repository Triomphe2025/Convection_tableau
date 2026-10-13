"""
Système de modèles de tableaux pour TriosSeconverter.

Permet de définir des structures de tableaux personnalisées
(colonnes, séparateur de section, pied de page).
"""

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List
import json
import logging

logger = logging.getLogger(__name__)

# Modèles livrés avec l'appli (relus à chaque version) ; ceux de l'utilisateur sont dans
# Config.MODELES_UTILISATEUR. Dans l'exe, ce fichier est dans le dossier de l'appli.
TEMPLATES_FILE = Path(__file__).parent / "templates.json"


@dataclass
class TableTemplate:
    """Définit la structure d'un tableau à reconnaître par OCR."""

    name: str
    columns: List[str]

    # Mot-clé qui identifie une ligne de séparation (ex: "NOM DU CABLE")
    section_keyword: str = "NOM DU CABLE"

    # Pied de page
    has_footer: bool = True
    footer_left_label: str = "M  T  I"

    # Formats du pied (utilisés uniquement comme repli si render_* échoue)
    footer_row1_format: str = "P.E.T.   :     {PET}    BORNIER :    {BORNIER}"
    footer_row2_format: str = (
        "NO PLAN    :   {NO_PLAN}  |  INDICE : {INDICE}  |  PAGE :   {PAGE}"
    )

    # Mots-clés pour détecter les lignes de pied en OCR
    footer_detect_keywords: List[str] = field(
        default_factory=lambda: ['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :']
    )
    footer_mti_tokens: List[str] = field(
        default_factory=lambda: ['M', 'T', 'I']
    )

    # Champs à extraire du pied de page : {"label": "...", "key": "..."}
    # - label : mot-clé recherché dans le texte du pied (insensible à la casse)
    # - key   : nom de la clé dans le dict metadata (et placeholder {KEY} dans les formats)
    # Les 5 champs standard (PET, BORNIER, NO_PLAN, INDICE, PAGE) ont des patterns
    # affinés codés en dur ; les champs supplémentaires utilisent un pattern générique.
    footer_extract_fields: List[Dict[str, str]] = field(
        default_factory=lambda: [
            {"label": "P.E.T.",  "key": "PET"},
            {"label": "BORNIER", "key": "BORNIER"},
            {"label": "NO PLAN", "key": "NO_PLAN"},
            {"label": "INDICE",  "key": "INDICE"},
            {"label": "PAGE",    "key": "PAGE"},
        ]
    )

    # Largeurs Excel par nom de colonne (0 = largeur auto 20)
    col_widths: Dict[str, float] = field(default_factory=dict)

    description: str = ""

    def col_width(self, col_name: str) -> float:
        """Retourne la largeur Excel d'une colonne (défaut 20)."""
        return self.col_widths.get(col_name, 20.0)

    def _build_safe_meta(self, meta: Dict) -> Dict:
        """
        Construit le dict de substitution pour format_map().
        Toutes les clés de meta sont incluses (champs standards ET champs
        personnalisés comme CABLE, TYPE…). Une clé absente rend '' : aucune
        valeur n'est inventée (plus d'INDICE « 0 » par défaut).
        """
        safe: Dict = defaultdict(str)
        for k, v in meta.items():
            if k != 'PIED_BRUT':
                safe[k] = str(v or '').strip()
        return safe

    @staticmethod
    def _lignes_brutes(meta: Dict) -> List[str]:
        """(ligne 1, ligne 2) du pied lu tel quel, ou [] si aucun pied brut n'a été lu.

        L'Excel n'a que 2 lignes de pied : la dernière ligne du document va en
        ligne 2 (N° PLAN / INDICE / PAGE), les précédentes sont mises bout à bout
        en ligne 1 (CABLE puis TYPE sur deux lignes dans 223111PE011).
        """
        lignes = [str(x).strip() for x in (meta.get('PIED_BRUT') or []) if str(x).strip()]
        if not lignes:
            return []
        if len(lignes) == 1:
            return [lignes[0], '']
        return ['     '.join(lignes[:-1]), lignes[-1]]

    def render_footer_row1(self, meta: Dict) -> str:
        """Ligne 1 du pied : le pied brut lu s'il existe, sinon footer_row1_format."""
        brutes = self._lignes_brutes(meta)
        if brutes:
            return brutes[0]
        safe = self._build_safe_meta(meta)
        try:
            return self.footer_row1_format.format_map(safe)
        except Exception:
            return f"P.E.T.   :     {safe['PET']:<50}BORNIER :    {safe['BORNIER']}"

    def render_footer_row2(self, meta: Dict) -> str:
        """Ligne 2 du pied : le pied brut lu s'il existe, sinon footer_row2_format."""
        brutes = self._lignes_brutes(meta)
        if brutes:
            return brutes[1]
        safe = self._build_safe_meta(meta)
        try:
            return self.footer_row2_format.format_map(safe)
        except Exception:
            return (f"NO PLAN    :   {safe['NO_PLAN']:<37}"
                    f"|  INDICE : {safe['INDICE']:<8}"
                    f"|  PAGE :   {safe['PAGE']}")

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "TableTemplate":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ── Modèle par défaut (bornier standard) ─────────────────────────────

DEFAULT_TEMPLATE = TableTemplate(
    name="Bornier standard",
    columns=["BORNE", "COULEUR", "SIGNAL", "JARRETIERES"],
    section_keyword="NOM DU CABLE",
    has_footer=True,
    footer_left_label="M  T  I",
    footer_row1_format="P.E.T.   :     {PET:<50}BORNIER :    {BORNIER}",
    footer_row2_format="NO PLAN    :   {NO_PLAN:<37}|  INDICE : {INDICE:<8}|  PAGE :   {PAGE}",
    footer_detect_keywords=['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :'],
    footer_mti_tokens=['M', 'T', 'I'],
    col_widths={"BORNE": 8, "COULEUR": 12, "SIGNAL": 50, "JARRETIERES": 15},
    description="Tableau de bornier électrique standard",
)


REPARTITEUR_TEMPLATE = TableTemplate(
    name="Répartiteur",
    columns=["TENANT", "JAR", "ABOUTISSANT", "SIGNAL"],
    section_keyword="NOM DU CABLE",
    has_footer=True,
    footer_left_label="M  T  I",
    # "JARRETIERAGE" est un element fixe du document, pas une donnee variable
    footer_row1_format="P.E.T.   :     {PET:<50}JARRETIERAGE",
    footer_row2_format="NO PLAN    :   {NO_PLAN:<37}|  INDICE : {INDICE:<8}|  PAGE :   {PAGE}",
    footer_detect_keywords=['NO PLAN', 'P.E.T', 'INDICE', 'BORNIER :'],
    footer_mti_tokens=['M', 'T', 'I'],
    col_widths={"TENANT": 22, "JAR": 10, "ABOUTISSANT": 22, "SIGNAL": 36},
    description="Tableau répartiteur : TENANT / JAR / ABOUTISSANT / SIGNAL",
)


# ── Gestionnaire de modèles ───────────────────────────────────────────

class TemplateManager:
    """Charge, sauvegarde et liste les modèles de tableaux."""

    def __init__(self):
        self._templates: Dict[str, TableTemplate] = {}
        self._load()

    # ── Persistance ───────────────────────────────────────────────────

    @staticmethod
    def _lire(chemin: Path) -> Dict[str, TableTemplate]:
        if not chemin.exists():
            return {}
        try:
            with open(chemin, encoding='utf-8') as f:
                return {nom: TableTemplate.from_dict(td) for nom, td in json.load(f).items()}
        except Exception as e:
            logger.warning(f"Impossible de charger {chemin} : {e}")
            return {}

    def _load(self) -> None:
        """Modèles livrés (code, puis templates.json livré), puis ceux de l'utilisateur.

        Un modèle livré est toujours relu tel que livré : une nouvelle version le met à jour.
        Un modèle créé par l'utilisateur, d'un autre nom, est gardé d'une version à l'autre.
        """
        from config import Config, chemin_ressource
        self._templates = {
            "Bornier standard": DEFAULT_TEMPLATE,
            "Répartiteur":      REPARTITEUR_TEMPLATE,
        }
        livres = self._lire(chemin_ressource(TEMPLATES_FILE.name))
        livres.pop("Bornier standard", None)
        self._templates.update(livres)
        self._livres = set(self._templates)
        for nom, modele in self._lire(Path(Config.MODELES_UTILISATEUR)).items():
            if nom not in self._livres:
                self._templates[nom] = modele

    def est_livre(self, name: str) -> bool:
        """Modèle livré avec l'appli (non supprimable, remis à jour à chaque version)."""
        return name in self._livres

    def save(self) -> None:
        """Modèles de l'utilisateur dans son dossier ; les modèles livrés n'y vont pas."""
        from config import Config
        try:
            chemin = Path(Config.MODELES_UTILISATEUR)
            chemin.parent.mkdir(parents=True, exist_ok=True)
            data = {name: t.to_dict() for name, t in self._templates.items()
                    if name not in self._livres}
            with open(chemin, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Erreur sauvegarde templates : {e}")

    # ── CRUD ─────────────────────────────────────────────────────────

    def add_or_update(self, template: TableTemplate) -> None:
        self._templates[template.name] = template
        self.save()

    def delete(self, name: str) -> None:
        if name in self._livres:
            return
        self._templates.pop(name, None)
        self.save()

    def get(self, name: str) -> TableTemplate:
        return self._templates.get(name, DEFAULT_TEMPLATE)

    def names(self) -> List[str]:
        return list(self._templates.keys())

    def all(self) -> List[TableTemplate]:
        return list(self._templates.values())
