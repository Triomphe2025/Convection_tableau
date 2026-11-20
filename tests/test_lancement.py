"""Contrôleur de lancement (sans Qt) : fichiers traités un à un, erreur → suivant, arrêt."""
import evenements as ev
from trios_qt.lancement import ControleurLancement


class _FauxTraitement:
    def __init__(self):
        self.demarres = []
        self.evenements = []
        self.fin = None

    def demarrer_fichier(self, nom):
        self.demarres.append(nom)

    def sur_evenement(self, e):
        self.evenements.append(e)

    def terminer(self, excel=None, dossier=None):
        self.fin = (excel, dossier)


class _FauxService:
    def __init__(self, chemin, dossier, on_ev, sortie=ev.FIN):
        self.chemin = chemin
        self.dossier = dossier
        self.on_ev = on_ev
        self.resultat = chemin + ".xlsx"
        self.arrete = False
        self._sortie = sortie

    def demarrer(self):
        self.on_ev(ev.Evenement(type=ev.PAGE_LUE, rang=1, total=1))
        self.on_ev(ev.Evenement(type=self._sortie))

    def arreter(self):
        self.arrete = True


class TestControleurLancement:

    def test_traite_tous_les_fichiers_dans_l_ordre(self):
        t = _FauxTraitement()
        c = ControleurLancement(lambda ch, d, cb: _FauxService(ch, d, cb), t)
        c.lancer([("a.pdf", r"C:\s"), ("b.pdf", r"C:\s")])
        assert t.demarres == ["a.pdf", "b.pdf"]
        assert t.fin is not None   # terminé, boutons d'ouverture montrés

    def test_erreur_passe_au_suivant(self):
        t = _FauxTraitement()

        def fabrique(ch, d, cb):
            return _FauxService(ch, d, cb, sortie=ev.ERREUR if ch == "a.pdf" else ev.FIN)

        c = ControleurLancement(fabrique, t)
        c.lancer([("a.pdf", ""), ("b.pdf", "")])
        assert t.demarres == ["a.pdf", "b.pdf"]   # l'échec de a n'arrête pas b

    def test_arreter_stoppe_le_service_et_vide_la_file(self):
        t = _FauxTraitement()
        services = []

        def fabrique(ch, d, cb):
            s = _FauxService(ch, d, cb, sortie=ev.PAGE_DEBUT)  # ne se termine pas seul
            services.append(s)
            return s

        c = ControleurLancement(fabrique, t)
        c.lancer([("a.pdf", ""), ("b.pdf", "")])
        c.arreter()
        assert services[-1].arrete is True
        assert c.en_cours() is False
