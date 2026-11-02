"""
Polices sans table Unicode dans un PDF vectoriel : lecture sans OCR distant.

Certains PDF embarquent une police en sous-ensemble sans table ToUnicode (223111PE052 :
en-têtes et pieds en Comic Sans). La page s'affiche bien, mais sa couche texte rend des
numéros de glyphes (\\x01, \\x02…) : la grille ne trouve plus l'en-tête « BORNE COULEUR
SIGNAL JARRETIERES » et la page était écartée comme une page de garde.

Le dessin d'une lettre, lui, est le même partout où la police est utilisée. Chaque glyphe
illisible est donc reconnu par son dessin (points des contours de la police TrueType) :
1. d'abord dans le texte lisible du même document : une page où la même police a sa
   table Unicode (PE052 p. 12 et 25) donne la lettre exacte de chaque dessin ;
2. sinon par Tesseract, en local (aucun appel API, aucun jeton) : chaque morceau de
   texte illisible est lu, aligné caractère par caractère sur ses glyphes, et chaque
   dessin prend la lettre la plus souvent lue sur tout le document (« 2 » lu « e » une
   fois mais « 2 » dans chaque « 223111 » reste un « 2 »).
Une lettre lue une seule fois est relue autrement (autre résolution, autre découpage) ;
si elle reste sans 2e lecture concordante, la page le signale dans A VERIFIER. Une lettre
introuvable devient « ? » (signalée aussi), jamais une lettre inventée.
Le corps du tableau, lui, reste lu tel quel dans la couche texte. Les pages sans police
illisible (cas général) ne passent pas par ce module.
"""

import hashlib
import logging
import struct
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Résolution du rendu d'un morceau de texte relu par Tesseract (polices de pied ~11 pt).
_DPI_TESSERACT = 400
# Morceaux relus au plus par document (garde-fou de durée : ~0,1 s chacun).
_MAX_MORCEAUX = 300
# Lectures concordantes à partir desquelles un dessin n'a plus besoin d'être relu.
_VOTES_SUFFISANTS = 3

# Table de décodage d'un caractère : (lettre, sûre). Lettre « ? » si rien ne la donne.
Lettre = Tuple[str, bool]


def illisible(code: int) -> bool:
    """Caractère rendu sans équivalent Unicode : numéro de glyphe brut ou U+FFFD.

    get_texttrace rend U+FFFD ; get_text rend le code brut de la police (\\x01…),
    y compris 9, 10 et 13 qui ne sont alors pas des blancs : voir code_brut.
    """
    return code == 0xFFFD or (code < 0x20 and code not in (9, 10, 13))


def code_brut(code: int) -> bool:
    """Dans un span qui a des caractères illisibles, tout code de contrôle en est un."""
    return code == 0xFFFD or code < 0x20


def position_caractere(police: str, origine) -> Tuple[str, float, float]:
    """Clé d'un caractère commune à get_text et get_texttrace (même origine)."""
    return police, round(origine[0], 1), round(origine[1], 1)


# -- Empreinte du dessin des glyphes (TrueType) ------------------------------------

def _tables(buf: bytes) -> Optional[Dict[str, Tuple[int, int]]]:
    """Répertoire des tables d'une police TrueType ; None pour tout autre format."""
    if len(buf) < 12 or buf[:4] not in (b'\x00\x01\x00\x00', b'true'):
        return None
    n = struct.unpack('>H', buf[4:6])[0]
    if len(buf) < 12 + 16 * n:
        return None
    tables = {}
    for i in range(n):
        tag, _, debut, longueur = struct.unpack('>4sIII', buf[12 + 16 * i: 28 + 16 * i])
        tables[tag.decode('latin-1')] = (debut, longueur)
    return tables


def _contours(data: bytes):
    """Points (x, y, sur la courbe) et fins de contours d'un glyphe TrueType simple."""
    nc = struct.unpack('>h', data[:2])[0]
    fins = struct.unpack(f'>{nc}H', data[10:10 + 2 * nc])
    npts = fins[-1] + 1 if nc else 0
    i = 10 + 2 * nc
    i += 2 + struct.unpack('>H', data[i:i + 2])[0]          # instructions ignorées
    drapeaux: List[int] = []
    while len(drapeaux) < npts:
        f = data[i]
        i += 1
        drapeaux.append(f)
        if f & 8:                                              # drapeau répété
            drapeaux += [f] * data[i]
            i += 1

    def lire(court: int, meme: int) -> List[int]:
        nonlocal i
        v, valeurs = 0, []
        for f in drapeaux:
            if f & court:
                d = data[i]
                i += 1
                v += d if f & meme else -d
            elif not f & meme:
                v += struct.unpack('>h', data[i:i + 2])[0]
                i += 2
            valeurs.append(v)
        return valeurs

    xs = lire(2, 16)
    ys = lire(4, 32)
    return tuple(zip(xs, ys, (f & 1 for f in drapeaux))), fins


def empreintes_glyphes(buf: bytes) -> Optional[Dict[int, Optional[str]]]:
    """{n° de glyphe: empreinte du dessin} d'une police TrueType ; '' = glyphe vide.

    L'empreinte porte sur le dessin décodé (points, courbes, contours), pas sur les
    octets : deux sous-ensembles de la même police encodent les mêmes points
    différemment. None (glyphe) : composé ou illisible ; None (police) : pas TrueType.
    """
    t = _tables(buf)
    if not t or not all(k in t for k in ('head', 'loca', 'glyf', 'maxp')):
        return None
    try:
        tete = t['head'][0]
        longs = struct.unpack('>h', buf[tete + 50: tete + 52])[0] == 1
        nb = struct.unpack('>H', buf[t['maxp'][0] + 4: t['maxp'][0] + 6])[0]
        loca = t['loca'][0]
        if longs:
            pos = struct.unpack(f'>{nb + 1}I', buf[loca: loca + 4 * (nb + 1)])
        else:
            pos = [2 * v for v in struct.unpack(f'>{nb + 1}H', buf[loca: loca + 2 * (nb + 1)])]
    except struct.error:
        return None
    glyf = t['glyf'][0]
    sortie: Dict[int, Optional[str]] = {}
    for g in range(nb):
        data = buf[glyf + pos[g]: glyf + pos[g + 1]]
        if len(data) < 10:
            sortie[g] = ''
            continue
        try:
            if struct.unpack('>h', data[:2])[0] < 0:
                sortie[g] = None
                continue
            sortie[g] = hashlib.sha1(repr(_contours(data)).encode()).hexdigest()[:16]
        except (struct.error, IndexError):
            sortie[g] = None
    return sortie


# -- Décodage d'un document ----------------------------------------------------------

class DecodageDocument:
    """Lettre de chaque caractère illisible d'un document, trouvée une fois pour toutes."""

    # Faux : sans le texte lisible du document comme référence (essais : Tesseract seul).
    REFERENCE_INTERNE = True

    def __init__(self, doc):
        self._doc = doc
        self._empreintes: Dict[int, Optional[Dict]] = {}
        self.tesseract_absent = False
        self.morceaux_relus = 0
        # cle de dessin -> lettre ; cle = empreinte TrueType, sinon « xref:glyphe »
        self._lettres: Dict[str, Lettre] = {}
        # (xref, n° de glyphe) -> cle de dessin
        self._cle: Dict[Tuple[int, int], str] = {}
        self._construire()

    # Empreintes d'une police du document (cache par xref).
    def _empreintes_police(self, xref: int) -> Dict:
        if xref not in self._empreintes:
            try:
                buf = self._doc.extract_font(xref)[3]
                self._empreintes[xref] = empreintes_glyphes(buf) if buf else None
            except Exception:                              # police non extractible
                self._empreintes[xref] = None
        return self._empreintes[xref] or {}

    @staticmethod
    def _polices_page(page) -> Dict[str, int]:
        """Nom de police (sans le préfixe de sous-ensemble) -> xref ; noms en double écartés."""
        vus: Dict[str, List[int]] = defaultdict(list)
        for police in page.get_fonts():
            vus[police[3].split('+')[-1]].append(police[0])
        return {nom: xrefs[0] for nom, xrefs in vus.items() if len(set(xrefs)) == 1}

    def _construire(self) -> None:
        reference: Dict[str, Counter] = defaultdict(Counter)   # dessin -> lettres lisibles
        morceaux = []                                           # textes illisibles à relire
        for page in self._doc:
            polices = None
            glyphes_page = []                       # glyphes illisibles non vides de la page
            for trace in page.get_texttrace():
                caracteres = trace.get('chars', ())
                if not caracteres:
                    continue
                if polices is None:
                    polices = self._polices_page(page)
                xref = polices.get(trace.get('font', ''))
                if xref is None:
                    continue                    # police introuvable ou nom ambigu sur la page
                empreintes = self._empreintes_police(xref)
                for code, glyphe, origine, boite in caracteres:
                    dessin = empreintes.get(glyphe)
                    if not illisible(code):
                        if code > 32 and dessin and self.REFERENCE_INTERNE:
                            reference[dessin][chr(code)] += 1
                        continue
                    cle = (dessin if dessin is not None else f'{xref}:{glyphe}')
                    self._cle[(xref, glyphe)] = cle
                    if cle != '':
                        glyphes_page.append((origine[1], boite, cle))
            morceaux += _morceaux(page.number, glyphes_page)
        if not self._cle:
            return

        for cle in set(self._cle.values()):
            if cle == '':
                self._lettres[cle] = (' ', True)
            elif cle in reference and len(reference[cle]) == 1:
                self._lettres[cle] = (next(iter(reference[cle])), True)

        inconnues = {c for c in self._cle.values() if c not in self._lettres}
        if inconnues:
            self._relire_tesseract(morceaux, inconnues)

    def _relire_tesseract(self, morceaux, inconnues) -> None:
        """Lettres des dessins inconnus, par lecture Tesseract locale des morceaux de ligne.

        1er passage (400 dpi, une ligne) jusqu'à _VOTES_SUFFISANTS lectures concordantes
        par dessin ; puis les dessins lus une seule fois sont relus autrement (300 dpi,
        un mot) : deux lectures indépendantes qui concordent rendent la lettre sûre.
        """
        from config import Config
        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            self.tesseract_absent = True
            return
        if not Config.TESSERACT_TROUVE:
            self.tesseract_absent = True
            return
        import fitz
        pytesseract.pytesseract.tesseract_cmd = Config.TESSERACT_PATH
        langue = getattr(Config, 'OCR_LANGUAGE', 'eng') or 'eng'
        votes: Dict[str, Counter] = defaultdict(Counter)

        def lire(morceau, dpi: int, psm: int) -> Optional[str]:
            page = self._doc[morceau['page']]
            zone = fitz.Rect(morceau['boite']) + (-2, -2, 2, 2)
            pix = page.get_pixmap(dpi=dpi, clip=zone, colorspace=fitz.csGRAY)
            image = Image.frombytes('L', (pix.width, pix.height), pix.samples)
            try:
                return pytesseract.image_to_string(image, lang=langue, config=f'--psm {psm}')
            except pytesseract.TesseractError:            # langue absente : défaut
                return pytesseract.image_to_string(image, config=f'--psm {psm}')

        def voter(morceau, lu: str) -> None:
            cles = morceau['cles']
            lettres = [c for c in lu if not c.isspace()]
            if len(lettres) != len(cles):
                return                                     # alignement impossible
            # Les lettres déjà connues doivent concorder : sinon la lecture est décalée.
            connues = [(self._lettres[c][0], l) for c, l in zip(cles, lettres)
                       if c in self._lettres]
            if connues and sum(a.upper() == b.upper() for a, b in connues) < 0.7 * len(connues):
                return
            for cle, lettre in zip(cles, lettres):
                if cle in inconnues:
                    votes[cle][lettre] += 1

        def total(cle) -> int:
            compte = votes.get(cle)
            return compte.most_common(1)[0][1] if compte else 0

        passages = [(_DPI_TESSERACT, 7, lambda c: c in inconnues and total(c) < _VOTES_SUFFISANTS),
                    (300, 8, lambda c: c in inconnues and total(c) == 1)]
        try:
            for dpi, psm, a_relire in passages:
                for morceau in morceaux:
                    if self.morceaux_relus >= _MAX_MORCEAUX:
                        break
                    if any(a_relire(c) for c in morceau['cles']):
                        lu = lire(morceau, dpi, psm)
                        self.morceaux_relus += 1
                        voter(morceau, lu or '')
        except Exception as exc:                           # Tesseract absent ou en échec
            logger.warning("Relecture Tesseract impossible : %s", exc)
            self.tesseract_absent = True

        for cle, compte in votes.items():
            if not compte:
                continue
            (lettre, n), *autres = compte.most_common()
            second = autres[0][1] if autres else 0
            self._lettres[cle] = (lettre, n >= 2 and n > second)

    def table_page(self, page) -> Dict[Tuple[str, float, float], Lettre]:
        """{(nom de police, x, y de l'origine): (lettre, sûre)} des caractères illisibles.

        Clé par position : get_text ne donne pas le n° de glyphe, get_texttrace si, et
        les deux placent chaque caractère à la même origine.
        """
        if not self._cle:
            return {}
        polices = self._polices_page(page)
        table = {}
        for trace in page.get_texttrace():
            nom = trace.get('font', '')
            xref = polices.get(nom)
            if xref is None:
                continue
            for code, glyphe, origine, _boite in trace.get('chars', ()):
                if illisible(code):
                    cle = self._cle.get((xref, glyphe))
                    table[position_caractere(nom, origine)] = self._lettres.get(cle, ('?', False))
        return table


def _morceaux(numero: int, glyphes) -> List[Dict]:
    """Glyphes illisibles d'une page regroupés en morceaux de ligne à relire.

    Un morceau : glyphes d'une même ligne sans grand vide entre eux (un blanc au plus,
    soit moins d'une demi-hauteur de texte). Deux champs du pied, et les traits du
    tableau entre eux, restent ainsi hors de l'image : Tesseract y lirait des « | ».
    """
    lignes: List[List] = []
    for g in sorted(glyphes, key=lambda g: (g[0], g[1][0])):
        if lignes and abs(g[0] - lignes[-1][0][0]) <= 2:
            lignes[-1].append(g)
        else:
            lignes.append([g])
    morceaux = []
    for ligne in lignes:
        morceau = None
        for _y, boite, cle in sorted(ligne, key=lambda g: g[1][0]):
            hauteur = boite[3] - boite[1]
            if morceau is None or boite[0] - morceau['boite'][2] > max(0.5 * hauteur, 2):
                morceau = {'page': numero, 'cles': [], 'boite': list(boite)}
                morceaux.append(morceau)
            morceau['cles'].append(cle)
            b = morceau['boite']
            morceau['boite'] = [min(b[0], boite[0]), min(b[1], boite[1]),
                                max(b[2], boite[2]), max(b[3], boite[3])]
    return morceaux


# Repli si le document n'accepte pas d'attribut : (document, décodage), le document gardé
# en référence pour que son id ne soit pas réattribué à un autre PDF tant qu'il est en cache.
_CACHE: List[Tuple[object, DecodageDocument]] = []


def decodage_document(doc) -> DecodageDocument:
    """Décodage du document, calculé à la 1re page qui en a besoin puis gardé avec lui."""
    decodage = getattr(doc, '_decodage_polices_illisibles', None)
    if decodage is not None:
        return decodage
    for document, deja in _CACHE:
        if document is doc:
            return deja
    decodage = DecodageDocument(doc)
    try:
        doc._decodage_polices_illisibles = decodage
    except AttributeError:
        _CACHE.append((doc, decodage))
        del _CACHE[:-4]
    return decodage
