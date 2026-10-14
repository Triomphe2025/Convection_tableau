"""
Encodage léger des textes sensibles embarqués (la consigne envoyée à Claude), pour qu'ils
n'apparaissent pas en clair dans l'exe. Ce N'EST PAS un chiffrement : juste un brouillage
réversible qui évite une lecture directe avec un éditeur de texte.

Au build, `python textes_proteges.py <source.txt> <sortie.dat>` encode le fichier lisible ;
à l'exécution, `decoder_fichier` le relit. Le .txt lisible reste dans le dépôt (jamais
embarqué dans l'exe) ; seul le .dat encodé est embarqué.
"""
import sys
from pathlib import Path

_CLE = b'TriosSeconverter-1.8'


def _brouiller(donnees: bytes) -> bytes:
    return bytes(o ^ _CLE[i % len(_CLE)] for i, o in enumerate(donnees))


def encoder(texte: str) -> bytes:
    import base64
    return base64.b85encode(_brouiller(texte.encode('utf-8')))


def decoder(blob: bytes) -> str:
    import base64
    return _brouiller(base64.b85decode(blob)).decode('utf-8')


def decoder_fichier(chemin: Path) -> str:
    return decoder(Path(chemin).read_bytes())


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 1
    source, sortie = Path(argv[0]), Path(argv[1])
    blob = encoder(source.read_text(encoding='utf-8'))
    sortie.write_bytes(blob)
    assert decoder(blob) == source.read_text(encoding='utf-8'), "aller-retour faux"
    print(f"Encodé : {source.name} → {sortie.name} ({len(blob)} octets)")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
