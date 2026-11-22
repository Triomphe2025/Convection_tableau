"""Fenêtre principale : barre latérale + QStackedWidget (une page vide par écran).

Structure de l'écran 01_convertir.png. Les pages sont vides à l'étape 3 (contenu aux étapes
suivantes) ; le changement d'écran se fait en fondu (jeton passage_ecran, 300 ms), sauf si les
animations sont réduites.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QSize, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from trios_qt import animations, icones, theme


class _PontEvenements(QObject):
    """Fait traverser au fil de l'interface les événements émis par le fil de conversion."""
    recu = Signal(object)


LARGEUR_BARRE = 232  # px, comme la maquette 01_convertir
TAILLE_ICONE = 18

TITRE_FENETRE = "TriosSeconverter"

# (clé, libellé, marque) ; marque : None, "compteur" (Relecture) ou "beta" (Plans → DXF).
NAV_PRINCIPALE = (
    ("convertir", "Convertir", None),
    ("relecture", "Relecture", "compteur"),
    ("mise_en_forme", "Mise en forme Excel", None),
    ("plans", "Plans → DXF", "beta"),
)
NAV_BAS = (
    ("reglages", "Réglages", None),
    ("aide", "Aide", None),
)


class FenetrePrincipale(QWidget):
    """Fenêtre racine ; expose .pages, .boutons et aller_a(clé) pour la navigation et les tests."""

    def __init__(self, jetons: dict | None = None, points_a_relire: int = 0,
                 fabrique_service=None):
        super().__init__()
        self._jetons = jetons or theme.charger_jetons()
        self._points_a_relire = points_a_relire
        self._fabrique_service = fabrique_service or self._fabrique_reelle
        self._controleur = None
        self._ponts = []
        self.setObjectName("fenetre")  # cible QSS du fond général (pas tous les QWidget)
        self.setWindowTitle(TITRE_FENETRE)
        self.resize(1360, 900)

        self.pages: dict[str, QWidget] = {}
        self.boutons: dict[str, QPushButton] = {}
        self._pile = QStackedWidget()
        self._groupe = QButtonGroup(self)
        self._groupe.setExclusive(True)
        self._duree = int(self._jetons["mouvement_ms"]["passage_ecran"])
        self._courbe = animations.courbe_depuis_jetons(self._jetons["courbe_standard"])

        racine = QHBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(0)
        racine.addWidget(self._construire_barre_laterale())
        racine.addWidget(self._pile, 1)

        self._monter_convertir()
        self._monter_traitement()

        premiere = NAV_PRINCIPALE[0][0]
        self.boutons[premiere].setChecked(True)
        self._pile.setCurrentWidget(self.pages[premiere])

    def _monter_traitement(self) -> None:
        # Écran Traitement hors barre latérale : atteint depuis « Lancer ».
        from trios_qt.page_traitement import PageTraitement
        self.page_traitement = PageTraitement()
        self.page_traitement.setProperty("classe", "page")
        self.pages["traitement"] = self.page_traitement
        self._pile.addWidget(self.page_traitement)
        self.page_convertir.lancer_demande.connect(self._lancer_conversion)
        self.page_traitement.arret_demande.connect(self._arreter_conversion)

    def _lancer_conversion(self) -> None:
        from trios_qt.lancement import ControleurLancement
        couples = self.page_convertir.fichiers_a_lancer()
        if not couples:
            return
        self._controleur = ControleurLancement(self._fabrique_service, self.page_traitement)
        self.aller_a("traitement")
        self._controleur.lancer(couples)

    def _arreter_conversion(self) -> None:
        if self._controleur is not None:
            self._controleur.arreter()

    def _fabrique_reelle(self, chemin, dossier, on_evenement):
        from pathlib import Path

        from converter import Converter
        from service_conversion import ServiceConversion

        pont = _PontEvenements()
        pont.recu.connect(on_evenement, Qt.ConnectionType.QueuedConnection)
        self._ponts.append(pont)   # garder la référence (sinon ramassé)
        converter = Converter(Path(chemin), Path(dossier or "."),
                              on_log=lambda _m: None)
        return ServiceConversion(converter, on_evenement=pont.recu.emit)

    def _monter_convertir(self) -> None:
        # Remplace tout le contenu de la page générique « convertir » par l'écran réel
        # (qui porte son propre titre « Nouvelle conversion »).
        from trios_qt.page_convertir import PageConvertir
        page = self.pages["convertir"]
        disposition = page.layout()
        while disposition.count():
            element = disposition.takeAt(0)
            widget = element.widget()
            if widget is not None:
                widget.setParent(None)  # détache tout de suite (deleteLater est différé)
                widget.deleteLater()
        disposition.setContentsMargins(0, 0, 0, 0)
        self.page_convertir = PageConvertir(parent=page)
        disposition.addWidget(self.page_convertir, 1)

    def _construire_barre_laterale(self) -> QWidget:
        c = self._jetons["couleurs"]
        barre = QWidget()
        barre.setObjectName("barre_laterale")
        barre.setFixedWidth(LARGEUR_BARRE)
        colonne = QVBoxLayout(barre)
        colonne.setContentsMargins(16, 20, 16, 16)
        colonne.setSpacing(4)

        self._logo = QLabel()
        self._logo.setObjectName("logo")
        self._logo.setTextFormat(Qt.TextFormat.RichText)
        self._logo.setText(
            f'<span style="color:{c["rose_trios"]}">Trios</span>'
            f'<span style="color:{c["texte"]}">Seconverter</span>')
        colonne.addWidget(self._logo)
        colonne.addSpacing(18)

        for cle, libelle, marque in NAV_PRINCIPALE:
            colonne.addWidget(self._creer_entree(cle, libelle, marque))
        colonne.addStretch(1)
        for cle, libelle, marque in NAV_BAS:
            colonne.addWidget(self._creer_entree(cle, libelle, marque))

        colonne.addWidget(self._carte_etat())
        return barre

    def _creer_entree(self, cle: str, libelle: str, marque) -> QPushButton:
        c = self._jetons["couleurs"]
        bouton = QPushButton(f"  {libelle}")
        bouton.setObjectName(f"nav_{cle}")
        bouton.setProperty("classe", "nav")  # cible du style QSS commun aux entrées de nav
        bouton.setCheckable(True)
        bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        bouton.setIconSize(QSize(TAILLE_ICONE, TAILLE_ICONE))
        # Icône teintée : texte_secondaire au repos, rose quand l'entrée est active.
        icone_repos = icones.charger_icone(cle, c["texte_secondaire"], TAILLE_ICONE)
        icone_actif = icones.charger_icone(cle, c["rose_trios"], TAILLE_ICONE)
        bouton.setIcon(icone_repos)
        bouton.toggled.connect(
            lambda actif, b=bouton, r=icone_repos, a=icone_actif: b.setIcon(a if actif else r))
        bouton.clicked.connect(lambda _=False, k=cle: self.aller_a(k))
        self._groupe.addButton(bouton)
        self.boutons[cle] = bouton
        if marque:
            self._ajouter_pastille(bouton, marque)

        page = QWidget()
        page.setObjectName(f"page_{cle}")
        page.setProperty("classe", "page")  # reçoit le fond général (QSS)
        disposition = QVBoxLayout(page)
        disposition.setContentsMargins(40, 36, 40, 36)
        titre = QLabel(libelle)
        titre.setObjectName("titre_ecran")
        disposition.addWidget(titre)
        disposition.addStretch(1)
        self.pages[cle] = page
        self._pile.addWidget(page)
        return bouton

    def _ajouter_pastille(self, bouton: QPushButton, marque: str) -> None:
        # Pastille alignée à droite de l'entrée : compteur (Relecture) ou « bêta » (Plans → DXF).
        rangee = QHBoxLayout(bouton)
        rangee.setContentsMargins(0, 0, 10, 0)
        rangee.addStretch(1)
        if marque == "compteur":
            pastille = QLabel(str(self._points_a_relire))
            pastille.setObjectName("pastille_compteur")
        else:
            pastille = QLabel("bêta")
            pastille.setObjectName("pastille_beta")
        pastille.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pastille.setFixedHeight(theme.HAUTEUR_PASTILLE)  # pilule, pas bloc pleine hauteur
        rangee.addWidget(pastille, 0, Qt.AlignmentFlag.AlignVCenter)
        self.pastilles = getattr(self, "pastilles", {})
        self.pastilles[bouton.objectName()] = pastille

    def _carte_etat(self) -> QWidget:
        import interface_helpers
        from config import Config

        carte = QWidget()
        carte.setObjectName("carte_etat")
        disposition = QVBoxLayout(carte)
        disposition.setContentsMargins(12, 10, 12, 10)
        disposition.setSpacing(2)

        modele = interface_helpers.nom_modele_lisible(
            getattr(Config, "CLAUDE_OCR_MODEL", "")) or "—"
        modele = modele.split(" — ")[0]   # carte étroite : sans la mention « recommandé »
        self.etiquette_modele = QLabel(modele)
        self.etiquette_modele.setObjectName("etat_modele")

        ligne_cle = QHBoxLayout()
        ligne_cle.setContentsMargins(0, 0, 0, 0)
        ligne_cle.setSpacing(6)
        self.pastille_cle = QLabel()
        self.pastille_cle.setObjectName("etat_pastille_cle")
        self.pastille_cle.setFixedSize(8, 8)
        self.etiquette_cle = QLabel()
        self.etiquette_cle.setObjectName("etat_cle")
        ligne_cle.addWidget(self.pastille_cle, 0, Qt.AlignmentFlag.AlignVCenter)
        ligne_cle.addWidget(self.etiquette_cle, 1)

        self.etiquette_version = QLabel("Version 2.0 · aperçu")
        self.etiquette_version.setObjectName("etat_version")
        disposition.addWidget(self.etiquette_modele)
        disposition.addLayout(ligne_cle)
        disposition.addWidget(self.etiquette_version)
        # Carte cliquable : saisir / coller la clé API (persistée entre sessions).
        carte.setCursor(Qt.CursorShape.PointingHandCursor)
        carte.mousePressEvent = lambda _e: self._saisir_cle_api()
        self._rafraichir_carte_cle()
        return carte

    def _rafraichir_carte_cle(self) -> None:
        import interface_helpers
        from config import Config
        c = self._jetons["couleurs"]
        etat = interface_helpers.etat_cle_api(getattr(Config, "CLAUDE_API_KEY", ""))
        self.couleur_cle = c["succes"] if etat == "configurée" else c["a_relire"]
        self.pastille_cle.setStyleSheet(
            f"background-color: {self.couleur_cle}; border-radius: 4px;")
        self.etiquette_cle.setText(f"clé {etat}")

    def definir_cle_api(self, cle: str) -> None:
        """Enregistre la clé (persistée), la pose dans Config et rafraîchit la carte d'état."""
        from config import Config
        from trios_qt import reglages
        cle = (cle or "").strip()
        reglages.ecrire_cle_api(cle)
        Config.CLAUDE_API_KEY = cle
        self._rafraichir_carte_cle()

    def _saisir_cle_api(self) -> None:
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        from config import Config
        texte, ok = QInputDialog.getText(
            self, "Clé API Anthropic", "Colle ta clé API (sk-…) :",
            QLineEdit.EchoMode.Password, getattr(Config, "CLAUDE_API_KEY", ""))
        if ok:
            self.definir_cle_api(texte)

    def aller_a(self, cle: str) -> None:
        page = self.pages[cle]
        self._pile.setCurrentWidget(page)
        bouton = self.boutons.get(cle)   # les écrans hors nav (traitement) n'ont pas de bouton
        if bouton is not None and not bouton.isChecked():
            bouton.setChecked(True)
        animations.fondu_entree(page, self._duree, self._courbe)

    def ecran_courant(self) -> str:
        courant = self._pile.currentWidget()
        for cle, page in self.pages.items():
            if page is courant:
                return cle
        return ""
