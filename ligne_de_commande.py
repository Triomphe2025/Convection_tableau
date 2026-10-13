"""
Ligne de commande de TriosSeconverter (exe ou Python) : conversion, reformatage, DXF, état.

L'exe n'a pas de console : chaque commande écrit son journal dans un fichier (--journal), et
rend un code de sortie (0 = réussi). Sert aux essais de l'exe sans clic et aux traitements par
lots. Appelée par interface.py quand l'exe reçoit des arguments ; aucune logique ici, seulement
la répartition vers converter, generer_classeur et cad.service.

Exemples :
    TriosSeconverter.exe infos --journal etat.txt
    TriosSeconverter.exe convertir doc.pdf sortie --modele "REPARTITEUR 2" --mode tesseract
    TriosSeconverter.exe formater classeur.xlsx classeur_reformate.xlsx
    TriosSeconverter.exe dxf plan.tif sortie_dxf
"""
import argparse
import sys
from pathlib import Path
from typing import Callable, List, Optional


def _ecrivain(journal: Optional[str]) -> Callable[[str], None]:
    """Écrit chaque ligne dans le fichier journal et, s'il y en a une, sur la console."""
    fichier = open(journal, 'w', encoding='utf-8') if journal else None
    console = sys.stdout if sys.stdout is not None else None
    if console is not None and hasattr(console, 'reconfigure'):
        console.reconfigure(encoding='utf-8', errors='replace')

    def ecrire(message: str) -> None:
        for sortie in (fichier, console):
            if sortie is not None:
                sortie.write(f"{message}\n")
                sortie.flush()
    return ecrire


def _infos(log) -> int:
    from config import Config, chemin_ressource
    from lexique_reference import lexique_complet
    from template import TemplateManager
    etat = 'trouvé' if Config.TESSERACT_TROUVE else 'INTROUVABLE'
    log(f"Tesseract : {Config.TESSERACT_PATH} ({etat})")
    log(f"Dossier utilisateur : {Config.DOSSIER_UTILISATEUR}")
    _, bilan = lexique_complet(chemin_ressource(Config.QUALITE_LEXIQUE_COMPILE),
                               Path(Config.QUALITE_LEXIQUE_DOSSIER),
                               Config.QUALITE_LEXIQUE_REFERENCE, Config.QUALITE_LEXIQUE_FEUILLE)
    log(f"Lexique : {bilan}")
    gestion = TemplateManager()
    log("Modèles : " + ', '.join(f"{n}{' (livré)' if gestion.est_livre(n) else ''}"
                                 for n in gestion.names()))
    return 0


def _convertir(args, log) -> int:
    from config import Config
    from converter import Converter
    from template import TemplateManager
    if args.mode:
        Config.OCR_MODE = args.mode
    resultat = Converter(word_file=Path(args.source), output_dir=Path(args.sortie),
                         template=TemplateManager().get(args.modele), on_log=log).run()
    log(f"Excel : {resultat.get('excel')}")
    return 0


def _formater(args, log) -> int:
    from generer_classeur import reformatter_excel
    n = reformatter_excel(Path(args.entree), Path(args.sortie), on_log=log)
    return 0 if n else 1


def _dxf(args, log) -> int:
    from cad.service import convert_to_dxf
    chemin = convert_to_dxf(Path(args.source), Path(args.sortie), on_log=log)
    log(f"DXF : {chemin}")
    return 0 if chemin and Path(chemin).exists() else 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog='TriosSeconverter')
    parser.add_argument('--journal', default=None, help="Fichier où écrire le journal")
    sous = parser.add_subparsers(dest='commande', required=True)
    sous.add_parser('infos', help="Tesseract, dossier utilisateur, lexique, modèles")
    c = sous.add_parser('convertir', help="Convertit un document (PDF, Word, journal .jsonl)")
    c.add_argument('source')
    c.add_argument('sortie', help="Dossier de sortie")
    c.add_argument('--modele', default='Bornier standard')
    c.add_argument('--mode', default=None, help="tesseract, claude, … (défaut : config.py)")
    f = sous.add_parser('formater', help="Reformate un Excel produit")
    f.add_argument('entree')
    f.add_argument('sortie')
    d = sous.add_parser('dxf', help="Vectorise un plan (PDF, TIF) en DXF")
    d.add_argument('source')
    d.add_argument('sortie', help="Dossier de sortie")
    args = parser.parse_args(argv)
    log = _ecrivain(args.journal)
    try:
        return {'infos': lambda: _infos(log), 'convertir': lambda: _convertir(args, log),
                'formater': lambda: _formater(args, log), 'dxf': lambda: _dxf(args, log)
                }[args.commande]()
    except Exception as exc:
        import traceback
        log(f"✗ {type(exc).__name__} : {exc}")
        log(traceback.format_exc())
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
