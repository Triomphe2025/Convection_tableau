"""Étape 3 — fenêtre principale : chaque bouton de la barre latérale affiche sa page."""
import pytest

pytest.importorskip("PySide6")

from trios_qt import animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.fenetre import NAV_BAS, NAV_PRINCIPALE, FenetrePrincipale  # noqa: E402

TOUTES_LES_CLES = [c for c, _, _ in NAV_PRINCIPALE] + [c for c, _, _ in NAV_BAS]


@pytest.fixture
def fenetre(qtbot):
    creer_application([])
    theme.appliquer_theme(creer_application([]))
    # Navigation déterministe : pas de fondu en cours pendant les assertions.
    animations.definir_reduction(True)
    f = FenetrePrincipale(points_a_relire=12)
    qtbot.addWidget(f)
    yield f
    animations.reinitialiser()


def test_ecran_par_defaut_est_convertir(fenetre):
    assert fenetre.ecran_courant() == "convertir"
    assert fenetre.boutons["convertir"].isChecked()


def test_chaque_bouton_affiche_sa_page(fenetre):
    for cle in TOUTES_LES_CLES:
        fenetre.boutons[cle].click()
        assert fenetre.ecran_courant() == cle, f"le bouton {cle} n'a pas affiché sa page"


def test_badge_relecture_affiche_le_compteur(fenetre):
    assert fenetre.pastilles["nav_relecture"].text() == "12"


def test_plans_porte_la_mention_beta(fenetre):
    assert fenetre.pastilles["nav_plans"].text() == "bêta"


def test_carte_etat_cle_configuree_pastille_verte(qtbot, monkeypatch):
    from config import Config
    from trios_qt import theme
    monkeypatch.setattr(Config, "CLAUDE_API_KEY", "sk-xxxx", raising=False)
    monkeypatch.setattr(Config, "CLAUDE_OCR_MODEL", "claude-sonnet-5-5", raising=False)
    jetons = theme.charger_jetons()
    f = FenetrePrincipale(jetons=jetons)
    qtbot.addWidget(f)
    assert "Sonnet" in f.etiquette_modele.text()
    assert "configurée" in f.etiquette_cle.text()
    assert f.couleur_cle == jetons["couleurs"]["succes"]


def test_carte_etat_cle_absente_pastille_orange(qtbot, monkeypatch):
    from config import Config
    from trios_qt import theme
    monkeypatch.setattr(Config, "CLAUDE_API_KEY", "", raising=False)
    jetons = theme.charger_jetons()
    f = FenetrePrincipale(jetons=jetons)
    qtbot.addWidget(f)
    assert "absente" in f.etiquette_cle.text()
    assert f.couleur_cle == jetons["couleurs"]["a_relire"]
