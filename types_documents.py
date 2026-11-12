"""Registre des types de documents : champs optionnels en mémoire, templates.json inchangé."""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

FAMILLES = ('tableau', 'plan', 'mixte', 'excel', 'journal')


@dataclass(frozen=True)
class Reconnaissance:
    """Indices de reconnaissance d'un type (phase 2 : detecter_type)."""
    mots_pied: Tuple[str, ...] = ()
    marque_cartouche: str = ""
    entete_colonnes: Tuple[str, ...] = ()
    format_page: str = ""


@dataclass(frozen=True)
class TypeDocument:
    """Un type de document du registre ; les champs des modèles existants ne changent pas."""
    nom: str
    famille: str
    reconnaissance: Reconnaissance = field(default_factory=Reconnaissance)
    sorties: Tuple[str, ...] = ()
    profil_lecture: str = ""
    ecran_attente: str = ""
    relecture: bool = False
    extensions: Tuple[str, ...] = ()
    modele: str = ""


# Types intégrés des familles sans modèle de tableau (comme DEFAULT_TEMPLATE vit dans template.py).
TYPE_PLAN = TypeDocument(
    nom="Plan",
    famille="plan",
    reconnaissance=Reconnaissance(format_page="grand format"),
    sorties=("dxf",),
    profil_lecture="cad",
    ecran_attente="plan",
    relecture=False,
    extensions=(".pdf", ".tif", ".tiff"),
)
TYPE_EXCEL = TypeDocument(
    nom="Excel",
    famille="excel",
    sorties=("excel",),
    profil_lecture="formatage",
    ecran_attente="excel",
    relecture=False,
    extensions=(".xlsx", ".xlsm"),
)
TYPE_JOURNAL = TypeDocument(
    nom="Journal",
    famille="journal",
    sorties=("excel",),
    profil_lecture="log-replay",
    ecran_attente="journal",
    relecture=False,
    extensions=(".jsonl",),
)
TYPES_INTEGRES = (TYPE_PLAN, TYPE_EXCEL, TYPE_JOURNAL)


def _type_depuis_modele(modele) -> TypeDocument:
    """Type « tableau » déduit d'un TableTemplate : les champs du modèle ne sont pas touchés."""
    return TypeDocument(
        nom=modele.name,
        famille="tableau",
        reconnaissance=Reconnaissance(
            mots_pied=tuple(modele.footer_detect_keywords),
            marque_cartouche=modele.footer_left_label,
            entete_colonnes=tuple(modele.columns),
            format_page="A4",
        ),
        sorties=("excel",),
        profil_lecture="claude",
        ecran_attente="tableau",
        relecture=True,
        extensions=(".pdf", ".docx"),
        modele=modele.name,
    )


def _modeles_livres() -> Dict:
    """Modèles vivants (DEFAULT + templates.json + modèles utilisateur), via TemplateManager."""
    from template import TemplateManager
    return {modele.name: modele for modele in TemplateManager().all()}


def registre(modeles: Optional[Dict] = None) -> Dict[str, TypeDocument]:
    """Registre des types : un type « tableau » par modèle + les familles intégrées."""
    if modeles is None:
        modeles = _modeles_livres()
    types = {modele.name: _type_depuis_modele(modele) for modele in modeles.values()}
    for integre in TYPES_INTEGRES:
        types[integre.nom] = integre
    return types


def _meme_reconnaissance(a: Reconnaissance, b: Reconnaissance) -> bool:
    # Mêmes colonnes, mêmes mots de pied et même cartouche = reconnaissance indiscernable.
    return (a.entete_colonnes == b.entete_colonnes
            and a.mots_pied == b.mots_pied
            and a.marque_cartouche == b.marque_cartouche)


def doublons(types: Dict[str, TypeDocument]) -> List[Tuple[str, str]]:
    """Paires de types « tableau » à la reconnaissance identique — signalés, jamais supprimés."""
    tableaux = [t for t in types.values() if t.famille == "tableau"]
    paires = []
    for i in range(len(tableaux)):
        for j in range(i + 1, len(tableaux)):
            if _meme_reconnaissance(tableaux[i].reconnaissance, tableaux[j].reconnaissance):
                paires.append((tableaux[i].nom, tableaux[j].nom))
    return paires
