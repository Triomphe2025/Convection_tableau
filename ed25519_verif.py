"""Vérification de signature Ed25519 en pur Python (RFC 8032), sans dépendance.

Seule la VÉRIFICATION est ici (clé publique) : c'est ce que l'exe embarque. La
fabrication des clés et des licences se fait à part, avec `cryptography`, sur le poste
privé. Code dérivé de l'implémentation de référence du domaine public (RFC 8032).
"""
import hashlib

_q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_d = (-121665 * pow(121666, _q - 2, _q)) % _q
_I = pow(2, (_q - 1) // 4, _q)


def _recover_x(y, sign):
    if y >= _q:
        return None
    xx = (y * y - 1) * pow(_d * y * y + 1, _q - 2, _q)
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if (x * x - xx) % _q != 0:
        return None
    if (x & 1) != sign:
        x = _q - x
    return x


# Points en coordonnées étendues (X, Y, Z, T) : addition et doublement sans inverse modulaire.
_By = (4 * pow(5, _q - 2, _q)) % _q
_Bx = _recover_x(_By, 0)
_B = (_Bx, _By, 1, (_Bx * _By) % _q)


def _add(P, Q):
    A = ((P[1] - P[0]) * (Q[1] - Q[0])) % _q
    Bv = ((P[1] + P[0]) * (Q[1] + Q[0])) % _q
    C = (2 * P[3] * Q[3] * _d) % _q
    D = (2 * P[2] * Q[2]) % _q
    E, F, G, H = Bv - A, D - C, D + C, Bv + A
    return (E * F % _q, G * H % _q, F * G % _q, E * H % _q)


def _mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    if (P[0] * Q[2] - Q[0] * P[2]) % _q != 0:
        return False
    return (P[1] * Q[2] - Q[1] * P[2]) % _q == 0


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, 'little')
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, (x * y) % _q)


def verifier(message: bytes, signature: bytes, cle_publique: bytes) -> bool:
    """Vrai si la signature de `message` est valide pour `cle_publique` (32 octets)."""
    if len(signature) != 64:
        return False
    A = _decompress(cle_publique)
    if A is None:
        return False
    R = signature[:32]
    s = int.from_bytes(signature[32:], 'little')
    if s >= _L:
        return False
    h = int.from_bytes(hashlib.sha512(R + cle_publique + message).digest(), 'little') % _L
    Rp = _decompress(R)
    if Rp is None:
        return False
    return _equal(_mul(s, _B), _add(Rp, _mul(h, A)))
