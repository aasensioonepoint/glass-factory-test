"""Vérification Ed25519 (RFC 8032) et minisign, bibliothèque standard seule (T-01M5W2SCS5).

Préalable commun de la livraison sécurisée (signature des artefacts, jeton de
licence) : conception dans `docs/interne/roadmap/livraison-securisee-licences.html`
§§ 2.4, 2.6, 3.1-3.2. Aucune dépendance : `hashlib` porte SHA-512 et BLAKE2b.

API
- `verifier(cle_publique, message, signature) -> bool` : Ed25519 PUR, RFC 8032
  § 5.1.7. Clé de 32 octets, signature de 64 octets ; une autre longueur, ou un
  argument qui n'est pas des octets, lève `FormatInvalide`. Tout le reste rend
  `False` : S ≥ L, R ou A non décodable (y ≥ p, x = 0 avec bit de signe à 1,
  pas de racine), R ou A d'ordre petit, équation non vérifiée.
- `verifier_minisign(cle_publique_minisign, contenu, minisig) -> bool` : format
  minisign. Clé : la ligne base64 « RW… » (RWQ, RWR, RWS ou RWT selon l'id ; 42
  octets : `Ed`, id de clé de 8 octets, clé de 32 octets), ou le fichier `.pub`
  entier. Signature : le fichier `.minisig` entier (4 lignes). Algorithme `ED`
  (signature sur BLAKE2b-512 du contenu) par défaut ; `Ed` (legacy, signature sur
  le contenu) seulement sur `admettre_legacy=True`, sinon `FormatInvalide` : les
  octets d'algorithme ne sont signés par rien. La signature GLOBALE, sur la
  signature et le commentaire de confiance, est vérifiée aussi : un commentaire
  altéré rend `False`. Un id de clé différent de celui de la clé rend `False`.
  Une forme cassée (base64, longueur, préfixe de ligne, algorithme inconnu,
  nombre de lignes) lève `FormatInvalide`.
- `exiger_minisign(...)` : la même vérification, qui lève `SignatureInvalide`
  au lieu de rendre `False` ; la forme d'appel des consommateurs qui ferment.

Aucun chemin ne rend `True` par défaut : seule l'égalité de groupe calculée le fait.

TEMPS NON CONSTANT, ASSUMÉ : ce module ne VÉRIFIE que des signatures publiques
avec des clés publiques ; aucun secret ne passe par lui, une fuite par le temps
n'a rien à révéler. Il ne SIGNE pas, et ne doit jamais servir à signer.

Équation vérifiée : [S]B = R + [k]A sans cofacteur (RFC 8032 § 5.1.7 l'admet),
avec refus des R et A d'ordre petit, comme libsodium sur lequel repose minisign.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

__all__ = [
    "ErreurSignature",
    "FormatInvalide",
    "SignatureInvalide",
    "exiger_minisign",
    "verifier",
    "verifier_minisign",
]

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_RACINE_MOINS_UN = pow(2, (_P - 1) // 4, _P)
_NEUTRE = (0, 1, 1, 0)

_ALGO_PUR = b"Ed"
_ALGO_PREHACHE = b"ED"
_PREFIXE_NON_SIGNE = "untrusted comment: "
_PREFIXE_SIGNE = "trusted comment: "
_TAILLE_CLE_MINISIGN = 2 + 8 + 32
_TAILLE_SIG_MINISIGN = 2 + 8 + 64


class ErreurSignature(ValueError):
    """Base des erreurs de ce module."""


class FormatInvalide(ErreurSignature):
    """Entrée mal formée : longueur, base64, préfixe, algorithme, type."""


class SignatureInvalide(ErreurSignature):
    """Signature bien formée mais fausse (levée par `exiger_minisign`)."""


def _octets(valeur: object, nom: str, taille: int | None = None) -> bytes:
    if not isinstance(valeur, (bytes, bytearray, memoryview)):
        raise FormatInvalide(f"{nom} : octets attendus, reçu {type(valeur).__name__}")
    brut = bytes(valeur)
    if taille is not None and len(brut) != taille:
        raise FormatInvalide(f"{nom} : {taille} octets attendus, reçu {len(brut)}")
    return brut


def _ajouter(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Addition complète en coordonnées étendues (a = -1), vaut aussi pour le doublement."""
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _multiplier(point: tuple[int, int, int, int], scalaire: int) -> tuple[int, int, int, int]:
    resultat = _NEUTRE
    while scalaire:
        if scalaire & 1:
            resultat = _ajouter(resultat, point)
        point = _ajouter(point, point)
        scalaire >>= 1
    return resultat


def _egaux(p1: tuple[int, int, int, int], p2: tuple[int, int, int, int]) -> bool:
    """Égalité projective : X1·Z2 = X2·Z1 et Y1·Z2 = Y2·Z1."""
    return (p1[0] * p2[2] - p2[0] * p1[2]) % _P == 0 and (p1[1] * p2[2] - p2[1] * p1[2]) % _P == 0


def _decoder(encodage: bytes) -> tuple[int, int, int, int] | None:
    """Décodage RFC 8032 § 5.1.3 ; `None` si l'encodage n'est pas celui d'un point."""
    y = int.from_bytes(encodage, "little")
    signe = y >> 255
    y &= (1 << 255) - 1
    if y >= _P:
        return None
    u = (y * y - 1) % _P
    v = (_D * y * y + 1) % _P
    x = u * pow(v, 3, _P) * pow(u * pow(v, 7, _P), (_P - 5) // 8, _P) % _P
    carre = v * x * x % _P
    if carre == (-u) % _P:
        x = x * _RACINE_MOINS_UN % _P
    elif carre != u:
        return None
    if x == 0 and signe:
        return None
    if x & 1 != signe:
        x = _P - x
    return (x, y, 1, x * y % _P)


def _ordre_petit(point: tuple[int, int, int, int]) -> bool:
    huit = _ajouter(point, point)
    huit = _ajouter(huit, huit)
    huit = _ajouter(huit, huit)
    return _egaux(huit, _NEUTRE)


_BY = 4 * pow(5, _P - 2, _P) % _P
_BASE_OU_RIEN = _decoder(_BY.to_bytes(32, "little"))
if _BASE_OU_RIEN is None:
    raise RuntimeError("point de base Ed25519 non décodable")
_BASE = _BASE_OU_RIEN


def verifier(cle_publique: bytes, message: bytes, signature: bytes) -> bool:
    """Ed25519 pur (RFC 8032 § 5.1.7). `FormatInvalide` sur une longueur ou un type faux."""
    cle = _octets(cle_publique, "clé publique", 32)
    msg = _octets(message, "message")
    sig = _octets(signature, "signature", 64)
    s = int.from_bytes(sig[32:], "little")
    if s >= _L:
        return False
    a = _decoder(cle)
    r = _decoder(sig[:32])
    if a is None or r is None or _ordre_petit(a) or _ordre_petit(r):
        return False
    k = int.from_bytes(hashlib.sha512(sig[:32] + cle + msg).digest(), "little") % _L
    return _egaux(_multiplier(_BASE, s), _ajouter(r, _multiplier(a, k)))


def _b64(texte: str, nom: str, taille: int) -> bytes:
    try:
        brut = base64.b64decode(texte.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise FormatInvalide(f"{nom} : base64 invalide") from exc
    if len(brut) != taille:
        raise FormatInvalide(f"{nom} : {taille} octets attendus, reçu {len(brut)}")
    return brut


def _lignes(texte: str) -> list[str]:
    return [ligne.rstrip("\r") for ligne in texte.split("\n")]


def _cle_minisign(cle_publique_minisign: str) -> tuple[bytes, bytes]:
    if not isinstance(cle_publique_minisign, str):
        raise FormatInvalide("clé minisign : texte attendu")
    utiles = [ligne for ligne in _lignes(cle_publique_minisign)
              if ligne.strip() and not ligne.startswith(_PREFIXE_NON_SIGNE)]
    if len(utiles) != 1:
        raise FormatInvalide(f"clé minisign : une ligne de clé attendue, {len(utiles)} trouvée(s)")
    brut = _b64(utiles[0], "clé minisign", _TAILLE_CLE_MINISIGN)
    if brut[:2] != _ALGO_PUR:
        raise FormatInvalide("clé minisign : algorithme de clé inconnu")
    return brut[2:10], brut[10:]


def _lire_minisig(minisig: str) -> tuple[bytes, bytes, bytes, bytes, bytes]:
    if not isinstance(minisig, str):
        raise FormatInvalide("minisig : texte attendu")
    lignes = _lignes(minisig)
    while lignes and lignes[-1] == "":
        lignes.pop()
    if len(lignes) != 4:
        raise FormatInvalide(f"minisig : 4 lignes attendues, {len(lignes)} trouvée(s)")
    if not lignes[0].startswith(_PREFIXE_NON_SIGNE):
        raise FormatInvalide("minisig : ligne 1 sans « untrusted comment: »")
    if not lignes[2].startswith(_PREFIXE_SIGNE):
        raise FormatInvalide("minisig : ligne 3 sans « trusted comment: »")
    brut = _b64(lignes[1], "minisig signature", _TAILLE_SIG_MINISIGN)
    algo = brut[:2]
    if algo not in (_ALGO_PUR, _ALGO_PREHACHE):
        raise FormatInvalide("minisig : algorithme de signature inconnu")
    globale = _b64(lignes[3], "minisig signature globale", 64)
    try:
        commentaire = lignes[2][len(_PREFIXE_SIGNE):].encode("utf-8")
    except UnicodeError as exc:
        raise FormatInvalide("minisig : commentaire de confiance non encodable en UTF-8") from exc
    return algo, brut[2:10], brut[10:], commentaire, globale


def verifier_minisign(cle_publique_minisign: str, contenu: bytes, minisig: str, *,
                      admettre_legacy: bool = False) -> bool:
    """Vérifie un `.minisig` ET sa signature globale. `FormatInvalide` sur une forme cassée.

    `ED` (préhaché) seul par défaut : les 2 octets d'algorithme ne sont couverts par aucune
    signature, admettre `Ed` laisse présenter BLAKE2b(contenu) comme contenu. `Ed` (legacy)
    n'est lu que sur `admettre_legacy=True`.
    """
    id_cle, cle = _cle_minisign(cle_publique_minisign)
    donnees = _octets(contenu, "contenu")
    algo, id_sig, signature, commentaire, globale = _lire_minisig(minisig)
    if algo == _ALGO_PUR and not admettre_legacy:
        raise FormatInvalide("minisig : signature legacy « Ed » refusée, préhachage « ED » exigé")
    if id_sig != id_cle:
        return False
    if algo == _ALGO_PREHACHE:
        donnees = hashlib.blake2b(donnees, digest_size=64).digest()
    if not verifier(cle, donnees, signature):
        return False
    return verifier(cle, signature + commentaire, globale)


def exiger_minisign(cle_publique_minisign: str, contenu: bytes, minisig: str, *,
                    admettre_legacy: bool = False) -> None:
    """Comme `verifier_minisign`, mais lève `SignatureInvalide` au lieu de rendre `False`."""
    if not verifier_minisign(cle_publique_minisign, contenu, minisig, admettre_legacy=admettre_legacy):
        raise SignatureInvalide("signature minisign refusée")
