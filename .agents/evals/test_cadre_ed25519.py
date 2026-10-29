"""`cadre._ed25519` — vérificateur Ed25519 (RFC 8032) et minisign, stdlib seule (T-01M5W2SCS5).

Provenance des vecteurs, pour qu'aucun ne soit auto-produit par le module jugé :
- RFC8032 : extraits du texte officiel de la RFC 8032 § 7.1 (TEST 1, 2, 3, 1024,
  SHA(abc)), recontrôlés par un signataire indépendant (`cryptography` 50.0.1,
  OpenSSL 3.6.4) qui a rendu les mêmes clés publiques et signatures.
- MINISIGN : `minisign` n'est pas installé sur le poste de fabrication. Les deux
  fichiers ont été CONSTRUITS au format minisign par le même signataire
  indépendant, avec la clé secrète de RFC 8032 TEST 1 et l'id de clé
  `c4d2e1f0a5b69788` : clé = base64(`Ed` ‖ id ‖ pk) ; ligne 2 = base64(algo ‖ id ‖
  sig), sig sur le contenu (`Ed`) ou sur BLAKE2b-512 du contenu (`ED`) ;
  ligne 4 = base64(Ed25519(sig ‖ commentaire de confiance)).

Chaque témoin nomme en docstring le MUTANT qui le fait rougir.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SPEC_VENDOR = importlib.util.spec_from_file_location(
    "_cadre_ed25519_vendor_paths", ROOT / ".agents" / "bin" / "vendor_paths.py")
assert _SPEC_VENDOR is not None and _SPEC_VENDOR.loader is not None
_VENDOR = importlib.util.module_from_spec(_SPEC_VENDOR)
sys.modules[_SPEC_VENDOR.name] = _VENDOR
_SPEC_VENDOR.loader.exec_module(_VENDOR)
_VENDOR.charger_paquet(ROOT, "cadre")
SRC = _VENDOR.exiger(ROOT, "cadre").parent

from cadre import _ed25519 as ed  # noqa: E402
from cadre._ed25519 import (  # noqa: E402
    FormatInvalide,
    SignatureInvalide,
    exiger_minisign,
    verifier,
    verifier_minisign,
)

MODULE = SRC / "cadre" / "_ed25519.py"
P = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493

# nom : (clé publique, message, signature), en hexadécimal.
RFC8032 = {
    "TEST 1": (
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b",
    ),
    "TEST 2": (
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    "TEST 3": (
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
    "TEST 1024": (
        "278117fc144c72340f67d0f2316e8386ceffbf2b2428c9c51fef7c597f1d426e",
        (
            "08b8b2b733424243760fe426a4b54908632110a66c2f6591eabd3345e3e4eb98"
            "fa6e264bf09efe12ee50f8f54e9f77b1e355f6c50544e23fb1433ddf73be84d8"
            "79de7c0046dc4996d9e773f4bc9efe5738829adb26c81b37c93a1b270b20329d"
            "658675fc6ea534e0810a4432826bf58c941efb65d57a338bbd2e26640f89ffbc"
            "1a858efcb8550ee3a5e1998bd177e93a7363c344fe6b199ee5d02e82d522c4fe"
            "ba15452f80288a821a579116ec6dad2b3b310da903401aa62100ab5d1a36553e"
            "06203b33890cc9b832f79ef80560ccb9a39ce767967ed628c6ad573cb116dbef"
            "efd75499da96bd68a8a97b928a8bbc103b6621fcde2beca1231d206be6cd9ec7"
            "aff6f6c94fcd7204ed3455c68c83f4a41da4af2b74ef5c53f1d8ac70bdcb7ed1"
            "85ce81bd84359d44254d95629e9855a94a7c1958d1f8ada5d0532ed8a5aa3fb2"
            "d17ba70eb6248e594e1a2297acbbb39d502f1a8c6eb6f1ce22b3de1a1f40cc24"
            "554119a831a9aad6079cad88425de6bde1a9187ebb6092cf67bf2b13fd65f270"
            "88d78b7e883c8759d2c4f5c65adb7553878ad575f9fad878e80a0c9ba63bcbcc"
            "2732e69485bbc9c90bfbd62481d9089beccf80cfe2df16a2cf65bd92dd597b07"
            "07e0917af48bbb75fed413d238f5555a7a569d80c3414a8d0859dc65a46128ba"
            "b27af87a71314f318c782b23ebfe808b82b0ce26401d2e22f04d83d1255dc51a"
            "ddd3b75a2b1ae0784504df543af8969be3ea7082ff7fc9888c144da2af58429e"
            "c96031dbcad3dad9af0dcbaaaf268cb8fcffead94f3c7ca495e056a9b47acdb7"
            "51fb73e666c6c655ade8297297d07ad1ba5e43f1bca32301651339e22904cc8c"
            "42f58c30c04aafdb038dda0847dd988dcda6f3bfd15c4b4c4525004aa06eeff8"
            "ca61783aacec57fb3d1f92b0fe2fd1a85f6724517b65e614ad6808d6f6ee34df"
            "f7310fdc82aebfd904b01e1dc54b2927094b2db68d6f903b68401adebf5a7e08"
            "d78ff4ef5d63653a65040cf9bfd4aca7984a74d37145986780fc0b16ac451649"
            "de6188a7dbdf191f64b5fc5e2ab47b57f7f7276cd419c17a3ca8e1b939ae49e4"
            "88acba6b965610b5480109c8b17b80e1b7b750dfc7598d5d5011fd2dcc5600a3"
            "2ef5b52a1ecc820e308aa342721aac0943bf6686b64b2579376504ccc493d97e"
            "6aed3fb0f9cd71a43dd497f01f17c0e2cb3797aa2a2f256656168e6c496afc5f"
            "b93246f6b1116398a346f1a641f3b041e989f7914f90cc2c7fff357876e506b5"
            "0d334ba77c225bc307ba537152f3f1610e4eafe595f6d9d90d11faa933a15ef1"
            "369546868a7f3a45a96768d40fd9d03412c091c6315cf4fde7cb68606937380d"
            "b2eaaa707b4c4185c32eddcdd306705e4dc1ffc872eeee475a64dfac86aba41c"
            "0618983f8741c5ef68d3a101e8a3b8cac60c905c15fc910840b94c00a0b9d0"
        ),
        "0aab4c900501b3e24d7cdf4663326a3a87df5e4843b2cbdb67cbf6e460fec350"
        "aa5371b1508f9f4528ecea23c436d94b5e8fcd4f681e30a6ac00a9704a188a03",
    ),
    "TEST SHA(abc)": (
        "ec172b93ad5e563bf4932c70e1245034c35467ef2efd4d64ebf819683467e2bf",
        (
            "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
            "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f"
        ),
        "dc2a4459e7369633a52b1bf277839a00201009a3efbf3ecb69bea2186c26b589"
        "09351fc9ac90b3ecfdfbc7c66431e0303dca179c138ac17ad9bef1177331a704",
    ),
}

MINISIGN_CLE = "RWTE0uHwpbaXiNdamAGCsQq31Uv+08lkBzoO4XLz2qYjJa8CGmj3B1Ea"
MINISIGN_CONTENU = b"cadre-kit 1.0.0 artefact de test minisign\n"
MINISIG_PUR = (
    "untrusted comment: signature from minisign secret key\n"
    "RWTE0uHwpbaXiBA2amZtVCB0Ly6i+3dSA+vChQXmlHBWzwNsXsF/fNzuqLsWxP4VjIbHHSIKn98EJgGJCDuBuWKUNp2uFYD4Twc=\n"
    "trusted comment: timestamp:1761436800\tfile:artefact.txt\tlegacy\n"
    "mvMRWAVhjKNgS4dPr1DXg7lxhPP29RnFc2DhavbhjTAHcRHU6m1g5Ztb5KdklIYddOAIegtOD1pfICIPif6MDA==\n"
)
MINISIG_PREHACHE = (
    "untrusted comment: signature from minisign secret key\n"
    "RUTE0uHwpbaXiDSDoX/4zaHrtAkpMXu6cgLV9FFbJM7y2UBXgeBc2FzAAl+UTQzJ/BsQ+4/W4+frnVBNpVic95QDdi3pJFwOOQQ=\n"
    "trusted comment: timestamp:1761436800\tfile:artefact.txt\thashed\n"
    "R8PoZQNAsMw1HJR4WGaaC25Q4XuviJKg03TeChNy1Bd1G56BPfuG7YjAAk7jJIq9Eh1TmrFfaLCI2EXQiN1EDA==\n"
)
MINISIGS = {"Ed": MINISIG_PUR, "ED": MINISIG_PREHACHE}
#: `admettre_legacy` à passer pour lire chaque vecteur : `Ed` n'est lu que sur demande.
LEGACY = {"Ed": True, "ED": False}
#: Un point d'ordre 8 (torsion d'Ed25519) ; son ordre est vérifié par le banc, pas supposé.
TORSION_8 = "c7176a703d4dd84fba3c0b760d10670f2a2053fa2c39ccc64ec7fd7792ac037a"


def _vecteur(nom: str) -> tuple[bytes, bytes, bytes]:
    cle, msg, sig = RFC8032[nom]
    return bytes.fromhex(cle), bytes.fromhex(msg), bytes.fromhex(sig)


def _bit(donnees: bytes, index: int) -> bytes:
    brut = bytearray(donnees)
    brut[index // 8] ^= 1 << (index % 8)
    return bytes(brut)


def _ligne(minisig: str, numero: int, nouvelle: str) -> str:
    lignes = minisig.split("\n")
    lignes[numero] = nouvelle
    return "\n".join(lignes)


def _b64_ligne(minisig: str, numero: int) -> bytes:
    return base64.b64decode(minisig.split("\n")[numero])


def _encoder(point: tuple[int, int, int, int]) -> bytes:
    """Encodage RFC 8032 § 5.1.2, côté banc : le module ne signe ni n'encode."""
    x, y, z, _ = point
    zi = pow(z, P - 2, P)
    return (y * zi % P | ((x * zi % P) & 1) << 255).to_bytes(32, "little")


class VecteursRfc8032(unittest.TestCase):
    def test_les_cinq_vecteurs_de_la_rfc_sont_acceptes(self):
        """MUTANT : comparaison finale fausse, SHA-512 sur un autre ordre (A‖R‖M) → rouge.
        SURVIVANT NOMMÉ : k sans `% L` reste vert, équivalent pour une clé d'ordre premier ([k]A = [k mod L]A)."""
        for nom in RFC8032:
            with self.subTest(nom):
                self.assertIs(verifier(*_vecteur(nom)), True)

    def test_le_vecteur_sha_abc_porte_bien_sha512_abc(self):
        """Le message de TEST SHA(abc) est SHA-512("abc") : la transcription n'a rien perdu."""
        self.assertEqual(_vecteur("TEST SHA(abc)")[1], hashlib.sha512(b"abc").digest())
        self.assertEqual(len(_vecteur("TEST 1024")[1]), 1023)

    def test_un_bit_de_message_signature_ou_cle_rend_faux(self):
        """MUTANT : comparaison finale toujours vraie (`return True`) → rouge."""
        for nom in RFC8032:
            cle, msg, sig = _vecteur(nom)
            msg_mute = _bit(msg, 0) if msg else b"\x00"
            for etiquette, args in (
                ("message", (cle, msg_mute, sig)),
                ("signature R", (cle, msg, _bit(sig, 5))),
                ("signature S", (cle, msg, _bit(sig, 300))),
                ("clé", (_bit(cle, 9), msg, sig)),
            ):
                with self.subTest(nom=nom, mutation=etiquette):
                    self.assertIs(verifier(*args), False)

    def test_s_non_canonique_s_plus_l_rend_faux(self):
        """MUTANT : contrôle `S >= L` retiré → S+L passe ([S+L]B = [S]B), rouge.

        Contrôle de non-vacuité : S+L tient sur 32 octets et diffère de S.
        """
        for nom in RFC8032:
            cle, msg, sig = _vecteur(nom)
            s = int.from_bytes(sig[32:], "little")
            self.assertLess(s + L, 2**256)
            tordue = sig[:32] + (s + L).to_bytes(32, "little")
            with self.subTest(nom):
                self.assertIs(verifier(cle, msg, tordue), False)

    def test_s_egal_a_l_rend_faux(self):
        """S = L est refusé. SURVIVANT NOMMÉ : le mutant `S > L` passe ce témoin, car [L]B = O et
        l'équation O = R + [k]A échoue d'elle-même ; S = L ≡ 0 ne rend valide qu'une signature
        S = 0 déjà valide, aucune malléabilité ne s'ouvre. S+L (témoin précédent) ne le tue pas non plus."""
        cle, msg, sig = _vecteur("TEST 1")
        self.assertIs(verifier(cle, msg, sig[:32] + L.to_bytes(32, "little")), False)

    def test_point_r_ou_a_non_decodable_rend_faux(self):
        """MUTANT : contrôle `y >= p` retiré dans `_decoder` → rouge par l'`assertIsNone` direct
        de `_decoder` : via `verifier`, y = p+1 se lit y = 1 (le neutre), que le refus des
        points d'ordre petit rejette aussi ; les sous-tests de `verifier` seuls ne le tuent pas."""
        cle, msg, sig = _vecteur("TEST 1")
        y_hors_corps = (P + 1).to_bytes(32, "little")
        x_nul_signe = (1 | (1 << 255)).to_bytes(32, "little")
        sans_racine = (2).to_bytes(32, "little")
        for etiquette, args in (
            ("R : y ≥ p", (cle, msg, y_hors_corps + sig[32:])),
            ("A : y ≥ p", (y_hors_corps, msg, sig)),
            ("A : x = 0, signe 1", (x_nul_signe, msg, sig)),
            ("R : pas de racine", (cle, msg, sans_racine + sig[32:])),
            ("A : pas de racine", (sans_racine, msg, sig)),
        ):
            with self.subTest(etiquette):
                self.assertIs(verifier(*args), False)
        self.assertIsNone(ed._decoder(sans_racine))
        self.assertIsNone(ed._decoder(y_hors_corps))
        # MUTANT : refus « x = 0 et signe 1 » retiré → rouge ici seulement (via `verifier`,
        # le point lu est le neutre, rattrapé par l'ordre petit).
        self.assertIsNone(ed._decoder(x_nul_signe))
        self.assertIsNotNone(ed._decoder((1).to_bytes(32, "little")))

    def test_la_forme_canonique_du_neutre_se_decode(self):
        """Contrôle de non-vacuité du témoin y ≥ p : y = 1 se décode, y = p+1 (même valeur mod p) non."""
        self.assertIsNotNone(ed._decoder((1).to_bytes(32, "little")))

    def test_cle_d_ordre_petit_ne_valide_pas_la_signature_forgee(self):
        """MUTANT : refus des points d'ordre petit retiré → A = R = neutre, S = 0 vérifie
        [0]B = O + [k]O pour TOUT message, rouge."""
        neutre = (1).to_bytes(32, "little")
        forge = neutre + bytes(32)
        for msg in (b"", b"n'importe quel message"):
            with self.subTest(msg=msg):
                self.assertIs(verifier(neutre, msg, forge), False)

    def test_r_d_ordre_petit_avec_equation_juste_rend_faux(self):
        """MUTANT : refus de R d'ordre petit retiré (A gardé) → rouge.

        Clé honnête (graine RFC 8032 TEST 1), R = neutre, S = k·a mod L : [S]B = R + [k]A
        tient, seule la politique « R d'ordre petit refusé » (libsodium) la rejette.
        Contrôle de non-vacuité : la même construction avec R = [r]B honnête est acceptée.
        """
        graine = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
        h = hashlib.sha512(graine).digest()
        a = (int.from_bytes(h[:32], "little") & ((1 << 254) - 8)) | (1 << 254)
        cle = _vecteur("TEST 1")[0]
        msg = b"r d'ordre petit"
        neutre = (1).to_bytes(32, "little")
        k = int.from_bytes(hashlib.sha512(neutre + cle + msg).digest(), "little") % L
        self.assertIs(verifier(cle, msg, neutre + (k * a % L).to_bytes(32, "little")), False)
        r = 12345
        r_enc = _encoder(ed._multiplier(ed._BASE, r))
        k = int.from_bytes(hashlib.sha512(r_enc + cle + msg).digest(), "little") % L
        self.assertIs(verifier(cle, msg, r_enc + ((r + k * a) % L).to_bytes(32, "little")), True)

    def test_cle_de_torsion_avec_equation_juste_rend_faux(self):
        """MUTANTS : `or _ordre_petit(a)` retiré → rouge sur les 7 clés ; contrôle 4P au lieu
        de 8P → rouge sur les 4 clés d'ordre 8.

        Clé = chacun des 7 points de torsion non neutres (le sous-groupe d'ordre 8 engendré
        par TORSION_8), R = [r]B honnête, S = r, message cherché tel que k ≡ 0 mod 8 :
        [k]A = O, donc [S]B = R + [k]A TIENT (vérifié ici) et seule la garde d'ordre petit
        sur A rejette. OpenSSL 3.6 accepte ces clés (mesure de l'exec-critic) ; ce module
        les refuse, comme libsodium : épinglé.
        """
        t8 = ed._decoder(bytes.fromhex(TORSION_8))
        self.assertIsNotNone(t8)
        self.assertFalse(ed._egaux(ed._multiplier(t8, 4), ed._NEUTRE))
        self.assertTrue(ed._egaux(ed._multiplier(t8, 8), ed._NEUTRE))
        cles = {_encoder(ed._multiplier(t8, j)) for j in range(1, 8)}
        self.assertEqual(len(cles), 7)
        self.assertNotIn((1).to_bytes(32, "little"), cles)
        r = 424242
        point_r = ed._multiplier(ed._BASE, r)
        r_enc = _encoder(point_r)
        s_enc = r.to_bytes(32, "little")
        for cle in sorted(cles):
            point_a = ed._decoder(cle)
            for i in range(256):
                msg = b"forge-" + str(i).encode()
                k = int.from_bytes(hashlib.sha512(r_enc + cle + msg).digest(), "little") % L
                if k % 8 == 0:
                    break
            else:
                self.fail("aucun message à k ≡ 0 mod 8 en 256 essais")
            with self.subTest(cle=cle.hex()):
                self.assertTrue(ed._egaux(ed._multiplier(ed._BASE, r),
                                          ed._ajouter(point_r, ed._multiplier(point_a, k))))
                self.assertIs(verifier(cle, msg, r_enc + s_enc), False)

    def test_longueurs_et_types_faux_levent_format_invalide(self):
        """Jamais `False` muet ni `True` sur une forme cassée."""
        cle, msg, sig = _vecteur("TEST 1")
        for etiquette, args in (
            ("clé courte", (cle[:31], msg, sig)),
            ("clé longue", (cle + b"\x00", msg, sig)),
            ("signature courte", (cle, msg, sig[:63])),
            ("signature longue", (cle, msg, sig + b"\x00")),
            ("clé texte", (cle.hex(), msg, sig)),
            ("message texte", (cle, "", sig)),
            ("signature None", (cle, msg, None)),
        ):
            with self.subTest(etiquette), self.assertRaises(FormatInvalide):
                verifier(*args)

    def test_octets_assimiles_acceptes(self):
        cle, msg, sig = _vecteur("TEST 2")
        self.assertIs(verifier(bytearray(cle), memoryview(msg), bytearray(sig)), True)


class Minisign(unittest.TestCase):
    """`Ed` (legacy) n'est lu que sur `admettre_legacy=True` : chaque cas sur MINISIG_PUR le passe,
    pour que le refus legacy ne masque pas le contrôle que le cas vise."""

    def test_vecteurs_ed_et_ED_acceptes(self):
        """MUTANT : préhachage BLAKE2b retiré ou appliqué à `Ed` → rouge."""
        for algo, minisig in MINISIGS.items():
            with self.subTest(algo):
                self.assertEqual(_b64_ligne(minisig, 1)[:2], algo.encode())
                self.assertIs(verifier_minisign(
                    MINISIGN_CLE, MINISIGN_CONTENU, minisig, admettre_legacy=LEGACY[algo]), True)
                self.assertIsNone(exiger_minisign(
                    MINISIGN_CLE, MINISIGN_CONTENU, minisig, admettre_legacy=LEGACY[algo]))

    def test_legacy_ed_refuse_par_defaut(self):
        """MUTANT : refus de `Ed` par défaut retiré → rouge (MINISIG_PUR rendrait True)."""
        with self.assertRaises(FormatInvalide):
            verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU, MINISIG_PUR)
        with self.assertRaises(FormatInvalide):
            exiger_minisign(MINISIGN_CLE, MINISIGN_CONTENU, MINISIG_PUR)

    def test_bascule_ED_vers_Ed_ne_passe_pas_par_defaut(self):
        """MUTANT : refus de `Ed` par défaut retiré → rouge.

        Attaque (critic-opus, mesurée) : les 2 octets d'algorithme ne sont signés par rien ;
        MINISIG_PREHACHE basculé `ED` → `Ed`, présenté avec BLAKE2b(contenu) COMME contenu,
        vérifie. Contrôle de non-vacuité : sous `admettre_legacy=True`, la bascule passe.
        """
        ligne = _b64_ligne(MINISIG_PREHACHE, 1)
        bascule = _ligne(MINISIG_PREHACHE, 1, base64.b64encode(b"Ed" + ligne[2:]).decode())
        empreinte = hashlib.blake2b(MINISIGN_CONTENU, digest_size=64).digest()
        with self.assertRaises(FormatInvalide):
            verifier_minisign(MINISIGN_CLE, empreinte, bascule)
        self.assertIs(verifier_minisign(MINISIGN_CLE, empreinte, bascule, admettre_legacy=True), True)

    def test_contenu_altere_rend_faux_et_exiger_leve(self):
        """MUTANT : `return False` de la signature du contenu retiré → rouge."""
        for algo, minisig in MINISIGS.items():
            with self.subTest(algo):
                self.assertIs(verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU + b"x", minisig,
                                                admettre_legacy=LEGACY[algo]), False)
                with self.assertRaises(SignatureInvalide):
                    exiger_minisign(MINISIGN_CLE, MINISIGN_CONTENU + b"x", minisig,
                                    admettre_legacy=LEGACY[algo])

    def test_commentaire_de_confiance_altere_rend_faux(self):
        """MUTANT : vérification de la signature globale retirée (`return True`) → rouge."""
        for algo, minisig in MINISIGS.items():
            tc = minisig.split("\n")[2]
            for etiquette, nouveau in (("caractère", tc.replace("1761436800", "1761436801")),
                                       ("suffixe", tc + " ")):
                with self.subTest(algo=algo, mutation=etiquette):
                    self.assertIs(verifier_minisign(
                        MINISIGN_CLE, MINISIGN_CONTENU, _ligne(minisig, 2, nouveau),
                        admettre_legacy=LEGACY[algo]), False)

    def test_signature_globale_alteree_rend_faux(self):
        for algo, minisig in MINISIGS.items():
            globale = _bit(_b64_ligne(minisig, 3), 17)
            with self.subTest(algo):
                self.assertIs(verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU, _ligne(
                    minisig, 3, base64.b64encode(globale).decode()), admettre_legacy=LEGACY[algo]), False)

    def test_id_de_cle_different_rend_faux(self):
        """MUTANT : comparaison des id de clé retirée → même clé, signature valide, rouge."""
        brut = base64.b64decode(MINISIGN_CLE)
        autre_id = base64.b64encode(brut[:2] + _bit(brut[2:10], 0) + brut[10:]).decode()
        for algo, minisig in MINISIGS.items():
            with self.subTest(algo, cote="clé"):
                self.assertIs(verifier_minisign(
                    autre_id, MINISIGN_CONTENU, minisig, admettre_legacy=LEGACY[algo]), False)
            ligne = _b64_ligne(minisig, 1)
            sig_autre_id = base64.b64encode(ligne[:2] + _bit(ligne[2:10], 63) + ligne[10:]).decode()
            with self.subTest(algo, cote="signature"):
                self.assertIs(verifier_minisign(
                    MINISIGN_CLE, MINISIGN_CONTENU, _ligne(minisig, 1, sig_autre_id),
                    admettre_legacy=LEGACY[algo]), False)

    def test_algorithme_echange_rend_faux(self):
        """`Ed` lu comme `ED` (et l'inverse, legacy admis) : la signature porte sur autre chose."""
        for algo, minisig in MINISIGS.items():
            ligne = _b64_ligne(minisig, 1)
            echange = (b"ED" if algo == "Ed" else b"Ed") + ligne[2:]
            with self.subTest(algo):
                self.assertIs(verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU, _ligne(
                    minisig, 1, base64.b64encode(echange).decode()), admettre_legacy=True), False)

    def test_fichier_pub_entier_et_crlf_acceptes(self):
        pub = "untrusted comment: minisign public key C4D2E1F0A5B69788\n" + MINISIGN_CLE + "\n"
        crlf = MINISIG_PREHACHE.replace("\n", "\r\n")
        self.assertIs(verifier_minisign(pub, MINISIGN_CONTENU, MINISIG_PREHACHE), True)
        self.assertIs(verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU, crlf), True)

    def test_formes_cassees_levent_format_invalide(self):
        """MUTANT : une forme cassée rendue `True` par défaut → rouge. Legacy admis : le refus
        de `Ed` ne masque aucun cas."""
        brut_cle = base64.b64decode(MINISIGN_CLE)
        ligne = _b64_ligne(MINISIG_PUR, 1)
        cas_minisig = {
            "trois lignes": "\n".join(MINISIG_PUR.split("\n")[:3]),
            "ligne 1 sans préfixe": _ligne(MINISIG_PUR, 0, "comment: x"),
            # MUTANT : préfixe sans l'espace final (minisign l'exige) → rouge.
            "ligne 1 sans espace après le préfixe": _ligne(MINISIG_PUR, 0, "untrusted comment:x"),
            "ligne 3 sans préfixe": _ligne(MINISIG_PUR, 2, "timestamp:1"),
            "base64 cassé": _ligne(MINISIG_PUR, 1, "RWT!!!"),
            "signature tronquée": _ligne(MINISIG_PUR, 1, base64.b64encode(ligne[:-1]).decode()),
            "algorithme inconnu": _ligne(MINISIG_PUR, 1, base64.b64encode(b"Ex" + ligne[2:]).decode()),
            "globale tronquée": _ligne(MINISIG_PUR, 3, base64.b64encode(bytes(63)).decode()),
            "cinq lignes": MINISIG_PUR + "en trop\n",
        }
        for etiquette, minisig in cas_minisig.items():
            with self.subTest(etiquette), self.assertRaises(FormatInvalide):
                verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU, minisig, admettre_legacy=True)
        cas_cle = {
            "clé vide": "",
            "deux clés": MINISIGN_CLE + "\n" + MINISIGN_CLE,
            "clé tronquée": base64.b64encode(brut_cle[:-1]).decode(),
            "algorithme de clé": base64.b64encode(b"ED" + brut_cle[2:]).decode(),
            "clé octets": MINISIGN_CLE.encode(),
        }
        for etiquette, cle in cas_cle.items():
            with self.subTest(etiquette), self.assertRaises(FormatInvalide):
                verifier_minisign(cle, MINISIGN_CONTENU, MINISIG_PUR, admettre_legacy=True)
        with self.assertRaises(FormatInvalide):
            verifier_minisign(MINISIGN_CLE, "texte", MINISIG_PUR, admettre_legacy=True)
        with self.assertRaises(FormatInvalide):
            verifier_minisign(MINISIGN_CLE, MINISIGN_CONTENU, MINISIG_PUR.encode(), admettre_legacy=True)

    def test_surrogate_isole_dans_le_commentaire_leve_format_invalide(self):
        """MUTANTS : `try/except UnicodeError` retiré → UnicodeEncodeError s'échappe, rouge ;
        encodage déplacé APRÈS la vérification du contenu → contenu faux rendrait `False`, rouge."""
        tc = MINISIG_PREHACHE.split("\n")[2] + "\ud800"
        minisig = _ligne(MINISIG_PREHACHE, 2, tc)
        for contenu in (MINISIGN_CONTENU, b"autre"):
            with self.subTest(contenu=contenu), self.assertRaises(FormatInvalide):
                verifier_minisign(MINISIGN_CLE, contenu, minisig)


class Module(unittest.TestCase):
    def test_bibliotheque_standard_seule(self):
        """Aucune dépendance : les imports du module sont dans une liste fermée stdlib."""
        arbre = ast.parse(MODULE.read_text(encoding="utf-8"))
        importes = set()
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Import):
                importes.update(alias.name.split(".")[0] for alias in noeud.names)
            elif isinstance(noeud, ast.ImportFrom):
                importes.add((noeud.module or "").split(".")[0])
        self.assertEqual(importes, {"__future__", "base64", "binascii", "hashlib"})

    def test_hierarchie_des_erreurs(self):
        self.assertTrue(issubclass(FormatInvalide, ed.ErreurSignature))
        self.assertTrue(issubclass(SignatureInvalide, ed.ErreurSignature))
        self.assertTrue(issubclass(ed.ErreurSignature, ValueError))


if __name__ == "__main__":
    unittest.main()
