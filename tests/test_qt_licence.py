"""Étape 4 — la licence est contrôlée avant d'ouvrir la fenêtre, avec les mêmes messages.

run_qt réutilise licence.exiger() (même fichier, mêmes textes que l'exe actuel) : licence
valable -> préavis éventuel ; LicenceError -> message puis arrêt (code 3). Aucune boîte Qt
réelle n'est ouverte ici : on injecte le présentateur de message.
"""
import pytest

import licence
import run_qt


def test_licence_valable_rend_le_preavis_sans_message(monkeypatch):
    monkeypatch.setattr(licence, "exiger", lambda: "expire bientôt")
    messages = []
    preavis = run_qt.verifier_licence(lambda m: messages.append(m))
    assert preavis == "expire bientôt"
    assert messages == []  # pas d'erreur affichée quand la licence est valable


def test_licence_invalide_affiche_le_message_et_arrete(monkeypatch):
    def lever():
        raise licence.LicenceError("Aucune licence trouvée. 1234")
    monkeypatch.setattr(licence, "exiger", lever)
    messages = []
    with pytest.raises(SystemExit) as sortie:
        run_qt.verifier_licence(lambda m: messages.append(m))
    assert sortie.value.code == 3
    # Le message montré est exactement celui de la LicenceError (mêmes textes que l'exe actuel).
    assert messages == ["Aucune licence trouvée. 1234"]


def test_titre_licence_identique_a_l_interface_actuelle():
    # Même titre que interface.py (_controler_licence_graphique).
    assert run_qt.TITRE_LICENCE == "TriosSeconverter — licence"
