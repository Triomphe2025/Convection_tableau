#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_table_compare.py
====================

Controle de conversion : compare un PDF SCANNE (pages = images) avec le PDF
NUMERIQUE cense le reproduire (issu d'Excel, d'une ressaisie, d'un OCR...),
et sort la liste des divergences, cellule par cellule.

Aucune IA generative. Toute la chaine est deterministe et rejouable :
  1. inventaire technique des deux fichiers          (PyMuPDF)
  2. appariement automatique des pages               (difflib sur le texte)
  3. extraction des tableaux
        - cote numerique : couche texte + coordonnees   (PyMuPDF)
        - cote scanne    : lignes du cadre + OCR positionne (OpenCV + Tesseract)
  4. alignement des lignes par sequence, puis diff par champ
  5. classement : IDENTIQUE / BENIN (artefact OCR) / A_VERIFIER
  6. rapport JSON + CSV + HTML

Dependances :
    pip install pymupdf opencv-python-headless numpy
    apt install tesseract-ocr tesseract-ocr-fra      (ou equivalent Windows)

Usage :
    python pdf_table_compare.py scan.pdf numerique.pdf -o rapport/
    python pdf_table_compare.py scan.pdf numerique.pdf --colonnes BORNE COULEUR SIGNAL JARRETIERES
"""

from __future__ import annotations

import argparse
import csv
import difflib
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from pathlib import Path

import cv2
import numpy as np
import pymupdf


# =============================================================================
#  Parametres
# =============================================================================

@dataclass
class Config:
    colonnes: list[str] = field(default_factory=lambda: [
        "BORNE", "COULEUR", "SIGNAL", "JARRETIERES"])
    dpi: int = 300                 # rendu des pages scannees
    lang: str = "fra"              # langue Tesseract
    psm: str = "6"                 # 6 = bloc de texte uniforme : bon pour un tableau
    seuil_benin: float = 0.90      # similarite au-dela de laquelle on dit "artefact OCR"
    seuil_appariement: float = 0.45
    tol_ligne_num: float = 3.0     # points  : regroupement vertical cote numerique
    tol_ligne_scan: float = 12.0   # pixels  : idem cote scanne
    # motif des cles de ligne valides (ici : 10, A01, 12B, P1...)
    motif_cle: str = r"^[A-Z]?[0-9]{1,3}[A-Z]?$"

    @property
    def cols(self) -> list[str]:
        return [c.lower() for c in self.colonnes]


# confusions de caracteres typiques d'un OCR sur imprimante matricielle / fax
OCR_EQUIV = [("0", "O"), ("0", "Q"), ("1", "I"), ("1", "L"), ("5", "S"),
             ("8", "B"), ("2", "Z"), ("6", "G"), ("7", "T"), ("4", "A"),
             ("V", "Y"), ("U", "V")]


# =============================================================================
#  Normalisation
# =============================================================================

def norm(s: str) -> str:
    """Canonicalisation d'affichage : accents, casse, espaces, ponctuation OCR."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper().replace("’", "'").replace("`", "'")
    s = re.sub(r"[^A-Z0-9+/.\-' ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fold(s: str) -> str:
    """Normalisation agressive : on replie les confusions OCR et on ote les espaces."""
    s = norm(s)
    for chiffre, lettre in OCR_EQUIV:
        s = s.replace(lettre, chiffre)
    return s.replace(" ", "")


def sim(a: str, b: str) -> float:
    # autojunk=False est indispensable : au-dela de 200 elements, l'heuristique
    # par defaut de difflib traite les caracteres frequents comme du bruit et
    # effondre le score de deux pages pourtant quasi identiques.
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


# =============================================================================
#  Inventaire technique
# =============================================================================

def inventaire(path: str) -> dict:
    """Dit si un PDF est scanne (images) ou numerique (couche texte), et comment."""
    doc = pymupdf.open(path)
    n_txt = n_img = 0
    dpis: list[int] = []
    for page in doc:
        n_txt += len(page.get_text().strip())
        for img in page.get_images(full=True):
            n_img += 1
            try:
                w, h = img[2], img[3]
                dpis.append(round(w / (page.rect.width / 72)))
            except Exception:
                pass
    meta = doc.metadata or {}
    car_par_page = n_txt / max(len(doc), 1)
    return {
        "fichier": Path(path).name,
        "pages": len(doc),
        "caracteres_texte": n_txt,
        "caracteres_par_page": round(car_par_page, 1),
        "images": n_img,
        "dpi_estime": int(np.median(dpis)) if dpis else None,
        "producteur": meta.get("producer") or "",
        "createur": meta.get("creator") or "",
        # un PDF "image" a beaucoup d'images et quasi pas de texte
        "nature": ("SCANNE (image, sans couche texte)" if car_par_page < 50 and n_img >= len(doc)
                   else "NUMERIQUE (couche texte exploitable)" if car_par_page >= 50
                   else "MIXTE / INDETERMINE"),
    }


# =============================================================================
#  Extraction : cote numerique (couche texte)
# =============================================================================

def mots_numerique(doc, page_no: int) -> list[tuple]:
    return [(w[0], w[1], w[2], w[3], w[4]) for w in doc[page_no].get_text("words")]


def bornes_depuis_entete(mots, cfg: Config):
    """Deduit les frontieres de colonnes de la position des libelles d'entete."""
    tetes: dict[str, tuple[float, float]] = {}
    for x0, y0, x1, y1, t in mots:
        k = norm(t)
        for lab in cfg.colonnes:
            if k == norm(lab) and lab not in tetes:
                tetes[lab] = (x0, x1)
    if len(tetes) < len(cfg.colonnes):
        return None
    centres = [sum(tetes[c]) / 2 for c in cfg.colonnes]
    return ([0.0]
            + [(centres[i] + centres[i + 1]) / 2 for i in range(len(centres) - 1)]
            + [1e6])


# =============================================================================
#  Extraction : cote scanne (image)
# =============================================================================

def page_en_image(doc, page_no: int, dpi: int, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    doc[page_no].get_pixmap(dpi=dpi).save(str(dest))
    return dest


def bornes_depuis_traits(png: Path, min_frac: float = 0.35):
    """Extrait les traits verticaux du cadre par morphologie -> frontieres."""
    img = cv2.imread(str(png), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    h, _ = img.shape
    bw = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    noyau = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, int(h * min_frac))))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, noyau)
    cols = np.where(vert.sum(axis=0) > 0)[0]
    if len(cols) == 0:
        return None
    groupes, cur = [], [cols[0]]
    for c in cols[1:]:
        if c - cur[-1] <= 5:
            cur.append(c)
        else:
            groupes.append(float(np.mean(cur))); cur = [c]
    groupes.append(float(np.mean(cur)))
    return groupes if len(groupes) >= 2 else None


def mots_ocr(png: Path, cfg: Config) -> list[tuple]:
    """Tesseract en sortie TSV : chaque mot avec sa boite et sa confiance."""
    res = subprocess.run(
        ["tesseract", str(png), "-", "-l", cfg.lang, "--psm", cfg.psm, "tsv"],
        capture_output=True, text=True)
    mots = []
    for ligne in res.stdout.splitlines()[1:]:
        f = ligne.split("\t")
        if len(f) < 12:
            continue
        txt = f[11].strip()
        try:
            conf = float(f[10])
        except ValueError:
            continue
        if conf < 0 or not txt:
            continue
        x, y, w, h = map(int, f[6:10])
        mots.append((x, y, x + w, y + h, txt))
    return mots


# =============================================================================
#  Mise en lignes / colonnes (commun aux deux cotes)
# =============================================================================

def grouper_lignes(mots, tol: float):
    ordonnes = sorted(mots, key=lambda t: (t[1], t[0]))
    lignes, cur, ref = [], [], None
    for m in ordonnes:
        cy = (m[1] + m[3]) / 2
        if ref is None or abs(cy - ref) <= tol:
            cur.append(m)
            ref = cy if ref is None else (ref + cy) / 2
        else:
            lignes.append(cur); cur = [m]; ref = cy
    if cur:
        lignes.append(cur)
    return lignes


def ranger_en_colonnes(lignes, bornes, cfg: Config) -> list[dict]:
    out = []
    for ln in lignes:
        cases = {c: [] for c in cfg.cols}
        for m in sorted(ln, key=lambda t: t[0]):
            cx = (m[0] + m[2]) / 2
            for i, c in enumerate(cfg.cols):
                if bornes[i] <= cx < bornes[i + 1]:
                    cases[c].append(m[4])
                    break
        row = {c: " ".join(cases[c]).strip() for c in cfg.cols}
        if any(row.values()):
            out.append(row)
    return out


def lignes_de_donnees(rows, cfg: Config) -> list[dict]:
    """Ecarte entetes, cartouches et lignes parasites : on garde les cles plausibles."""
    motif = re.compile(cfg.motif_cle)
    cle = cfg.cols[0]
    return [r for r in rows if motif.match(norm(r[cle]).replace(" ", ""))]


def extraire_numerique(doc, page_no: int, cfg: Config) -> list[dict]:
    mots = mots_numerique(doc, page_no)
    bornes = bornes_depuis_entete(mots, cfg)
    if bornes is None:
        return []
    return lignes_de_donnees(
        ranger_en_colonnes(grouper_lignes(mots, cfg.tol_ligne_num), bornes, cfg), cfg)


def extraire_scan(png: Path, cfg: Config) -> list[dict]:
    mots = mots_ocr(png, cfg)
    if not mots:
        return []
    traits = bornes_depuis_traits(png)
    bornes = None
    if traits and len(traits) >= len(cfg.colonnes) + 1:
        interieurs = traits[1:-1][:len(cfg.colonnes) - 1]
        if len(interieurs) == len(cfg.colonnes) - 1:
            bornes = [traits[0]] + interieurs + [traits[-1]]
    if bornes is None:                       # repli : on se cale sur l'entete lue
        bornes = bornes_depuis_entete(mots, cfg)
    if bornes is None:
        return []
    return lignes_de_donnees(
        ranger_en_colonnes(grouper_lignes(mots, cfg.tol_ligne_scan), bornes, cfg), cfg)


# =============================================================================
#  Appariement des pages
# =============================================================================

def apparier_pages(txt_scan: list[str], txt_num: list[str], seuil: float = 0.30):
    """Apparie les pages deux a deux en preservant l'ordre (les deux PDF peuvent
    ne pas avoir le meme nombre de pages : pagination, pages de garde...)."""
    a = [fold(t)[:400] for t in txt_scan]
    b = [fold(t)[:400] for t in txt_num]
    paires, restants_b = [], list(range(len(b)))
    for i in range(len(a)):
        meilleur, score = None, 0.0
        for j in restants_b[:6]:             # fenetre glissante : l'ordre est conserve
            s = sim(a[i], b[j])
            if s > score:
                meilleur, score = j, s
        if meilleur is not None and score >= seuil:
            paires.append((i, meilleur, round(score, 3)))
            restants_b = [j for j in restants_b if j > meilleur]
        else:
            paires.append((i, None, 0.0))
    return paires


# =============================================================================
#  Comparaison
# =============================================================================

def signature(r: dict, cfg: Config) -> str:
    c = cfg.cols
    return fold(r[c[0]]) + "|" + fold(r[c[2] if len(c) > 2 else c[-1]])[:18]


def aligner(rs: list[dict], rn: list[dict], cfg: Config):
    """Alignement de sequence : resiste a une cle mal lue par l'OCR."""
    a = [signature(r, cfg) for r in rs]
    b = [signature(r, cfg) for r in rn]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    paires = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            paires += list(zip(range(i1, i2), range(j1, j2)))
        elif tag == "replace":
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                i, j = i1 + k, j1 + k
                if sim(a[i], b[j]) >= cfg.seuil_appariement:
                    paires.append((i, j))
                else:
                    paires += [(i, None), (None, j)]
            paires += [(i, None) for i in range(i1 + n, i2)]
            paires += [(None, j) for j in range(j1 + n, j2)]
        elif tag == "delete":
            paires += [(i, None) for i in range(i1, i2)]
        elif tag == "insert":
            paires += [(None, j) for j in range(j1, j2)]
    return paires


def comparer_ligne(rsc: dict, rnum: dict, cfg: Config):
    """Diff champ par champ, avec tolerance au debordement de colonne."""
    c = cfg.cols
    # si le texte complet de la ligne concorde, un ecart par colonne n'est qu'un
    # probleme de decoupage vertical, pas une divergence de contenu
    bloc_ok = "".join(fold(rsc[k]) for k in c) == "".join(fold(rnum[k]) for k in c)
    res = []
    for k in c:
        a, b = norm(rsc[k]), norm(rnum[k])
        if a == b:
            res.append((k, "IDENTIQUE", a, b))
        elif bloc_ok:
            res.append((k, "BENIN_COLONNE", a, b))
        elif fold(a) == fold(b) or sim(a, b) >= cfg.seuil_benin:
            res.append((k, "BENIN_OCR", a, b))
        elif not a:
            res.append((k, "A_VERIFIER_VIDE_SCAN", a, b))
        elif not b:
            res.append((k, "A_VERIFIER_VIDE_NUM", a, b))
        else:
            res.append((k, "A_VERIFIER", a, b))
    return res


# =============================================================================
#  Pilotage
# =============================================================================

def executer(pdf_scan: str, pdf_num: str, sortie: Path, cfg: Config) -> dict:
    sortie.mkdir(parents=True, exist_ok=True)
    tmp = sortie / "_pages"

    inv_s, inv_n = inventaire(pdf_scan), inventaire(pdf_num)
    print("== Inventaire ==")
    for inv in (inv_s, inv_n):
        print(f"  {inv['fichier']:<34} {inv['pages']:>3} p.  "
              f"{inv['caracteres_par_page']:>8} car./p.  "
              f"{inv['images']:>3} img  -> {inv['nature']}")

    d_s, d_n = pymupdf.open(pdf_scan), pymupdf.open(pdf_num)

    # --- pages en images + OCR brut, pour l'appariement ---
    print("\n== OCR du document scanne ==")
    ocr_pages: list[str] = []
    pngs: list[Path] = []
    for i in range(len(d_s)):
        png = page_en_image(d_s, i, cfg.dpi, tmp / f"scan_{i+1:03d}.png")
        pngs.append(png)
        ocr_pages.append(" ".join(m[4] for m in mots_ocr(png, cfg)))
        print(f"\r  page {i+1}/{len(d_s)}", end="", flush=True)
    print()

    txt_num = [p.get_text() for p in d_n]
    paires = apparier_pages(ocr_pages, txt_num)

    print("\n== Appariement des pages ==")
    for i, j, s in paires:
        cible = f"num p{j+1} (score {s})" if j is not None else "AUCUNE CORRESPONDANCE"
        print(f"  scan p{i+1:>2}  ->  {cible}")

    # --- comparaison des pages appariees ---
    total = {"IDENTIQUE": 0, "BENIN_OCR": 0, "BENIN_COLONNE": 0,
             "A_VERIFIER": 0, "A_VERIFIER_VIDE_SCAN": 0, "A_VERIFIER_VIDE_NUM": 0}
    orphelines = {"scan": 0, "numerique": 0}
    anomalies: list[dict] = []
    detail_pages: list[dict] = []

    print("\n== Comparaison des tableaux ==")
    print(f"  {'pages':<16}{'l.scan':>7}{'l.num':>7}{'cell.':>7}"
          f"{'ident.':>8}{'benin':>7}{'a verif':>9}{'orph.':>7}")
    print("  " + "-" * 68)

    for i, j, _ in paires:
        if j is None:
            continue
        rs = extraire_scan(pngs[i], cfg)
        rn = extraire_numerique(d_n, j, cfg)
        if not rs and not rn:
            continue                          # page sans tableau (garde, sommaire...)

        label = f"scan p{i+1} / num p{j+1}"
        pg = {k: 0 for k in total}
        orph = 0

        for a, b in aligner(rs, rn, cfg):
            if a is None or b is None:
                orph += 1
                cote = "numerique" if a is None else "scan"
                orphelines[cote] += 1
                src = rn[b] if a is None else rs[a]
                anomalies.append({
                    "pages": label, "statut": "LIGNE_ORPHELINE",
                    "presente_dans": cote, "cle": src[cfg.cols[0]],
                    "champ": "", "scan": "", "numerique": "",
                    "contenu": " | ".join(src[k] for k in cfg.cols)})
                continue
            for champ, statut, va, vb in comparer_ligne(rs[a], rn[b], cfg):
                pg[statut] += 1
                total[statut] += 1
                if statut.startswith("A_VERIFIER"):
                    anomalies.append({
                        "pages": label, "statut": statut, "presente_dans": "",
                        "cle": rn[b][cfg.cols[0]], "champ": champ,
                        "scan": va, "numerique": vb, "contenu": ""})

        cells = sum(pg.values())
        benin = pg["BENIN_OCR"] + pg["BENIN_COLONNE"]
        averif = cells - pg["IDENTIQUE"] - benin
        detail_pages.append({"pages": label, "lignes_scan": len(rs),
                             "lignes_num": len(rn), "cellules": cells,
                             "identiques": pg["IDENTIQUE"], "benins": benin,
                             "a_verifier": averif, "orphelines": orph})
        print(f"  {label:<16}{len(rs):>7}{len(rn):>7}{cells:>7}"
              f"{pg['IDENTIQUE']:>8}{benin:>7}{averif:>9}{orph:>7}")

    cells = sum(total.values())
    benin = total["BENIN_OCR"] + total["BENIN_COLONNE"]
    averif = cells - total["IDENTIQUE"] - benin
    synthese = {
        "inventaire_scan": inv_s, "inventaire_numerique": inv_n,
        "cellules": cells, "identiques": total["IDENTIQUE"],
        "benins": benin, "a_verifier": averif,
        "lignes_orphelines": orphelines,
        "concordance_stricte_pct": round(100 * total["IDENTIQUE"] / max(cells, 1), 2),
        "concordance_apres_ocr_pct": round(100 * (total["IDENTIQUE"] + benin) / max(cells, 1), 2),
        "detail_pages": detail_pages,
    }

    print("  " + "-" * 68)
    print(f"  {'TOTAL':<16}{'':>7}{'':>7}{cells:>7}"
          f"{total['IDENTIQUE']:>8}{benin:>7}{averif:>9}"
          f"{orphelines['scan']+orphelines['numerique']:>7}")
    print(f"\n  Concordance stricte    : {synthese['concordance_stricte_pct']} %")
    print(f"  Concordance apres OCR  : {synthese['concordance_apres_ocr_pct']} %")
    print(f"  Cellules a verifier    : {averif}")
    print(f"  Lignes orphelines      : scan {orphelines['scan']}, "
          f"numerique {orphelines['numerique']}")

    ecrire_rapports(sortie, synthese, anomalies, cfg)
    shutil.rmtree(tmp, ignore_errors=True)
    return synthese


# =============================================================================
#  Rapports
# =============================================================================

def ecrire_rapports(sortie: Path, synthese: dict, anomalies: list[dict], cfg: Config):
    (sortie / "synthese.json").write_text(
        json.dumps(synthese, ensure_ascii=False, indent=2), encoding="utf-8")
    (sortie / "anomalies.json").write_text(
        json.dumps(anomalies, ensure_ascii=False, indent=2), encoding="utf-8")

    champs = ["pages", "statut", "presente_dans", "cle", "champ",
              "scan", "numerique", "contenu"]
    with (sortie / "anomalies.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=champs, delimiter=";")
        w.writeheader()
        w.writerows(anomalies)

    cellules = [a for a in anomalies if a["statut"] != "LIGNE_ORPHELINE"]
    lignes = [a for a in anomalies if a["statut"] == "LIGNE_ORPHELINE"]

    def tableau(rows, cols, titres):
        th = "".join(f"<th>{html.escape(t)}</th>" for t in titres)
        tr = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(r.get(c, '')))}</td>" for c in cols) + "</tr>"
            for r in rows)
        return f"<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>"

    doc = f"""<!doctype html><html lang="fr"><meta charset="utf-8">
<title>Controle de conversion</title>
<style>
 body{{font:14px/1.5 system-ui,sans-serif;margin:2rem auto;max-width:1100px;padding:0 1rem}}
 h1{{font-size:1.5rem}} h2{{font-size:1.1rem;margin-top:2rem}}
 table{{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:13px}}
 th,td{{border:1px solid #d0d0d0;padding:.3rem .5rem;text-align:left;vertical-align:top}}
 th{{background:#f2f2f2}}
 .kpi{{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}}
 .kpi div{{border:1px solid #d0d0d0;border-radius:8px;padding:.7rem 1rem;min-width:150px}}
 .kpi b{{display:block;font-size:1.5rem}}
 code{{background:#f4f4f4;padding:0 .25rem}}
</style>
<h1>Controle de conversion scan &rarr; numerique</h1>
<p><code>{html.escape(synthese['inventaire_scan']['fichier'])}</code> ({synthese['inventaire_scan']['nature']})
 vs <code>{html.escape(synthese['inventaire_numerique']['fichier'])}</code> ({synthese['inventaire_numerique']['nature']})</p>
<div class="kpi">
 <div><b>{synthese['concordance_stricte_pct']} %</b>concordance stricte</div>
 <div><b>{synthese['concordance_apres_ocr_pct']} %</b>apres neutralisation OCR</div>
 <div><b>{synthese['a_verifier']}</b>cellules a verifier</div>
 <div><b>{synthese['lignes_orphelines']['scan'] + synthese['lignes_orphelines']['numerique']}</b>lignes orphelines</div>
</div>
<h2>Detail par page</h2>
{tableau(synthese['detail_pages'],
         ['pages','lignes_scan','lignes_num','cellules','identiques','benins','a_verifier','orphelines'],
         ['Pages','Lignes scan','Lignes num.','Cellules','Identiques','Benins','A verifier','Orphelines'])}
<h2>Cellules a verifier ({len(cellules)})</h2>
{tableau(cellules, ['pages','cle','champ','statut','scan','numerique'],
         ['Pages','Cle','Champ','Statut','Valeur scan','Valeur numerique'])}
<h2>Lignes orphelines ({len(lignes)})</h2>
{tableau(lignes, ['pages','presente_dans','cle','contenu'],
         ['Pages','Presente dans','Cle','Contenu'])}
</html>"""
    (sortie / "rapport.html").write_text(doc, encoding="utf-8")
    print(f"\n  Rapports ecrits dans {sortie}/ : "
          f"rapport.html, anomalies.csv, anomalies.json, synthese.json")


# =============================================================================
#  CLI
# =============================================================================

def main(argv=None):
    p = argparse.ArgumentParser(
        description="Controle de conversion entre un PDF scanne et sa version numerique.")
    p.add_argument("scan", help="PDF scanne (pages = images)")
    p.add_argument("numerique", help="PDF numerique cense le reproduire")
    p.add_argument("-o", "--sortie", default="rapport_comparaison")
    p.add_argument("--colonnes", nargs="+",
                   default=["BORNE", "COULEUR", "SIGNAL", "JARRETIERES"],
                   help="libelles d'entete des colonnes, dans l'ordre")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--lang", default="fra")
    p.add_argument("--psm", default="6")
    p.add_argument("--motif-cle", default=r"^[A-Z]?[0-9]{1,3}[A-Z]?$",
                   help="expression reguliere des cles de ligne valides")
    a = p.parse_args(argv)

    if not shutil.which("tesseract"):
        sys.exit("Tesseract est introuvable dans le PATH. Installez-le d'abord.")

    cfg = Config(colonnes=a.colonnes, dpi=a.dpi, lang=a.lang,
                 psm=a.psm, motif_cle=a.motif_cle)
    executer(a.scan, a.numerique, Path(a.sortie), cfg)


if __name__ == "__main__":
    main()
