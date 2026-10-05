"""
Relecture indépendante d'un scan pour la vérification de conversion.

Lecture de référence, distincte du moteur de conversion (ocr_processor) : une
lecture qui partage les défauts du moteur ne peut pas les contredire. Démarche
reprise de outils_reference/pdf_table_compare.py :
  rendu à Config.VERIF_RELECTURE_DPI → Tesseract psm VERIF_RELECTURE_PSM (TSV,
  confiance par mot) → colonnes calées sur les traits verticaux du cadre (repli :
  libellés de l'en-tête) → lignes par proximité verticale → seules les lignes dont
  la clé a la forme VERIF_MOTIF_CLE sont des données.
Produit le format pivot attendu par verificateur.verifier().
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from config import Config

# (x0, y0, x1, y1, texte, confiance)
Mot = Tuple[int, int, int, int, str, int]


def normaliser_cle(texte: str) -> str:
    """Clé de ligne comparable au motif : sans accents, ponctuation parasite ni espaces."""
    t = unicodedata.normalize('NFKD', texte or '')
    t = ''.join(c for c in t if not unicodedata.combining(c)).upper()
    return re.sub(r'[^A-Z0-9]', '', t)


def mots_tesseract(image, psm: Optional[str] = None) -> List[Mot]:
    """Mots lus par Tesseract (psm VERIF_RELECTURE_PSM par défaut) avec boîte et confiance."""
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH
    psm = Config.VERIF_RELECTURE_PSM if psm is None else psm
    data = pytesseract.image_to_data(
        image, lang=Config.OCR_LANGUAGE, config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT,
    )
    mots = []
    for i, texte in enumerate(data['text']):
        texte = (texte or '').strip()
        try:
            conf = int(float(data['conf'][i]))
        except (TypeError, ValueError):
            continue
        if texte and conf >= 0:
            x, y, w, h = (data[k][i] for k in ('left', 'top', 'width', 'height'))
            mots.append((x, y, x + w, y + h, texte, conf))
    return mots


def traits_verticaux(gris, part_min: float = 0.35) -> Optional[List[float]]:
    """Abscisses des traits verticaux du cadre (morphologie), ou None."""
    import cv2
    import numpy as np
    hauteur = gris.shape[0]
    noir = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    noyau = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, int(hauteur * part_min))))
    colonnes = np.where(cv2.morphologyEx(noir, cv2.MORPH_OPEN, noyau).sum(axis=0) > 0)[0]
    if len(colonnes) == 0:
        return None
    groupes, courant = [], [colonnes[0]]
    for c in colonnes[1:]:
        if c - courant[-1] <= 5:
            courant.append(c)
        else:
            groupes.append(float(np.mean(courant)))
            courant = [c]
    groupes.append(float(np.mean(courant)))
    return groupes if len(groupes) >= 2 else None


def bornes_entete(mots: List[Mot], colonnes: List[str]) -> Optional[List[float]]:
    """Frontières à mi-chemin des libellés de l'en-tête, ou None s'il en manque un."""
    centres = {}
    for x0, _, x1, _, texte, _ in mots:
        for col in colonnes:
            if normaliser_cle(texte) == normaliser_cle(col) and col not in centres:
                centres[col] = (x0 + x1) / 2
    if len(centres) < len(colonnes):
        return None
    c = [centres[col] for col in colonnes]
    return [0.0] + [(c[i] + c[i + 1]) / 2 for i in range(len(c) - 1)] + [1e9]


def bornes_colonnes(traits: Optional[List[float]], mots: List[Mot],
                    colonnes: List[str]) -> Optional[List[float]]:
    """Traits du cadre s'il y en a assez (bord + séparateurs), sinon en-tête lue."""
    n = len(colonnes)
    if traits and len(traits) >= n + 1:
        interieurs = traits[1:-1][:n - 1]
        if len(interieurs) == n - 1:
            return [traits[0]] + interieurs + [traits[-1]]
    return bornes_entete(mots, colonnes)


def grouper_lignes(mots: List[Mot], tolerance: float) -> List[List[Mot]]:
    """Mots regroupés en lignes par le centre vertical (moyenne glissante)."""
    lignes, courante, ref = [], [], None
    for m in sorted(mots, key=lambda m: (m[1], m[0])):
        cy = (m[1] + m[3]) / 2
        if ref is None or abs(cy - ref) <= tolerance:
            courante.append(m)
            ref = cy if ref is None else (ref + cy) / 2
        else:
            lignes.append(courante)
            courante, ref = [m], cy
    if courante:
        lignes.append(courante)
    return lignes


def ligne_en_cellules(ligne: List[Mot], bornes: List[float], n: int) -> Dict:
    """Mots rangés par le centre dans les colonnes ; confiance = moyenne des mots."""
    textes: List[List[str]] = [[] for _ in range(n)]
    confs: List[List[int]] = [[] for _ in range(n)]
    for x0, _, x1, _, texte, conf in sorted(ligne, key=lambda m: m[0]):
        cx = (x0 + x1) / 2
        for k in range(n):
            if bornes[k] <= cx < bornes[k + 1]:
                textes[k].append(texte)
                confs[k].append(conf)
                break
    return {
        'type': 'data',
        'cells': [' '.join(t) for t in textes],
        'confidence': [round(sum(c) / len(c)) if c else 100 for c in confs],
    }


def est_entete(ligne: Dict, colonnes: List[str]) -> bool:
    """Au moins deux cellules portent un libellé de colonne (borne de l'en-tête non lue)."""
    libelles = {normaliser_cle(c) for c in colonnes}
    return sum(1 for c in ligne['cells'] if normaliser_cle(c) in libelles) >= 2


def est_ligne_de_donnees(ligne: Dict) -> bool:
    """Clé de forme VERIF_MOTIF_CLE, ou clé illisible sur une ligne de tableau.

    En-tête (« BORNE »), section (« NOM DU ») et pied (« MATRA ») ont une clé
    qui n'a pas la forme d'une borne ; une ligne sans clé lue n'est écartée que
    si elle porte un libellé de pied ou presque aucun caractère.
    """
    cle = normaliser_cle(ligne['cells'][0])
    if cle:
        pliee = cle[0] + ''.join(Config.VERIF_REPLI_CLE.get(c, c) for c in cle[1:])
        return bool(re.match(Config.VERIF_MOTIF_CLE, pliee))
    reste = ' '.join(ligne['cells'][1:]).upper()
    if any(mot in reste for mot in Config.VERIF_MOTS_PIED):
        return False
    return len(normaliser_cle(reste)) >= Config.VERIF_LIGNE_BRUIT_MIN_CARS


def relire_image(image, colonnes: List[str]) -> Dict:
    """Une page scannée (image PIL) → résultat pivot ; success False sans tableau."""
    import numpy as np
    gris = np.array(image.convert('L'))
    mots = mots_tesseract(image)
    bornes = bornes_colonnes(traits_verticaux(gris), mots, colonnes) if mots else None
    if bornes is None:
        return {'success': False, 'headers': colonnes, 'rows': [], 'metadata': {}}
    lignes = [ligne_en_cellules(lg, bornes, len(colonnes))
              for lg in grouper_lignes(mots, Config.VERIF_RELECTURE_TOL_LIGNE)]
    rows = [lg for lg in lignes if est_ligne_de_donnees(lg) and not est_entete(lg, colonnes)]
    return {'success': bool(rows), 'headers': colonnes, 'rows': rows, 'metadata': {},
            'detection_method': 'relecture-scan'}


def relire_pdf(chemin, colonnes: List[str], annule=None) -> List[Dict]:
    """Chaque page du PDF relue comme un scan, quelle que soit sa couche texte."""
    import fitz
    from PIL import Image
    resultats = []
    with fitz.open(str(chemin)) as doc:
        for i, page in enumerate(doc):
            if annule and annule():
                break
            pix = page.get_pixmap(dpi=Config.VERIF_RELECTURE_DPI)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            resultat = relire_image(image, colonnes)
            resultat.update(page_num=i + 1, image_path=f'page_{i + 1}')
            resultats.append(resultat)
    return resultats
