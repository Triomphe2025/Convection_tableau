"""outils_build : préserve la licence du poste au rebuild et nettoie build\\<nom>."""
from pathlib import Path

import outils_build
from config import Config

NOM = "TriosSeconverter"
LIC = Config.LICENCE_NOM


def _preparer(racine: Path, avec_licence: bool):
    dist = racine / "dist" / NOM
    dist.mkdir(parents=True)
    (dist / f"{NOM}.exe").write_text("ancien exe", encoding="utf-8")
    if avec_licence:
        (dist / LIC).write_text("CLE-DU-POSTE", encoding="utf-8")
    (racine / "build" / NOM).mkdir(parents=True)
    return dist


def _build_simule(dist: Path):
    # Imite PyInstaller --clean --noconfirm : efface puis recrée dist\<nom>.
    def _fn(spec):
        import shutil
        shutil.rmtree(dist, ignore_errors=True)
        dist.mkdir(parents=True)
        (dist / f"{NOM}.exe").write_text("nouvel exe", encoding="utf-8")
        return 0
    return _fn


def test_licence_remise_a_cote_du_nouvel_exe(tmp_path):
    dist = _preparer(tmp_path, avec_licence=True)
    code = outils_build.construire("x.spec", NOM, racine=tmp_path, build_fn=_build_simule(dist))
    assert code == 0
    assert (dist / f"{NOM}.exe").read_text(encoding="utf-8") == "nouvel exe"
    # La licence est de retour, intacte, et n'a pas été laissée ailleurs.
    assert (dist / LIC).read_text(encoding="utf-8") == "CLE-DU-POSTE"
    assert list(tmp_path.rglob(LIC)) == [dist / LIC]
    assert not (tmp_path / "build" / NOM).exists()


def test_sans_licence_rien_a_preserver(tmp_path):
    dist = _preparer(tmp_path, avec_licence=False)
    outils_build.construire("x.spec", NOM, racine=tmp_path, build_fn=_build_simule(dist))
    assert not (dist / LIC).exists()
    assert not (tmp_path / "build" / NOM).exists()


def test_licence_restauree_meme_si_le_build_echoue(tmp_path):
    dist = _preparer(tmp_path, avec_licence=True)

    def _echoue(spec):
        import shutil
        shutil.rmtree(dist, ignore_errors=True)  # le rebuild a déjà effacé dist
        dist.mkdir(parents=True)
        return 2

    code = outils_build.construire("x.spec", NOM, racine=tmp_path, build_fn=_echoue)
    assert code == 2
    assert (dist / LIC).read_text(encoding="utf-8") == "CLE-DU-POSTE"


def test_nettoie_build_meme_sans_dist(tmp_path):
    (tmp_path / "build" / NOM).mkdir(parents=True)
    outils_build.construire("x.spec", NOM, racine=tmp_path, build_fn=lambda s: 0)
    assert not (tmp_path / "build" / NOM).exists()
