"""
Test doré du thermomètre : des fautes connues, injectées dans une copie de la
vérité de l'extrait 223111PE011, doivent toutes être retrouvées, au bon endroit,
et rien d'autre.

Graine fixe (GRAINE) ; la vérité sur disque n'est jamais modifiée (copie en
mémoire). Fautes : 10 valeurs déplacées dans la colonne voisine de la même ligne,
10 mots supprimés dans des cellules, 5 lignes supprimées, 3 lignes dupliquées,
2 paires de lignes inversées. Les fautes sont posées sur des lignes distantes d'au
moins deux lignes pour qu'aucune n'en masque une autre.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_mesure_thermometre.py -v
"""
import copy
import random
import unittest
from pathlib import Path

from mesure_precision import (
    CONTENU_DIFFERENT, GLISSEMENT, MANQUANT, _signature_ligne, mesurer,
)
from mesurer_precision import lire_verite_excel

VERITE = Path(__file__).parent / 'fixtures' / '223111PE011_extrait_verite.xlsx'
GRAINE = 20261002


def _injecter(pages, graine):
    """Copie fautive de la vérité et liste des fautes attendues, à leur place."""
    rng = random.Random(graine)
    conv = copy.deepcopy(pages)
    lignes = [(p, i) for p, page in enumerate(pages) for i in range(len(page['rows']))]
    rng.shuffle(lignes)
    prises = set()

    def libre(p, i, largeur=1):
        return all((p, k) not in prises for k in range(i - 2, i + largeur + 2))

    def prendre(n, filtre, largeur=1):
        choix = []
        for p, i in lignes:
            if len(choix) == n:
                break
            if i + largeur <= len(pages[p]['rows']) and libre(p, i, largeur) and filtre(p, i):
                prises.update((p, i + k) for k in range(largeur))
                choix.append((p, i))
        assert len(choix) == n, f"pas assez de lignes pour {n} fautes"
        return choix

    attendu = {'glissements': [], 'mots': [], 'supprimees': [], 'dupliquees': [],
               'inversees': []}
    ncol = len(pages[0]['rows'][0]['cells'])

    # Valeur entière déplacée vers la colonne voisine (vers la gauche en dernière colonne).
    for p, i in prendre(10, lambda p, i: any(pages[p]['rows'][i]['cells'])):
        cellules = conv[p]['rows'][i]['cells']
        k = rng.choice([k for k, c in enumerate(cellules) if c.strip()])
        voisine = k + 1 if k + 1 < ncol else k - 1
        valeur, cellules[k] = cellules[k], ''
        cellules[voisine] = ' '.join(filter(None, [cellules[voisine], valeur]))
        attendu['glissements'].append((p, i, k, voisine))

    # Un mot (2 caractères au moins) retiré d'une cellule qui en compte plusieurs.
    def a_plusieurs_mots(p, i):
        return any(len([m for m in c.split() if len(m) >= 2]) >= 2 and len(c.split()) >= 2
                   for c in pages[p]['rows'][i]['cells'])
    for p, i in prendre(10, a_plusieurs_mots):
        cellules = conv[p]['rows'][i]['cells']
        k = rng.choice([k for k, c in enumerate(cellules)
                        if len(c.split()) >= 2 and any(len(m) >= 2 for m in c.split())])
        mots = cellules[k].split()
        mot = rng.choice([m for m in mots if len(m) >= 2])
        mots.remove(mot)
        cellules[k] = ' '.join(mots)
        attendu['mots'].append((p, i, k, mot))

    supprimees = prendre(5, lambda p, i: True)
    dupliquees = prendre(3, lambda p, i: True)
    inversees = prendre(2, lambda p, i: True, largeur=2)
    for p, page in enumerate(conv):
        nouvelles = []
        lignes_page = page['rows']
        i = 0
        while i < len(lignes_page):
            if (p, i) in supprimees:
                attendu['supprimees'].append((p, i))
            elif (p, i) in inversees:
                nouvelles += [lignes_page[i + 1], lignes_page[i]]
                attendu['inversees'].append((p, i))
                i += 2
                continue
            elif (p, i) in dupliquees:
                nouvelles += [lignes_page[i], copy.deepcopy(lignes_page[i])]
                attendu['dupliquees'].append((p, i, len(nouvelles) - 1))
            else:
                nouvelles.append(lignes_page[i])
            i += 1
        page['rows'] = nouvelles
    return conv, attendu


class TestThermometre(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.verite, cls.colonnes = lire_verite_excel(VERITE)
        # Le thermomètre éprouve les fautes de CONTENU : les positions saisies à la main
        # (feuille Verite_positions, page 52) sont retirées de la référence, sinon les
        # espacements d'origine absents de la copie seraient comptés comme des fautes.
        for page in cls.verite:
            for ligne in page['rows']:
                ligne.pop('positions', None)
        avant = copy.deepcopy(cls.verite)
        cls.fautive, cls.attendu = _injecter(cls.verite, GRAINE)
        assert cls.verite == avant, "la vérité ne doit pas être modifiée"
        cls.rapport = mesurer(cls.verite, cls.fautive, cls.colonnes)
        cls.par_cellule = {(e.page_ref, e.ligne_ref, e.colonne): e
                           for e in cls.rapport.ecarts_cellules}

    def test_nombre_de_fautes_injectees(self):
        self.assertEqual({k: len(v) for k, v in self.attendu.items()},
                         {'glissements': 10, 'mots': 10, 'supprimees': 5, 'dupliquees': 3,
                          'inversees': 2})

    def test_pages_appariees_une_a_une(self):
        self.assertEqual(sorted(self.rapport.pages_appariees),
                         [(p, p) for p in range(len(self.verite)) if self.verite[p]['rows']
                          or self.verite[p].get('pied_texte')])

    def test_glissements_de_colonne_retrouves(self):
        for p, i, k, voisine in self.attendu['glissements']:
            for col in (k, voisine):
                e = self.par_cellule.get((p, i, self.colonnes[col]))
                self.assertIsNotNone(e, (p, i, self.colonnes[col]))
                self.assertEqual(e.classe, GLISSEMENT, e)

    def test_mots_supprimes_retrouves_dans_leur_cellule(self):
        for p, i, k, mot in self.attendu['mots']:
            e = self.par_cellule.get((p, i, self.colonnes[k]))
            self.assertIsNotNone(e, (p, i, self.colonnes[k], mot))
            self.assertIn(e.classe, (CONTENU_DIFFERENT, MANQUANT), e)
            self.assertIn(mot, e.valeur_ref.split())
            self.assertEqual(e.valeur_conv.split().count(mot), e.valeur_ref.split().count(mot) - 1)

    def test_lignes_supprimees_retrouvees(self):
        manquantes = {(o.page, o.ligne) for o in self.rapport.lignes_orphelines
                      if o.cote == 'MANQUANTE'}
        self.assertEqual(manquantes, set(self.attendu['supprimees']))

    def test_lignes_dupliquees_retrouvees(self):
        en_trop = {(o.page, o.contenu) for o in self.rapport.lignes_orphelines
                   if o.cote == 'EN_TROP'}
        self.assertEqual(en_trop, {(p, _signature_ligne(self.verite[p]['rows'][i]))
                                   for p, i, _ in self.attendu['dupliquees']})
        for o in self.rapport.lignes_orphelines:
            if o.cote == 'EN_TROP':
                place = next(c for p, _, c in self.attendu['dupliquees']
                             if p == o.page and _signature_ligne(self.verite[p]['rows'][_])
                             == o.contenu)
                self.assertIn(o.ligne, (place - 1, place))

    def test_paires_inversees_retrouvees(self):
        deplacees = {(d.page_ref, d.ligne_ref) for d in self.rapport.lignes_deplacees}
        self.assertEqual(len(deplacees), 2)
        for p, i in self.attendu['inversees']:
            self.assertTrue({(p, i), (p, i + 1)} & deplacees, (p, i))

    def test_aucun_autre_ecart(self):
        attendues = ({(p, i, self.colonnes[c]) for p, i, k, v in self.attendu['glissements']
                      for c in (k, v)}
                     | {(p, i, self.colonnes[k]) for p, i, k, _ in self.attendu['mots']})
        self.assertEqual(set(self.par_cellule), attendues)
        self.assertEqual(len(self.rapport.lignes_orphelines), 5 + 3)
        self.assertEqual(self.rapport.ecarts_pieds, [])
        self.assertEqual(self.rapport.ecarts_positions, [])


if __name__ == '__main__':
    unittest.main()
