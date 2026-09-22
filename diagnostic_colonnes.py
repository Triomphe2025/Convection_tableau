"""Diagnostic précis des erreurs de colonnes dans l'Excel généré par Claude Vision."""
import openpyxl
from pathlib import Path

xlsx = Path(r'C:\Users\Triomphe Tchounda\Downloads\document test\DOC FINAL\TACHE4_VD23111PE161\tous_les_borniers.xlsx')
wb = openpyxl.load_workbook(str(xlsx), data_only=True)
ws = wb['Borniers']
rows_all = list(ws.iter_rows(values_only=True))

SEP = "-" * 105


def row_str(r):
    vals = [str(c).strip()[:24] if c is not None else '' for c in r]
    return '|'.join(v.ljust(24) for v in (vals + [''] * 4)[:4])


# ── 1. Afficher le début des 6 premiers tableaux ─────────────────────────────
print("=== DEBUT DES 6 PREMIERS TABLEAUX ===")
found = 0
for i, row in enumerate(rows_all):
    vals = [str(c).strip() if c is not None else '' for c in row]
    joined = ' '.join(vals).upper()
    if 'FIL' in joined and 'TENANT' in joined and 'SIGNAL' in joined and 'ABOUTISSANT' in joined:
        found += 1
        if found > 6:
            break
        print(f"\n--- TABLEAU {found} (ligne Excel {i+1}) ---")
        print(f"{'FIL':24}|{'TENANT':24}|{'SIGNAL':24}|{'ABOUTISSANT':24}")
        print(SEP)
        for j in range(i + 1, min(i + 20, len(rows_all))):
            r = rows_all[j]
            vals2 = [str(c).strip() if c is not None else '' for c in r]
            if any(v for v in vals2):
                print(row_str(r))

# ── 2. Chercher les lignes où SIGNAL ressemble à du TENANT (contient CDG/EPL/CXM) ──
print("\n\n=== LIGNES SUSPECTES : valeur TENANT dans SIGNAL ===")
print(f"{'FIL':24}|{'TENANT':24}|{'SIGNAL':24}|{'ABOUTISSANT':24}")
print(SEP)
n = 0
for i, row in enumerate(rows_all):
    vals = [str(c).strip() if c is not None else '' for c in row]
    if len(vals) < 3:
        continue
    signal = vals[2] if len(vals) > 2 else ''
    # Un signal qui ressemble à un tenant (contient des patterns de borne)
    import re
    # Pattern TENANT typique : CDG xxx, EPL xxx, CXM xxx, SIV xxx
    if re.search(r'\b(CDG|EPL|CXM|SIV|SRV)\b', signal, re.I):
        if n < 20:
            print(f"L{i+1:4d} " + row_str(row))
        n += 1
print(f"Total : {n} lignes avec pattern TENANT dans colonne SIGNAL")

# ── 3. Lignes où ABOUTISSANT est vide mais SIGNAL est rempli ──────────────────
print("\n\n=== LIGNES : SIGNAL rempli mais ABOUTISSANT vide ===")
print(f"{'FIL':24}|{'TENANT':24}|{'SIGNAL':24}|{'ABOUTISSANT':24}")
print(SEP)
n2 = 0
for i, row in enumerate(rows_all):
    vals = [str(c).strip() if c is not None else '' for c in row]
    if len(vals) < 4:
        continue
    signal = vals[2] if len(vals) > 2 else ''
    aboutissant = vals[3] if len(vals) > 3 else ''
    fil = vals[0] if vals else ''
    # Exclure en-têtes et pieds
    if 'FIL' in fil.upper() or 'SIEMENS' in fil.upper():
        continue
    if signal and not aboutissant and fil:
        if n2 < 20:
            print(f"L{i+1:4d} " + row_str(row))
        n2 += 1
print(f"Total : {n2} lignes avec SIGNAL rempli et ABOUTISSANT vide")
