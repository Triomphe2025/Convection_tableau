"""
Tests de mesurer_precision.py (script CLI) sur des fichiers fabriqués :
une classe par fonction publique (Règle 07). Le cas réel 223111PE011 est
testé séparément dans tests/test_mesurer_precision_golden.py.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_mesurer_precision.py -v
"""
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl

import mesurer_precision as mpr


def _chemin_temp(suffixe: str) -> Path:
    """Chemin de fichier temporaire fermé (évite le verrou Windows de
    NamedTemporaryFile quand un autre outil rouvre le même fichier)."""
    fd, chemin = tempfile.mkstemp(suffix=suffixe)
    os.close(fd)
    return Path(chemin)


def _classeur(blocs):
    """blocs: liste de (entete, lignes_donnees, ligne_pied). Écrit un .xlsx temporaire."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for entete, lignes, pied in blocs:
        ws.append(entete)
        for ligne in lignes:
            ws.append(ligne)
        if pied:
            ws.append(pied)
        ws.append([])  # ligne vide entre blocs
    chemin = _chemin_temp('.xlsx')
    wb.save(chemin)
    return chemin


class TestLireXlsx(unittest.TestCase):

    def test_un_bloc_entete_donnees_pied(self):
        chemin = _classeur([(
            ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'],
            [['1', 'PH A104 01', 'RESERVE CABLEE', 'PH TA106 01']],
            ['CABLE : WPHA104/TA106', 'PAGE : 52'],
        )])
        pages = mpr.lire_xlsx(chemin)
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(pages[0]['rows']), 1)
        self.assertTrue(any('WPHA104' in p for p in pages[0]['pied_texte']))
        chemin.unlink()

    def test_deux_blocs_deviennent_deux_pages(self):
        bloc = (['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'],
                [['1', 'A', 'B', 'C']], ['PAGE : 1'])
        chemin = _classeur([bloc, bloc])
        pages = mpr.lire_xlsx(chemin)
        self.assertEqual(len(pages), 2)
        chemin.unlink()

    def test_lignes_avant_le_premier_entete_ignorees(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['bruit', 'avant', 'tout', 'entete'])
        ws.append(['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'])
        ws.append(['1', 'A', 'B', 'C'])
        chemin = _chemin_temp('.xlsx')
        wb.save(chemin)
        pages = mpr.lire_xlsx(chemin)
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(pages[0]['rows']), 1)
        chemin.unlink()

    def test_classeur_vide(self):
        wb = openpyxl.Workbook()
        chemin = _chemin_temp('.xlsx')
        wb.save(chemin)
        self.assertEqual(mpr.lire_xlsx(chemin), [])
        chemin.unlink()

    def test_feuille_nommee_explicitement(self):
        wb = openpyxl.Workbook()
        ws2 = wb.create_sheet('Autre')
        ws2.append(['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'])
        ws2.append(['1', 'A', 'B', 'C'])
        chemin = _chemin_temp('.xlsx')
        wb.save(chemin)
        pages = mpr.lire_xlsx(chemin, feuille='Autre')
        self.assertEqual(len(pages), 1)
        chemin.unlink()


class TestLireVeriteExcel(unittest.TestCase):

    def _fabriquer(self, lignes_tab, lignes_pied=None):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Verite_tableaux'
        ws.append([
            'Page extrait', 'Page document', 'Ligne', 'FIL', 'TENANT',
            'SIGNAL', 'ABOUTISSANT', 'A verifier en priorite', 'Valide par moi (x)',
        ])
        for ligne in lignes_tab:
            ws.append(ligne)
        if lignes_pied is not None:
            ws2 = wb.create_sheet('Verite_pieds')
            ws2.append([
                'Page extrait', 'Page document', 'CABLE', 'TYPE',
                'Complement', 'N° PLAN', 'INDICE', 'PAGE', 'Valide par moi (x)',
            ])
            for ligne in lignes_pied:
                ws2.append(ligne)
        chemin = _chemin_temp('.xlsx')
        wb.save(chemin)
        return chemin

    def test_colonnes_deduites_de_len_tete(self):
        ligne = [1, '1', 1, 'G', 'PH QTEL2 21', 'TEL PET', 'PH TELPH/A 01', None, 'X']
        chemin = self._fabriquer([ligne])
        pages, colonnes = mpr.lire_verite_excel(chemin)
        self.assertEqual(colonnes, ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'])
        chemin.unlink()

    def test_regroupement_par_page_extrait(self):
        chemin = self._fabriquer([
            [1, '1', 1, 'G', 'A', 'B', 'C', None, 'X'],
            [1, '1', 2, 'H', 'A', 'B', 'C', None, 'X'],
            [2, '2', 1, 'I', 'A', 'B', 'C', None, 'X'],
        ])
        pages, _ = mpr.lire_verite_excel(chemin)
        self.assertEqual(len(pages), 2)
        self.assertEqual(len(pages[0]['rows']), 2)
        self.assertEqual(len(pages[1]['rows']), 1)
        chemin.unlink()

    def test_page_sans_ligne_mais_avec_pied_incluse(self):
        chemin = self._fabriquer(
            [[1, '1', 1, 'G', 'A', 'B', 'C', None, 'X']],
            lignes_pied=[
                [1, '1', 'X', 'Y', 'Z', 'PLAN1', 'R', '1', 'X'],
                [2, '104', 'RESERVE', None, None, 'PLAN1', 'TP3', '104', 'X'],
            ],
        )
        pages, _ = mpr.lire_verite_excel(chemin)
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[1]['rows'], [])
        self.assertTrue(any('RESERVE' in p for p in pages[1]['pied_texte']))
        chemin.unlink()

    def test_sans_feuille_verite_pieds(self):
        chemin = self._fabriquer([[1, '1', 1, 'G', 'A', 'B', 'C', None, 'X']], lignes_pied=None)
        pages, _ = mpr.lire_verite_excel(chemin)
        self.assertEqual(pages[0]['pied_texte'], [])
        chemin.unlink()

    def test_espaces_conserves_et_positions_comparees(self):
        ligne = [1, '1', 1, 'D_T       02A', '1845N', 'ER        13', 'X', None, 'X']
        chemin = self._fabriquer([ligne])
        pages, _ = mpr.lire_verite_excel(chemin)
        ligne = pages[0]['rows'][0]
        self.assertEqual(ligne['cells'][0], 'D_T       02A')
        self.assertTrue(ligne['exact'])
        chemin.unlink()

    def test_lignes_sans_page_extrait_ignorees(self):
        chemin = self._fabriquer([[None, '', '', '', '', '', '', None, '']])
        pages, _ = mpr.lire_verite_excel(chemin)
        self.assertEqual(pages, [])
        chemin.unlink()


class TestLirePdfVectoriel(unittest.TestCase):

    def test_ligne_pipe_devient_une_ligne_de_donnees(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=400, height=200)
        page.insert_text((72, 72), '|1 |A   |B   |C   |', fontsize=10, fontname='cour')
        chemin = _chemin_temp('.pdf')
        doc.save(chemin)
        doc.close()
        colonnes = ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT']
        pages = mpr.lire_pdf_vectoriel(chemin, colonnes)
        self.assertEqual(len(pages), 1)
        chemin.unlink()

    def test_entete_et_soulignement_du_cadre_ignores(self):
        import fitz
        doc = fitz.open()
        page = doc.new_page(width=500, height=200)
        for y, texte in ((60, '|FIL |TENANT |SIGNAL |ABOUTISSANT |'),
                         (72, '|°°° |°°°°°° |°°°°°° |°°°°°°°°°°° |'),
                         (84, '|1 B |PH A1   |RESERVE|PH TA 01    |')):
            page.insert_text((20, y), texte, fontsize=9, fontname='cour')
        chemin = _chemin_temp('.pdf')
        doc.save(chemin)
        doc.close()
        pages = mpr.lire_pdf_vectoriel(chemin, ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT'])
        self.assertEqual([r['cells'][0] for r in pages[0]['rows']], ['1 B'])
        chemin.unlink()

    def test_page_sans_cadre_decoupee_par_la_grille(self):
        from template import TemplateManager
        modele = TemplateManager().get('REPARTITEUR')
        pages = mpr.lire_pdf_vectoriel(
            Path(__file__).parent / 'fixtures' / '223400PE137.pdf',
            list(modele.columns), template=modele,
        )
        page_37 = pages[36]
        self.assertEqual(len(page_37['rows']), 55)
        self.assertTrue(all(r['exact'] for r in page_37['rows']))
        self.assertTrue(any('PET' in lg for lg in page_37['pied_texte']))

    def test_page_sans_texte_donne_une_page_sans_lignes(self):
        import fitz
        doc = fitz.open()
        doc.new_page(width=200, height=200)
        chemin = _chemin_temp('.pdf')
        doc.save(chemin)
        doc.close()
        pages = mpr.lire_pdf_vectoriel(chemin, ['A', 'B'])
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]['rows'], [])
        chemin.unlink()


class TestVersionGit(unittest.TestCase):

    def test_retourne_le_hash_court(self):
        faux = MagicMock()
        faux.return_value.stdout = 'abc1234\n'
        with patch('mesurer_precision.subprocess.run', faux):
            self.assertEqual(mpr._version_git(), 'abc1234')

    def test_git_absent_retourne_point_d_interrogation(self):
        with patch('mesurer_precision.subprocess.run', side_effect=FileNotFoundError()):
            self.assertEqual(mpr._version_git(), '?')


class TestEcrireMesureCsv(unittest.TestCase):

    def test_cree_le_fichier_avec_entete(self):
        import mesure_precision as mp
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / 'mesures.csv'
            rapport = mp.RapportMesure(nb_cellules_comparees=10, nb_cellules_identiques=9)
            mpr.ecrire_mesure_csv(chemin, Path('sortie.xlsx'), rapport)
            lignes = list(csv.reader(chemin.open(encoding='utf-8')))
            self.assertEqual(lignes[0][0], 'date')
            self.assertEqual(lignes[1][1], 'sortie.xlsx')

    def test_ajoute_une_ligne_sans_repeter_len_tete(self):
        import mesure_precision as mp
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / 'mesures.csv'
            rapport = mp.RapportMesure()
            mpr.ecrire_mesure_csv(chemin, Path('a.xlsx'), rapport)
            mpr.ecrire_mesure_csv(chemin, Path('b.xlsx'), rapport)
            lignes = list(csv.reader(chemin.open(encoding='utf-8')))
            self.assertEqual(len(lignes), 3)


class TestEcrireMesureCsvAncienEntete(unittest.TestCase):

    def test_ancien_historique_complete_sans_glissement_de_valeurs(self):
        import mesure_precision as mp
        with tempfile.TemporaryDirectory() as tmp:
            chemin = Path(tmp) / 'mesures.csv'
            ancien = mpr.ENTETE_MESURES_CSV[:-2]
            with open(chemin, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(ancien)
                w.writerow([str(i) for i in range(len(ancien))])
            mpr.ecrire_mesure_csv(chemin, Path('b.xlsx'), mp.RapportMesure())
            lignes = list(csv.DictReader(chemin.open(encoding='utf-8')))
        self.assertEqual(lignes[0]['ecarts_positions'], str(len(ancien) - 1))
        self.assertEqual((lignes[0]['glissement'], lignes[0]['lignes_deplacees']), ('', ''))
        self.assertEqual((lignes[1]['glissement'], lignes[1]['lignes_deplacees']), ('0', '0'))


class TestMain(unittest.TestCase):

    def _fabriquer_paire(self, tmp):
        entete = ['FIL', 'TENANT', 'SIGNAL', 'ABOUTISSANT']
        ligne_donnee = ['1', 'PH QTEL2 21', 'TEL PET', 'PH TELPH/A 01']
        sortie = _classeur([(entete, [ligne_donnee], ['PAGE : 122'])])

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Verite_tableaux'
        entetes_tab = [
            'Page extrait', 'Page document', 'Ligne', 'FIL', 'TENANT',
            'SIGNAL', 'ABOUTISSANT', 'A verifier en priorite', 'Valide par moi (x)',
        ]
        ws.append(entetes_tab)
        ws.append([1, '122', 1, '1', 'PH QTEL2 21', 'TEL PET', 'PH TELPH/A 01', None, 'X'])
        ws2 = wb.create_sheet('Verite_pieds')
        ws2.append([
            'Page extrait', 'Page document', 'CABLE', 'TYPE',
            'Complement', 'N° PLAN', 'INDICE', 'PAGE', 'Valide par moi (x)',
        ])
        ws2.append([1, '122', None, None, None, None, None, '122', 'X'])
        reference = Path(tmp) / 'verite.xlsx'
        wb.save(reference)
        return sortie, reference

    def test_code_retour_0_si_identique(self):
        with tempfile.TemporaryDirectory() as tmp:
            sortie, reference = self._fabriquer_paire(tmp)
            code = mpr.main([str(sortie), str(reference), '--csv', str(Path(tmp) / 'm.csv')])
        self.assertEqual(code, 0)
        sortie.unlink()

    def test_sortie_introuvable_leve_filenotfounderror(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, reference = self._fabriquer_paire(tmp)
            with self.assertRaises(FileNotFoundError):
                mpr.main([str(Path(tmp) / 'absent.xlsx'), str(reference)])

    def test_reference_extension_non_supportee(self):
        with tempfile.TemporaryDirectory() as tmp:
            sortie, _ = self._fabriquer_paire(tmp)
            autre = Path(tmp) / 'notes.txt'
            autre.write_text('x', encoding='utf-8')
            with self.assertRaises(ValueError):
                mpr.main([str(sortie), str(autre)])
            sortie.unlink()

    def test_reference_pdf_sans_modele_leve_valueerror(self):
        import fitz
        with tempfile.TemporaryDirectory() as tmp:
            sortie, _ = self._fabriquer_paire(tmp)
            doc = fitz.open()
            doc.new_page()
            pdf = Path(tmp) / 'ref.pdf'
            doc.save(pdf)
            doc.close()
            with self.assertRaises(ValueError):
                mpr.main([str(sortie), str(pdf)])
            sortie.unlink()


if __name__ == '__main__':
    unittest.main()
