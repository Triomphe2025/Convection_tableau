"""Construction d'un exe PyInstaller en préservant la licence du poste.

Si un fichier de licence (Config.LICENCE_NOM) est déjà à côté de l'exe (dist\\<nom>) avant le
build, il est remis en place après — jamais lu, jamais copié ailleurs (déplacé dans un abri
temporaire puis ramené). build\\<nom> est supprimé à la fin pour ne laisser que dist\\.

Appel : env\\Scripts\\python.exe outils_build.py <spec> <nom>
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from config import Config


def _pyinstaller(spec: str) -> int:
    return subprocess.call([sys.executable, "-m", "PyInstaller", spec, "--noconfirm", "--clean"])


def nettoyer_build(nom: str, racine: Path) -> None:
    dossier = racine / "build" / nom
    if dossier.exists():
        shutil.rmtree(dossier, ignore_errors=True)


def construire(spec: str, nom: str, racine=None, build_fn=None) -> int:
    """Préserve la licence, (re)construit l'exe, la remet, supprime build\\<nom> ; rend le code."""
    racine = Path(racine or ".")
    build_fn = build_fn or _pyinstaller
    dist = racine / "dist" / nom
    licence = dist / Config.LICENCE_NOM

    abri = None
    if licence.exists():
        abri = Path(tempfile.mkdtemp(prefix="triosse_lic_")) / Config.LICENCE_NOM
        shutil.move(str(licence), str(abri))  # déplacée, jamais lue ni copiée ailleurs
    try:
        code = build_fn(spec)
    finally:
        if abri is not None and abri.exists():
            dist.mkdir(parents=True, exist_ok=True)
            shutil.move(str(abri), str(dist / Config.LICENCE_NOM))
            shutil.rmtree(abri.parent, ignore_errors=True)
    nettoyer_build(nom, racine)
    return code


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage : python outils_build.py <spec> <nom>")
        raise SystemExit(2)
    raise SystemExit(construire(sys.argv[1], sys.argv[2]))
