"""Diagnostic détaillé : affiche les tableaux avec des colonnes mal assignées."""
import openpyxl
import re
from pathlib import Path

xlsx = Path(r'C:\Users\Triomphe Tchounda\Downloads\document test\DOC FINAL\TACHE4_VD23111PE161\tous_les_borniers.xlsx')
wb = openpyxl.load_workbook(str(xlsx), data_only=True)
ws = wb['Borniers']
rows_all = list(ws.iter_rows(values_only=True))

# Patterns attendus dans chaque colonne pour un répartiteur
# FIL       : chiffres + lettre(s)  ex: "11 N N", "12 B I"
# TENANT    : station + code borne  ex: "CDG D1T 01A", "CXM DA 01"
# SIGNAL    : +/- signal ou texte   ex: "+TCA11-31", "RESERVE CABLEE"
# ABOUTISSANT: station + code borne ex: "EPL D113T 01A"

STATIONS = re.compile(r'\b(CDG|EPL|CXM|SIV|SRV|SIV1)\b', re.I)
SIGNAL_LIKE = re.compile(r'^[+\-]|RESERVE|COMMUN|TRANS|AES|TC |OC|TCA|BAC|DND|DP', re.I)

# Trouver les tableaux où SIGNAL contient du TENANT
print("=" * 90)
print("TABLEAUX OÙ SIGNAL CONTIENT DES DONNÉES DE TYPE TENANT (station CDG/EPL/CXM)")
print("=" * 90)

# Segmenter par tableau
tableau_starts = [i for i, row in enumerate(rows_all)
                  if any('FIL' == str(c).strip().upper() for c in row if c)]

print(f"Nombre de tableaux détectés : {len(tableau_starts)}\n")

for t_idx, start in enumerate(tableau_starts):
    end = tableau_starts[t_idx + 1] if t_idx + 1 < len(tableau_starts) else len(rows_all)
    data_rows = []
    for row in rows_all[start + 1:end]:
        vals = [str(c).strip() if c is not None else '' for c in row]
        if any(v for v in vals):
            data_rows.append(vals)

    # Compter lignes où SIGNAL ressemble à un TENANT
    signal_col_idx = 2
    bad = [r for r in data_rows
           if len(r) > signal_col_idx and STATIONS.search(r[signal_col_idx])]
    good_signal = [r for r in data_rows
                   if len(r) > signal_col_idx and SIGNAL_LIKE.search(r[signal_col_idx])]

    if bad:
        print(f"\n--- TABLEAU {t_idx+1} (ligne Excel {start+1}) ---")
        print(f"  Lignes avec station dans SIGNAL : {len(bad)}/{len(data_rows)}")
        print(f"  {'FIL':<15} {'TENANT':<25} {'SIGNAL (problème)':<35} {'ABOUTISSANT':<25}")
        print("  " + "-" * 100)
        for r in bad[:8]:
            fil = r[0][:14] if r else ''
            ten = r[1][:24] if len(r) > 1 else ''
            sig = r[2][:34] if len(r) > 2 else ''
            abo = r[3][:24] if len(r) > 3 else ''
            print(f"  {fil:<15} {ten:<25} {sig:<35} {abo:<25}")
        # Montrer aussi des bonnes lignes pour comparaison
        if good_signal:
            print(f"  ... et {len(good_signal)} lignes CORRECTES dans ce tableau :")
            for r in good_signal[:3]:
                fil = r[0][:14] if r else ''
                ten = r[1][:24] if len(r) > 1 else ''
                sig = r[2][:34] if len(r) > 2 else ''
                abo = r[3][:24] if len(r) > 3 else ''
                print(f"  {fil:<15} {ten:<25} {sig:<35} {abo:<25}")

print("\n\n" + "=" * 90)
print("RÉSUMÉ PAR TABLEAU")
print("=" * 90)
print(f"{'Tableau':>8} {'Ligne':>6} {'Total':>7} {'Signal OK':>10} {'Station/Signal':>15} {'%OK':>6}")
print("-" * 60)
for t_idx, start in enumerate(tableau_starts):
    end = tableau_starts[t_idx + 1] if t_idx + 1 < len(tableau_starts) else len(rows_all)
    data_rows = []
    for row in rows_all[start + 1:end]:
        vals = [str(c).strip() if c is not None else '' for c in row]
        if any(v for v in vals):
            data_rows.append(vals)
    bad = sum(1 for r in data_rows
              if len(r) > 2 and STATIONS.search(r[2]))
    pct = int(100 * (len(data_rows) - bad) / max(1, len(data_rows)))
    flag = " <<<" if bad > 3 else ""
    print(f"  T{t_idx+1:>5} {start+1:>6} {len(data_rows):>7} {len(data_rows)-bad:>10} {bad:>15} {pct:>5}%{flag}")
