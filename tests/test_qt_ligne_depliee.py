"""Étape 4b — ligne dépliée : accordéon, profils + recalcul, mode lot, réordonnancement."""
import pytest

pytest.importorskip("PySide6")

from trios_qt import analyse  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.modele_fichiers import LanceurAnalyse  # noqa: E402
from trios_qt.page_convertir import PageConvertir  # noqa: E402


class _Type:
    def __init__(self, nom="Bornier standard", famille="tableau", modele="Bornier standard"):
        self.nom = nom
        self.famille = famille
        self.modele = modele
        self.sorties = ("excel",)


_COUT = {None: 0.0, "claude-sonnet-5-5": 0.12, "claude-opus-5-5": 0.20}


def _estimer(chemin, type=None, profil=None, lot=False, modele=None, dossier_sortie=None):
    cout = _COUT.get(modele, 0.0)
    if lot:
        cout *= 0.5
    return {'cout_usd': cout, 'cache_connu': True, 'duree': {'texte': '~ 5 min'},
            'pages': {'total': 141, 'scan': 141, 'vectoriel': 0}, 'pages_payantes': 141}


def _res(etat=analyse.PRET, type_=None, payantes=141):
    if type_ is None and etat == analyse.PRET:
        type_ = _Type()
    return analyse.ResultatAnalyse(
        etat=etat, type=type_, preuves=["preuve"],
        estimation={'cout_usd': 0.12, 'cache_connu': True, 'duree': {'texte': '~ 5 min'},
                    'pages': {'total': 141, 'scan': 141, 'vectoriel': 0},
                    'pages_payantes': payantes})


def _page(qtbot, resultats):
    creer_application([])
    suite = iter(resultats)
    lanceur = LanceurAnalyse(analyser=lambda chemin, **kw: next(suite))
    p = PageConvertir(lanceur=lanceur, estimer_fn=_estimer)
    qtbot.addWidget(p)
    return p


def _ajouter(p, qtbot, chemins):
    with qtbot.waitSignal(p.lanceur.fini, timeout=2000):
        p.ajouter_sources(chemins[:1])
    for c in chemins[1:]:
        with qtbot.waitSignal(p.lanceur.fini, timeout=2000):
            p.ajouter_sources([c])


class TestLigneDepliee:

    def test_selection_deplie_une_seule_ligne(self, qtbot):
        p = _page(qtbot, [_res(), _res()])
        _ajouter(p, qtbot, [r"C:\a.pdf", r"C:\b.pdf"])
        p.selectionner(p.modele.ligne(0).ident)
        # Fenêtre non affichée (offscreen) : isVisibleTo ignore l'état « montré » de l'ancêtre.
        assert p.widget_ligne(0)._corps_deplie.isVisibleTo(p.widget_ligne(0))
        assert not p.widget_ligne(1)._corps_deplie.isVisibleTo(p.widget_ligne(1))

    def test_tableau_deplie_montre_trois_profils(self, qtbot):
        p = _page(qtbot, [_res()])
        _ajouter(p, qtbot, [r"C:\a.pdf"])
        p.selectionner(p.modele.ligne(0).ident)
        assert len(p.widget_ligne(0).profil_cartes) == 3

    def test_choisir_profil_met_a_jour_l_estimation(self, qtbot):
        p = _page(qtbot, [_res()])
        _ajouter(p, qtbot, [r"C:\a.pdf"])
        ident = p.modele.ligne(0).ident
        p.selectionner(ident)
        p.choisir_profil(ident, "difficile")
        # Opus 5.5, lot auto (141 pages) → 0,20 × 0,5 = 0,10.
        assert p.modele.ligne(0).resultat.estimation['cout_usd'] == pytest.approx(0.10)
        assert "0,10" in p.widget_ligne(0).texte_estimation_affiche()

    def test_ligne_reflete_le_profil_actif_au_depli(self, qtbot):
        # Au dépli, la ligne montre le profil actif (Précis) + lot auto → 0,12 × 0,5 = 0,06.
        p = _page(qtbot, [_res()])
        _ajouter(p, qtbot, [r"C:\a.pdf"])
        p.selectionner(p.modele.ligne(0).ident)
        assert p.modele.ligne(0).resultat.estimation['cout_usd'] == pytest.approx(0.06)

    def test_profil_tesseract_appele_sans_lot(self, qtbot):
        # Le lot ne concerne que Claude : estimer reçoit lot=False pour le profil Tesseract.
        appels = []

        def estimer_rec(chemin, type=None, profil=None, lot=False, modele=None,
                        dossier_sortie=None):
            appels.append((modele, lot))
            return _estimer(chemin, type=type, profil=profil, lot=lot, modele=modele)

        creer_application([])
        lanceur = LanceurAnalyse(analyser=lambda chemin, **kw: _res())
        p = PageConvertir(lanceur=lanceur, estimer_fn=estimer_rec)
        qtbot.addWidget(p)
        with qtbot.waitSignal(p.lanceur.fini, timeout=2000):
            p.ajouter_sources([r"C:\a.pdf"])
        p.selectionner(p.modele.ligne(0).ident)   # lot auto True → 3 cartes estimées
        lots_tesseract = [lot for modele, lot in appels if modele is None]
        lots_claude = [lot for modele, lot in appels if modele is not None]
        assert lots_tesseract and all(lot is False for lot in lots_tesseract)
        assert any(lot is True for lot in lots_claude)

    def test_lot_propose_au_dela_de_100_pages(self, qtbot):
        p = _page(qtbot, [_res(payantes=141)])
        _ajouter(p, qtbot, [r"C:\a.pdf"])
        ident = p.modele.ligne(0).ident
        p.selectionner(ident)
        assert p.modele.ligne(0).lot is True

    def test_lot_non_propose_en_dessous(self, qtbot):
        p = _page(qtbot, [_res(payantes=76)])
        _ajouter(p, qtbot, [r"C:\a.pdf"])
        ident = p.modele.ligne(0).ident
        p.selectionner(ident)
        assert p.modele.ligne(0).lot is False

    def test_basculer_lot_recalcule(self, qtbot):
        p = _page(qtbot, [_res()])
        _ajouter(p, qtbot, [r"C:\a.pdf"])
        ident = p.modele.ligne(0).ident
        p.selectionner(ident)
        p.choisir_profil(ident, "precis")          # 0,12 × 0,5 (lot auto) = 0,06
        assert p.modele.ligne(0).resultat.estimation['cout_usd'] == pytest.approx(0.06)
        p.basculer_lot(ident, False)               # sans lot → 0,12
        assert p.modele.ligne(0).resultat.estimation['cout_usd'] == pytest.approx(0.12)

    def test_reordonner_change_l_ordre(self, qtbot):
        p = _page(qtbot, [_res(), _res()])
        _ajouter(p, qtbot, [r"C:\a.pdf", r"C:\b.pdf"])
        a = p.modele.ligne(0).ident
        b = p.modele.ligne(1).ident
        p.reordonner(a, 1)
        assert [p.modele.ligne(i).ident for i in range(2)] == [b, a]

    def test_deposer_calcule_le_rang_depuis_le_y(self, qtbot):
        p = _page(qtbot, [_res(), _res(), _res()])
        _ajouter(p, qtbot, [r"C:\a.pdf", r"C:\b.pdf", r"C:\c.pdf"])
        for i in range(3):
            p.widget_ligne(i).setGeometry(0, i * 60, 400, 50)   # centres : 25, 85, 145
        a = p.modele.ligne(0).ident
        b = p.modele.ligne(1).ident
        c = p.modele.ligne(2).ident
        p.deposer_reordonne(a, 130)   # b (85) au-dessus, c (145) en dessous → rang 1
        assert [p.modele.ligne(i).ident for i in range(3)] == [b, a, c]

    def test_footer_cumule_cout_claude_et_differe(self, qtbot):
        # Deux fichiers prêts : a en lot (0,06 différé), b sans lot (0,12) → total 0,18.
        p = _page(qtbot, [_res(), _res()])
        _ajouter(p, qtbot, [r"C:\a.pdf", r"C:\b.pdf"])
        a = p.modele.ligne(0).ident
        b = p.modele.ligne(1).ident
        p.selectionner(a)
        p.choisir_profil(a, "precis")      # lot auto (141 pages) → 0,06 différé
        p.selectionner(b)
        p.choisir_profil(b, "precis")
        p.basculer_lot(b, False)           # sans lot → 0,12 immédiat
        texte = p.resume.text()
        assert "0,18" in texte and "Claude" in texte
        assert "0,06" in texte and "différé" in texte

    def test_inconnu_deplie_offre_creer_un_type(self, qtbot):
        p = _page(qtbot, [_res(etat=analyse.INCONNU, type_=None)])
        _ajouter(p, qtbot, [r"C:\mystere.pdf"])
        ident = p.modele.ligne(0).ident
        p.selectionner(ident)
        with qtbot.waitSignal(p.creer_type, timeout=1000):
            p.widget_ligne(0).bouton_creer_type.click()
