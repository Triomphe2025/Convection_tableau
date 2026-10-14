"""
Vérification Ed25519 pur Python (ed25519_verif.py) contre les vecteurs officiels RFC 8032
(section 7.1) : signatures valides acceptées, altérations rejetées, entrées mal formées rejetées.

Lancement :
    env\\Scripts\\python.exe -m pytest tests/test_ed25519_verif.py -v
"""
import unittest

from ed25519_verif import verifier

# RFC 8032 §7.1 — (clé publique, message, signature)
VECTEURS = [
    ('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
     'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc'
     '61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
    ('3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
     '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e4'
     '58f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
]


class TestVerifier(unittest.TestCase):

    def test_vecteurs_rfc_valides(self):
        for pub, msg, sig in VECTEURS:
            self.assertTrue(verifier(bytes.fromhex(msg), bytes.fromhex(sig), bytes.fromhex(pub)))

    def test_message_altere_rejete(self):
        pub, _, sig = VECTEURS[1]
        self.assertFalse(verifier(b'\x73', bytes.fromhex(sig), bytes.fromhex(pub)))

    def test_signature_alteree_rejetee(self):
        pub, msg, sig = VECTEURS[1]
        brut = bytes.fromhex(sig)
        cassee = brut[:-1] + bytes([brut[-1] ^ 1])
        self.assertFalse(verifier(bytes.fromhex(msg), cassee, bytes.fromhex(pub)))

    def test_mauvaise_cle_publique_rejetee(self):
        _, msg, sig = VECTEURS[1]
        self.assertFalse(verifier(bytes.fromhex(msg), bytes.fromhex(sig), bytes(32)))

    def test_signature_de_mauvaise_longueur_rejetee(self):
        pub, msg, _ = VECTEURS[1]
        self.assertFalse(verifier(bytes.fromhex(msg), b'\x00' * 10, bytes.fromhex(pub)))


if __name__ == '__main__':
    unittest.main()
