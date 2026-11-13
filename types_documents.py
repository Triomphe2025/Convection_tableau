"""Registre des types de documents : champs optionnels en mémoire, templates.json inchangé."""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FAMILLES = ('tableau', 'plan', 'mixte', 'excel', 'journal')

_NON_ALNUM = re.compile(r'[^A-Z0-9]')


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
            format_page="",
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


# ── Détection (étape 2) ───────────────────────────────────────────────

def _normaliser(texte: str) -> str:
    # Les pieds varient (points, espaces, « N° ») : on compare lettres et chiffres seuls.
    return _NON_ALNUM.sub('', (texte or '').upper())


def _tokens_type(t: TypeDocument):
    r = t.reconnaissance
    pied = [m for m in (_normaliser(x) for x in r.mots_pied) if m]
    cart = _normaliser(r.marque_cartouche)
    cols = [c for c in (_normaliser(x) for x in r.entete_colonnes) if c]
    return pied, cart, cols


def _compte_mot(texte_upper, token) -> int:
    # Un mot de reconnaissance ne compte que s'il est entier : les espaces et points
    # qu'un scan glisse entre les lettres (« J A R », « P.E.T ») sont tolérés, mais
    # « FIL » dans PROFIL / FILERIE ne compte pas (bornes de mot alphanumériques).
    cn = _normaliser(token)
    if not cn:
        return 0
    motif = r'(?<![A-Z0-9])' + r'[^A-Z0-9]*'.join(cn) + r'(?![A-Z0-9])'
    return 1 if re.search(motif, (texte_upper or '').upper()) else 0


def _score_type(texte_upper: str, t: TypeDocument):
    pied, cart, cols = _tokens_type(t)
    n_pied = sum(1 for m in pied if _compte_mot(texte_upper, m))
    n_cart = 1 if cart and _compte_mot(texte_upper, cart) else 0
    n_col = sum(1 for c in cols if _compte_mot(texte_upper, c))
    return n_pied, n_cart, n_col


def _confiance(n_pied, n_cart, n_col, total_pied, total_col) -> float:
    # Part « famille » (c'est bien un bornier) + part « modèle » (colonnes), à parts égales.
    part_famille = (n_pied + n_cart) / (total_pied + 1) if (total_pied + 1) else 0.0
    part_modele = (n_col / total_col) if total_col else 0.0
    return 0.5 * part_famille + 0.5 * part_modele


def a_preciser(confiance, preuves) -> bool:
    """True si le résultat est incertain : « à préciser » déjà noté, ou confiance faible.

    L'interface l'utilise pour afficher le modèle le plus proche comme proposition à confirmer.
    """
    from config import Config
    if any("à préciser" in (p or "") for p in (preuves or ())):
        return True
    return confiance < Config.DETECTION_SEUIL_SUR


def _rects_bandes(x0, y0, x1, y1):
    """Bandes à lire sur un scan : en-tête (haut, colonnes) et pied (bas), pleine largeur."""
    from config import Config
    h = y1 - y0
    entete = (x0, y0, x1, y0 + h * Config.DETECTION_ENTETE_BANDE)
    pied = (x0, y1 - h * Config.DETECTION_PIED_BANDE, x1, y1)
    return [entete, pied]


def _decider(texte, types, grand_format):
    """Cœur de la détection : choisit le type « tableau » le mieux reconnu dans `texte`.

    Aucun mot bornier + grand format → plan ; aucun mot + format standard → inconnu.
    Plusieurs modèles indiscernables (mêmes colonnes) → confiance plafonnée, « à préciser » ;
    un seul modèle mais faiblement reconnu (sous le seuil sûr) → « à préciser » aussi.
    """
    from config import Config
    texte_upper = (texte or '').upper()
    tableaux = [t for t in types.values() if t.famille == "tableau"]
    scored = []
    for t in tableaux:
        n_pied, n_cart, n_col = _score_type(texte_upper, t)
        scored.append((n_pied + n_cart + n_col, n_pied, n_cart, n_col, t))

    # Plan reconnu à ses mots de cartouche, quel que soit le format (les vrais plans sont
    # souvent en A3) : au moins N mots de cartouche ET aucun en-tête de colonne bornier.
    n_col_total = sum(s[3] for s in scored)
    n_plan = sum(1 for m in Config.DETECTION_MOTS_PLAN
                 if _compte_mot(texte_upper, _normaliser(m)))
    if n_plan >= Config.DETECTION_MOTS_PLAN_MIN and n_col_total == 0:
        return (TYPE_PLAN, Config.DETECTION_CONFIANCE_PLAN_CARTOUCHE,
                [f"{n_plan} mots de cartouche de plan",
                 "aucun en-tête de colonne bornier → plan"])

    meilleur = max((s[0] for s in scored), default=0)
    if meilleur == 0:
        if grand_format:
            return (TYPE_PLAN, Config.DETECTION_CONFIANCE_PLAN_FORMAT,
                    ["aucun mot de pied bornier", "grand format → plan"])
        return None, 0.0, ["aucun mot de reconnaissance trouvé (ni pied, ni colonnes)"]

    gagnants = [s for s in scored if s[0] == meilleur]
    _, n_pied, n_cart, n_col, t = max(gagnants, key=lambda s: (s[3], s[1]))
    total_pied = len(_tokens_type(t)[0])
    total_col = len(_tokens_type(t)[2])
    conf = _confiance(n_pied, n_cart, n_col, total_pied, total_col)

    trouves = []
    if n_pied or n_cart:
        trouves.append(f"pied reconnu ({n_pied + n_cart} indice(s))")
    if n_col:
        trouves.append(f"colonnes : {n_col} sur {total_col}")
    preuves = [f"modèle le plus proche : {t.nom}"] + trouves

    if len(gagnants) > 1:
        noms = ", ".join(sorted(s[4].nom for s in gagnants))
        conf = min(conf, Config.DETECTION_CONFIANCE_EX_AEQUO_MAX)
        preuves.append(f"à préciser entre : {noms}")
    elif conf < Config.DETECTION_SEUIL_SUR:
        preuves.append(f"à préciser (confiance faible) — modèle le plus proche : {t.nom}")
    return t, conf, preuves


def _grand_format(chemin) -> Tuple[bool, float]:
    """(grand format ?, grand côté en points) d'après la 1re page du PDF."""
    from config import Config
    import fitz
    doc = fitz.open(chemin)
    try:
        r = doc[0].rect if len(doc) else None
    finally:
        doc.close()
    if r is None:
        return False, 0.0
    cote = max(r.width, r.height)
    return cote > Config.DETECTION_GRAND_FORMAT_PT, cote


class TesseractIndisponible(Exception):
    """Tesseract introuvable ou en échec (langue absente) : la détection reste « à préciser »."""


def _tesseract_texte(page) -> str:
    """En-tête (colonnes) et pied d'un scan, lus par Tesseract en basse résolution.

    Lève TesseractIndisponible si Tesseract est introuvable ou échoue (jamais propagé plus haut :
    detecter_type ne lève pas, il passe « à préciser »).
    """
    from config import Config
    if not Config.TESSERACT_TROUVE:
        raise TesseractIndisponible("Tesseract introuvable")
    import fitz
    import pytesseract
    from PIL import Image
    pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH
    r = page.rect
    echelle = Config.DETECTION_TESSERACT_DPI / 72.0
    morceaux = []
    try:
        for x0, y0, x1, y1 in _rects_bandes(r.x0, r.y0, r.x1, r.y1):
            pix = page.get_pixmap(matrix=fitz.Matrix(echelle, echelle),
                                  clip=fitz.Rect(x0, y0, x1, y1))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            morceaux.append(pytesseract.image_to_string(
                img, lang=Config.OCR_LANGUAGE, config=f"--psm {Config.DETECTION_PSM}"))
    except Exception as exc:   # langue absente, programme introuvable à l'exécution, etc.
        raise TesseractIndisponible(str(exc)) from exc
    return "\n".join(morceaux)


def _indices_echantillon(n_pages: int, n: int) -> List[int]:
    """Indices répartis sur tout le document : le pied et les colonnes sont sur les pages
    intérieures (tableaux), pas sur les premières (garde, révisions) — milieu et fin compris."""
    if n_pages <= 0:
        return []
    if n_pages <= n:
        return list(range(n_pages))
    if n <= 1:
        return [0]
    return sorted({round(i * (n_pages - 1) / (n - 1)) for i in range(n)})


def _lire_texte_pdf(chemin) -> Tuple[str, set]:
    from config import Config
    import fitz
    doc = fitz.open(chemin)
    morceaux, sources = [], set()
    try:
        for i in _indices_echantillon(len(doc), Config.DETECTION_PAGES_ECHANTILLON):
            page = doc[i]
            natif = page.get_text()
            if len(natif.strip()) >= Config.DETECTION_MIN_CARS_NATIF:
                morceaux.append(natif)
                sources.add("texte natif")
            elif "Tesseract indisponible" not in sources:
                try:
                    lu = _tesseract_texte(page)
                except TesseractIndisponible:
                    sources.add("Tesseract indisponible")
                else:
                    if lu.strip():
                        morceaux.append(lu)
                        sources.add("Tesseract (pied + en-tête)")
    finally:
        doc.close()
    return " ".join(morceaux), sources


def _lire_texte_docx(chemin) -> Tuple[str, set]:
    from docx import Document
    doc = Document(str(chemin))
    morceaux = [p.text for p in doc.paragraphs]
    for tableau in doc.tables:
        for ligne in tableau.rows:
            morceaux.extend(cell.text for cell in ligne.cells)
    return " ".join(morceaux), {"texte docx"}


def detecter_type(chemin):
    """(type, confiance, preuves) d'un fichier : extension, puis format, puis texte du pied.

    jsonl / xlsx / tif sont décidés par l'extension ; pdf et docx sont reconnus au texte.
    Fichier inconnu : (None, 0.0, preuves expliquant pourquoi).
    """
    chemin = Path(chemin)
    ext = chemin.suffix.lower()
    if ext == ".jsonl":
        return TYPE_JOURNAL, 1.0, ["extension .jsonl → journal (replay)"]
    if ext in (".xlsx", ".xlsm"):
        return TYPE_EXCEL, 1.0, [f"extension {ext} → Excel à reformater"]
    if ext in (".tif", ".tiff"):
        return TYPE_PLAN, 0.9, [f"extension {ext} → plan (image)"]
    if ext not in (".pdf", ".docx"):
        return None, 0.0, [f"extension {ext} inconnue"]

    types = registre()
    entete = []
    grand = False
    if ext == ".pdf":
        grand, cote = _grand_format(chemin)
        entete.append(f"format {cote:.0f} pt ({'grand format' if grand else 'standard'})")
        texte, sources = _lire_texte_pdf(chemin)
    else:
        texte, sources = _lire_texte_docx(chemin)
    if sources:
        entete.append("texte : " + ", ".join(sorted(sources)))

    type_, conf, preuves = _decider(texte, types, grand)
    if "Tesseract indisponible" in sources:
        preuves = preuves + ["Tesseract indisponible (langue absente ou programme "
                             "introuvable) → à préciser"]
    return type_, conf, entete + preuves
