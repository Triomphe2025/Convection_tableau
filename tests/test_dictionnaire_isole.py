"""
Le vrai dictionnaire (data_dictionary.json) n'est jamais écrit par les tests : la suite
travaille sur une copie temporaire (tests/conftest.py), et le vrai fichier est contrôlé
identique avant et après la suite.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_dictionnaire_isole.py -v
"""
import data_dictionary


class TestDictionnaireIsole:

    def test_singleton_sur_la_copie(self, dictionnaire_temporaire):
        assert data_dictionary.get_dictionary().path.parent == dictionnaire_temporaire
        assert data_dictionary.get_pending_dictionary().path.parent == dictionnaire_temporaire

    def test_nouvelle_instance_sur_la_copie(self, dictionnaire_temporaire):
        assert data_dictionary.DataDictionary().path != data_dictionary.DICT_FILE

    def test_ecriture_dans_la_copie_vrai_fichier_intact(
            self, dictionnaire_temporaire, empreintes_dictionnaire):
        avant, empreinte = empreintes_dictionnaire
        dico = data_dictionary.get_dictionary()
        dico.add_value('SIGNAL', 'VALEUR FABRIQUEE PAR UN TEST')
        dico.save()
        assert 'VALEUR FABRIQUEE PAR UN TEST' in (
            dictionnaire_temporaire / 'data_dictionary.json').read_text('utf-8')
        assert empreinte() == avant

    def test_vrai_fichier_identique_jusqu_ici(self, empreintes_dictionnaire):
        avant, empreinte = empreintes_dictionnaire
        assert empreinte() == avant
