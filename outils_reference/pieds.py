import re, difflib
LAB = re.compile(r"((?:N°|NO)\s?PLAN|P\.?E\.?T\.?|\bCABLE|\bTYPE|INDICE|BORNIER|REF\s+CE)\s*:\s*|(PAGE)\s*:?\s*(?=\w)", re.I)
def champs(txt):
    """toutes les paires LIBELLE : valeur d'une ligne de pied, sans liste figee"""
    txt = txt.replace('|', '  ')
    ms = list(LAB.finditer(txt)); out = {}
    for k, m in enumerate(ms):
        fin = ms[k+1].start() if k+1 < len(ms) else len(txt)
        v = txt[m.end():fin].strip()
        key = re.sub(r'\s+', ' ', (m.group(1) or m.group(2)).upper()).replace('NO PLAN', 'N° PLAN').replace('N°PLAN', 'N° PLAN').replace('P.E.T.', 'PET').replace('P.E.T', 'PET')
        if v: out[key] = ' '.join(v.split())
    return out
def pages_ref_txt(path):
    pages, cur = [], {}
    for l in open(path, encoding='utf-8', errors='replace'):
        if LAB.search(l) and ('PLAN' in l.upper() or 'CABLE' in l.upper() or 'P.E.T' in l.upper() or 'TYPE' in l.upper()):
            cur.update(champs(l))
            if 'PLAN' in l.upper(): pages.append(cur); cur = {}
    return pages
def pages_xls(feet):
    pages, cur, rows = [], {}, []
    for row, j in feet:
        cur.update(champs(j)); rows.append(row)
        if 'PLAN' in j.upper(): pages.append((rows, cur)); cur, rows = {}, []
    return pages
def comparer_pieds(ref, xls):
    """ref: [dict], xls: [(rows, dict)] -> ecarts"""
    a = [r.get('PAGE', '') + '|' + r.get('CABLE', r.get('BORNIER', '')) for r in ref]
    b = [d.get('PAGE', '') + '|' + d.get('CABLE', d.get('BORNIER', '')) for _, d in xls]
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == 'insert' or op == 'delete': continue
        for i, j in zip(range(i1, i2), range(j1, j2)):
            r, (rows, d) = ref[i], xls[j]
            for k in sorted(set(r) & set(d)) + [k for k in set(r) - set(d)]:
                va, vb = ' '.join(r.get(k, '').split()), ' '.join(d.get(k, '').split())
                if va.replace(' ', '') != vb.replace(' ', ''):
                    out.append({'page': d.get('PAGE', '?'), 'rows': rows, 'champ': k, 'orig': va, 'xls': vb})
    return out
