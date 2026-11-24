"""Résumé de l'écran Terminé (phase 2D, module pur) : dérive les chiffres clés et « ce qui demande
ton attention » du résumé de conversion + des points à relire. Aucune lecture de fichier, aucun Qt.
"""


def cout_fr(usd) -> str:
    return f"{float(usd or 0):.2f} $".replace(".", ",")


def duree_h(secondes) -> str:
    """Durée lisible : « 1 h 18 min », « 18 min » ou « 42 s »."""
    s = int(secondes or 0)
    h, m = s // 3600, (s % 3600) // 60
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min"
    return f"{s} s"


def ligne_entete(resume: dict) -> str:
    parts = [resume.get("fichier", "")]
    if resume.get("pages_total"):
        parts.append(f"{resume['pages_total']} pages")
    if resume.get("duree_s") is not None:
        parts.append(duree_h(resume["duree_s"]))
    if resume.get("cout_usd") is not None:
        parts.append(cout_fr(resume["cout_usd"]))
    return " · ".join(p for p in parts if p)


def carte_tableaux(resume: dict):
    return str(resume.get("tableaux", 0)), "un par bornier, pied de page compris"


def carte_pages(resume: dict):
    n = resume.get("natures") or {}
    detail = []
    if n.get("scan"):
        detail.append(f"{n['scan']} scans")
    if n.get("vectoriel"):
        detail.append(f"{n['vectoriel']} vectorielles")
    if n.get("texte_cache"):
        detail.append(f"{n['texte_cache']} texte caché")
    return str(resume.get("pages_total", 0)), " · ".join(detail)


def carte_points(points: list):
    cellules = [p for p in points if p.get("cellule_excel")]
    pages = {p.get("page") for p in cellules if p.get("page")}
    return len(cellules), f"sur {len(pages)} pages · surlignés en orange dans l'Excel"


def carte_cout(resume: dict):
    detail = []
    if resume.get("duree_s") is not None:
        detail.append(duree_h(resume["duree_s"]))
    if resume.get("pages_servies_cache"):
        detail.append(f"{resume['pages_servies_cache']} pages servies par le cache")
    return cout_fr(resume.get("cout_usd", 0)), " · ".join(detail)


def attention(points: list) -> list:
    """Éléments de « Ce qui demande ton attention » : pages signalées, cellules qui s'écartent,
    résultat du contrôle Claude / Tesseract."""
    items = []
    degradees = [p for p in points if p.get("sorte") == "page_degradee"]
    for p in degradees:
        page = p.get("page_imprimee") or p.get("page")
        items.append({
            "niveau": "alerte", "action": "voir",
            "titre": f"Page {page} · bornier {p.get('bornier') or '?'} — scan défectueux",
            "detail": p.get("raison") or ""})
    ecarts = [p for p in points if p.get("sorte") in ("qualite", "conservation")]
    if ecarts:
        items.append({
            "niveau": "attention", "action": "relire",
            "titre": f"{len(ecarts)} cellules qui s'écartent de leurs voisines",
            "detail": ecarts[0].get("raison") or ""})
    if degradees:
        items.append({
            "niveau": "alerte", "action": None,
            "titre": f"Contrôle Claude / Tesseract : {len(degradees)} page(s) dégradée(s)",
            "detail": ""})
    else:
        items.append({
            "niveau": "ok", "action": None,
            "titre": "Contrôle Claude / Tesseract : aucune page dégradée",
            "detail": "Les deux lectures concordent sur toutes les pages scannées."})
    return items
