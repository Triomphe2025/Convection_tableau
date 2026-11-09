"""
Capture d'écran d'une page de l'interface — outil de revue visuelle.

Hors de l'exe : ce fichier n'est jamais ajouté à MODULES_PROJET du .spec. Il sert à
comparer l'interface avant/après une retouche visuelle (couleurs, contraste, flèches).

Usage :
    python outils/capture_interface.py <page_id> <sortie.png> [--workflow MODE]

<page_id> : accueil, stepper, dessins, mixte, dashboard, params, ocr, format, options, aide
            ("ocr" = page Mode OCR). La fenêtre est ouverte en 1060x760, la page demandée
            affichée, puis la fenêtre est photographiée (PIL.ImageGrab) dans le fichier de
            sortie. Lancer depuis la racine du dépôt (ou d'un worktree) pour l'« avant ».
"""
import sys
from pathlib import Path

# interface.py est à la racine du dépôt (ou du worktree) : un cran au-dessus de outils/.
RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))


def capturer(page_id: str, sortie: Path, workflow: str = "") -> None:
    import interface
    from PIL import ImageGrab

    app = interface.TriosSeconverterApp()
    app.geometry("1060x760+60+40")
    app.update_idletasks()
    app.update()

    if workflow:
        # _select_workflow(mode, couleur) ; la couleur n'affecte pas la capture.
        app._select_workflow(workflow, interface.COL_ACC)
        app.update()

    if page_id not in app._pages:
        app.destroy()
        raise SystemExit(f"page inconnue : {page_id} ({', '.join(app._pages)})")
    app._show_page(page_id)

    # La fenêtre doit être au premier plan pour qu'ImageGrab la saisisse (pas ce qui est dessous).
    app.deiconify()
    app.lift()
    app.wm_attributes('-topmost', True)
    app.focus_force()
    app.update_idletasks()
    app.update()
    app.after(500, app.quit)
    app.mainloop()
    app.update_idletasks()
    app.update()

    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    sortie.parent.mkdir(parents=True, exist_ok=True)
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(sortie)
    app.destroy()
    print(f"capture : {sortie}  ({w}x{h})")


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    wf = ""
    if '--workflow' in sys.argv:
        wf = sys.argv[sys.argv.index('--workflow') + 1]
    if len(args) != 2:
        raise SystemExit("usage : python outils/capture_interface.py <page_id> <sortie.png> "
                         "[--workflow MODE]")
    capturer(args[0], Path(args[1]), wf)
