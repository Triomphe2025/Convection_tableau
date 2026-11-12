"""Garde-fou : chaque module projet atteint par un point d'entrée est dans le .spec."""
import ast
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SPEC = RACINE / 'TriosSeconverter.spec'

# interface.py est le script d'Analysis (embarque d'office) ; converter et service_conversion
# sont les points d'entree du moteur dont l'exe charge toute la chaine d'imports.
POINTS_ENTREE = ['interface', 'converter', 'service_conversion']


def _est_module_projet(nom):
    rel = nom.replace('.', '/')
    return (RACINE / (rel + '.py')).is_file() or (RACINE / rel / '__init__.py').is_file()


def _chemin_module(nom):
    rel = nom.replace('.', '/')
    fichier = RACINE / (rel + '.py')
    if fichier.is_file():
        return fichier, False
    paquet = RACINE / rel / '__init__.py'
    if paquet.is_file():
        return paquet, True
    return None, False


def _imports_projet(nom):
    chemin, est_paquet = _chemin_module(nom)
    if chemin is None:
        return set()
    arbre = ast.parse(chemin.read_text(encoding='utf-8'))
    paquet = nom if est_paquet else nom.rpartition('.')[0]
    trouves = set()
    for node in ast.walk(arbre):
        if isinstance(node, ast.Import):
            for alias in node.names:
                trouves.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = paquet
                for _ in range(node.level - 1):
                    base = base.rpartition('.')[0]
                module = (base + '.' + node.module) if node.module else base
            else:
                module = node.module or ''
            trouves.add(module)
            for alias in node.names:
                trouves.add(module + '.' + alias.name)
    return {m for m in trouves if m and _est_module_projet(m)}


def _modules_atteints(racines):
    vus = set()
    pile = list(racines)
    while pile:
        module = pile.pop()
        if module in vus:
            continue
        vus.add(module)
        pile.extend(_imports_projet(module) - vus)
    return vus


def _modules_spec():
    arbre = ast.parse(SPEC.read_text(encoding='utf-8'))
    for node in ast.walk(arbre):
        if isinstance(node, ast.Assign):
            for cible in node.targets:
                if isinstance(cible, ast.Name) and cible.id == 'MODULES_PROJET':
                    return set(ast.literal_eval(node.value))
    raise AssertionError("MODULES_PROJET introuvable dans TriosSeconverter.spec")


class TestModulesProjetDansSpec:

    def test_tout_module_atteint_est_liste(self):
        requis = _modules_atteints(POINTS_ENTREE)
        requis.discard('interface')
        manquants = sorted(m for m in requis if m not in _modules_spec())
        assert not manquants, (
            "Modules du projet atteints depuis "
            + ", ".join(POINTS_ENTREE)
            + " mais absents de MODULES_PROJET du .spec (exe incomplet) : "
            + ", ".join(manquants)
        )

    def test_spec_sans_entree_morte(self):
        # Une entree jamais atteinte signale un module retire ou mal nomme dans le .spec.
        atteints = _modules_atteints(POINTS_ENTREE)
        mortes = sorted(m for m in _modules_spec() if m not in atteints)
        assert not mortes, "Entrees de MODULES_PROJET jamais atteintes : " + ", ".join(mortes)
