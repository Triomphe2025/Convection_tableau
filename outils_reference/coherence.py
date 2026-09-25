"""Detecteur sans IA : un meme code ecrit de deux facons dans un document,
a une confusion de caractere pres -> la forme minoritaire est suspecte."""
import re
from collections import Counter
CONF=[('1','I'),('1','L'),('I','L'),('0','O'),('0','D'),('O','D'),('5','S'),('8','B'),('2','Z'),
      ('6','G'),('P','F'),('R','K'),('E','F'),('C','G'),('H','K'),('U','V'),('V','Y'),('7','T'),('M','N')]
def variantes(t):
    for i,ch in enumerate(t):
        for a,b in CONF:
            if ch==a: yield t[:i]+b+t[i+1:]
            elif ch==b: yield t[:i]+a+t[i+1:]
        yield t[:i]+t[i+1:]                      # caractere en trop
def suspects(cellules, ratio=1.5):
    """cellules: liste de (id, texte). Retourne {id: [(forme_suspecte, forme_majoritaire)]}"""
    tok=lambda s: re.findall(r"[A-Z0-9][A-Z0-9'\"_/.-]{2,}", s.upper())
    freq=Counter(t for _,s in cellules for t in tok(s))
    out={}
    for cid,s in cellules:
        for t in tok(s):
            best=max(((freq[v],v) for v in variantes(t) if freq[v]>0), default=(0,None))
            if best[1] and best[0]>=2 and best[0]>=ratio*freq[t]:
                out.setdefault(cid,[]).append((t,best[1]))
    return out
