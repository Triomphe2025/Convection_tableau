"""
Ouvre l'interface en mode Claude sans appel API : les réponses enregistrées d'un passage
réel sont rejouées (faux client), pour essayer l'écran de validation à la main.

Outil d'essai hors de l'appli livrée. La relecture (« Relancer l'OCR ») n'a pas de réponse
enregistrée : elle échoue proprement, ce qui permet aussi de voir ce cas à l'écran.
Le dictionnaire (data_dictionary.json) n'est pas enrichi par les pages acceptées.

Lancement :
    env\\Scripts\\python.exe outils_reference\\rejeu_ecran_validation.py [223111PE011]
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJET))

from config import Config  # noqa: E402

MESURES = PROJET / 'mesures'


def faux_client(journal: Path):
    """Client Anthropic qui rend, dans l'ordre, les réponses brutes du journal."""
    reponses = [json.loads(lg)['raw'] for lg in journal.read_text('utf-8').splitlines()
                if lg.strip()]

    class Faux:
        def __init__(self, api_key=None, **kw):
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kw):
            if not reponses:
                raise RuntimeError("rejeu : aucune réponse enregistrée pour cette relecture")
            return SimpleNamespace(
                id='msg_rejeu', content=[SimpleNamespace(type='text', text=reponses.pop(0))],
                stop_reason='end_turn', model=kw['model'],
                usage=SimpleNamespace(input_tokens=0, output_tokens=0,
                                      cache_read_input_tokens=0,
                                      cache_creation_input_tokens=0))
    return Faux


def main(argv=None):
    document = (argv or sys.argv[1:] or ['223111PE011'])[0]
    journaux = sorted(MESURES.glob(f'{document}*_claude-opus-5-5_*/*_claude.jsonl'),
                      key=lambda p: p.stat().st_mtime)
    if not journaux:
        print(f"Aucun journal Claude enregistré pour {document} dans {MESURES}")
        return 1
    print(f"Rejeu de : {journaux[-1]}")
    Config.OCR_MODE = 'claude'
    Config.CLAUDE_API_KEY = 'rejeu-sans-api'
    Config.VALIDATION_INTERACTIVE = True
    from converter import Converter
    from interface import TriosSeconverterApp
    # Une page acceptée enrichit data_dictionary.json : un essai ne doit pas l'écrire.
    with patch('anthropic.Anthropic', faux_client(journaux[-1])), \
            patch.object(Converter, '_apprendre_corrections', lambda self, result: None):
        TriosSeconverterApp().mainloop()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
