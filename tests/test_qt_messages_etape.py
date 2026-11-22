"""Étape 2C-4 — messages d'étape en bas à droite, 3 s chacun (jeton message_etape_affiche).

File d'attente : un message à la fois, 3 s, puis le suivant. On teste la file et la durée ; le
passage au suivant est déclenché par le minuteur en vrai, appelé à la main dans le test.
"""
import pytest

pytest.importorskip("PySide6")

from trios_qt import animations, theme  # noqa: E402
from trios_qt.application import creer_application  # noqa: E402
from trios_qt.messages_etape import MessagesEtape  # noqa: E402


@pytest.fixture
def messages(qtbot):
    creer_application([])
    animations.definir_reduction(False)   # déterministe : le glissement peut démarrer
    m = MessagesEtape()
    qtbot.addWidget(m)
    yield m
    animations.reinitialiser()


class TestMessagesEtape:

    def test_afficher_montre_le_message(self, messages):
        messages.afficher("Plus que 10 pages")
        assert messages.message_courant() == "Plus que 10 pages"
        assert messages.est_visible() is True

    def test_file_passe_au_suivant(self, messages):
        messages.afficher("100 tableaux")
        messages.afficher("Plus que 10 pages")
        assert messages.message_courant() == "100 tableaux"   # le 1er d'abord
        messages._afficher_suivant()                          # fin des 3 s du 1er
        assert messages.message_courant() == "Plus que 10 pages"

    def test_file_videe_masque(self, messages):
        messages.afficher("Fin")
        messages._afficher_suivant()      # plus rien dans la file
        assert messages.message_courant() == ""
        assert messages.est_visible() is False

    def test_duree_est_le_jeton(self, messages):
        attendu = int(theme.charger_jetons()["mouvement_ms"]["message_etape_affiche"])
        assert messages.duree_ms() == attendu

    def test_minuteur_actif_pendant_affichage(self, messages):
        messages.afficher("x")
        assert messages.minuteur_actif() is True

    def test_cache_vide_la_file(self, messages):
        messages.afficher("a")
        messages.afficher("b")
        messages.show()
        messages.hide()
        assert messages.est_visible() is False
        assert messages.minuteur_actif() is False


class TestMessagesCarte:

    def test_est_une_carte_avec_icone(self, messages):
        assert messages.carte.objectName() == "carte_message"
        assert not messages.icone_pixmap().isNull()

    def test_duree_glissement_est_le_jeton(self, messages):
        attendu = int(theme.charger_jetons()["mouvement_ms"]["passage_ecran"])
        assert messages.duree_glissement_ms() == attendu

    def test_glisse_quand_anime(self, messages):
        messages.resize(400, 300)
        messages.afficher("Plus que 10 pages")
        assert messages.en_glissement() is True

    def test_apparait_sans_glissement_si_reduit(self, messages):
        animations.definir_reduction(True)
        messages.resize(400, 300)
        messages.afficher("Plus que 10 pages")
        assert messages.en_glissement() is False
        assert messages.est_visible() is True
