import pymupdf
from collections import Counter
def grille(page):
    """Listing imprimante -> liste de lignes texte a positions exactes.
    Chaque span est deja une chaine a chasse fixe ; on le pose a sa colonne de depart."""
    spans=[]
    for b in page.get_text('rawdict')['blocks']:
        for l in b.get('lines',[]):
            for s in l['spans']:
                t=''.join(c['c'] for c in s['chars'])
                if not t.strip('_ '): continue          # traits de cadre
                xs=[c['origin'][0] for c in s['chars']]
                pas=Counter(round(b2-a,2) for a,b2 in zip(xs,xs[1:])).most_common(1)[0][0] if len(xs)>1 else 6.0
                spans.append((s['origin'][1], xs[0], pas, t))
    if not spans: return []
    pas=Counter(p for *_,p,_ in spans).most_common(1)[0][0]
    x0=min(x for _,x,_,_ in spans)
    rows={}
    for y,x,_,t in spans: rows.setdefault(round(y),[]).append((x,t))
    out=[]
    for y in sorted(rows):
        line=[]
        for x,t in sorted(rows[y]):
            k=round((x-x0)/pas)
            if len(line)<k: line+= [' ']*(k-len(line))
            line[k:k+len(t)]=list(t)
        out.append(''.join(line).rstrip())
    return out
