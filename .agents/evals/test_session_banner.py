"""T-00001228 — la bannière de marque au SessionStart, retirable seulement par un
jeton signé Ed25519 (décisions pilote S-00004529, S-00004530, S-00004606,
S-00004618 ; plan docs/tasks/T-00001228-plan.md, annexe C).

CE QUE CE BANC TIENT, cas par cas (chaque cas peut rougir — voir les mutants) :
  C1   sans jeton : stdout est EXACTEMENT le décodage de message.oct, une ligne
       JSON de clé unique `systemMessage`, rc 0 — sous chaque bash disponible
       (/bin/bash 3.2 sur macOS ET le bash du PATH).
  C2   jeton valide, fabriqué par les commandes EXACTES de l'annexe D : silence.
  C3   `expires` = aujourd'hui (UTC) : bannière ; demain : silence (contrôle).
  C4   id révoqué par la ligne que rend `grep '^id='` (annexe D, 6) : bannière.
  C5   charge altérée après signature : bannière.
  C6   signature sous un autre espace de noms : bannière.
  C7   signature d'une autre clé : bannière.
  C7b  allowed_signers remplacé par la clé de l'attaquant, jeton qu'elle a
       signé : bannière (l'épingle).
  C8   seconde ligne d'attaquant dans allowed_signers : bannière (unicité).
  C9   ssh-keygen absent du PATH FIGÉ du hook : bannière (copie dont la ligne
       PATH pointe un dossier d'outils ; contrôle : avec ssh-keygen, silence).
  C10  grammaire du jeton : ligne en trop, en moins, réordonnée, `kind=autre`,
       `scope=local`, `expires` non numérique, sans saut final, CRLF, id vide.
  C11  message.oct absent, altéré, ou à saut de ligne brut : REPLI visible,
       lui aussi un `systemMessage` (C6 du plan-critic it. 1).
  C12  l'enregistrement dans settings.json (la forme PREFIX reste tenue par
       test_hook_env_hardening.py, SYM-11259, seul) ; aucune clé `env` que
       Claude Code ignore en portée projet, et dans le kit aucun `env` du tout
       (T-01M4WNKCBXS893CHPSKD1Z1PN9) ; la liste blanche == les clés de
       télémétrie du bloc utilisateur recommandé (S-01M4X6HVWK2E67ARX45NV6FB17).
  C15  sha256 du décodage EXACT épinglé, ouverture par `\\n`, <= 9 lignes,
       <= 70 colonnes, jeu de caractères borné — jamais le texte en clair.
  C16  épingle du hook == empreinte de la `*.pub` (glob, son nom n'est jamais
       cité) == empreinte de allowed_signers == la valeur de ce banc.
  C17  le hook réel sur l'arbre réel, HOME vide : bannière.
  C18  HOME absent de l'environnement : bannière, et aucun « unbound ».
  C19  un `ssh-keygen` factice en tête du PATH de l'utilisateur : bannière.
  C20  un jeton NON SIGNÉ de 1 Mio à en-tête valide : bannière en moins de 2 s
       (lecture bornée AVANT toute expansion de motif, exec-critic S-00004625).
  C21  allowed_signers de 66 lignes (65 commentées) : bannière ; 64 : silence.
  C13  les deux lignes `permissions.deny` de la bannière.
  C14  protect-paths.sh rejoué : bras (toutes formes, copie hors dépôt ; le
       lanceur garde-fermee.sh compris, T-01M4JRFS0T), règle de contenu
       (égalité, préfixe UNIQUE, deny, disableAllHooks, charge MultiEdit
       refusée), voisins permis ; les jambes de garde sous leurs DEUX formes
       fermées, la NUE (trois clés exactes) et l'ENVELOPPÉE sous garde-fermee.sh
       (quatre clés, `--echeance=N`, N + 2 <= timeout <= 600, type `command`,
       shell `bash`, garde visée == garde garantie), chaque état de départ
       CONSTRUIT ; dérivation safe-bash (la sonde du
       plan, rejouée sur le safe-bash.sh du banc). La COPIE du settings.json
       reçoit un `env` synthétique (ENV_SYNTHETIQUE) : la garde se juge sur un
       settings.json de projet qui en porte un ; un `env` déjà posé par l'adoptant
       y est REMPLACÉ, jamais doublé (test_c14_env_preexistant_adoptant).
  M1-M49 (M11b en sus) : chaque mutant fait rougir au moins un cas désigné ;
  la propriété fail-closed (avortement en tête de chaîne ⇒ bannière quand même)
  est un test à part.

CE QU'IL NE TIENT PAS (L-00000187) :
  * le rendu dans l'hôte : la ligne `SessionStart:startup says:` n'est mesurée
    qu'à la main (plan, annexe A1) ;
  * `resume`/`clear`, l'app de bureau, VS Code, `claude -p` : non mesurés ;
  * OpenSSH < 8.1 : non mesuré (un tel poste AFFICHE, fail-closed) ;
  * C2 porte la date de l'annexe D (20341007) : après le 2034-10-07 il rougit,
    comme le jeton du pilote expire.

LES FIXTURES S'ÉCRIVENT EN PYTHON, jamais par redirection shell : le bras
`*.agents/security/banner/*` de protect-paths.sh est une SOUS-CHAÎNE que
safe-bash dérive, et il refuse aussi une copie sous /tmp (mesuré, plan-critic
it. 1). Les clés sont JETABLES, générées ici ; la clé privée du pilote n'est
jamais lue. Le banc opère sur une COPIE du hook dont l'épingle est remplacée par
l'empreinte de la clé jetable ; C16 prouve que la vraie épingle est celle de la
vraie clé. Environnement par LISTE BLANCHE (PATH, HOME jetable,
CLAUDE_PROJECT_DIR jetable).

Sans ssh-keygen, le banc SAUTE nommément — sauf dans le kit sous CI=true, où
c'est un ÉCHEC nommé.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "session-banner.sh"
DONNEES = ROOT / ".agents" / "security" / "banner"
SETTINGS = ROOT / ".claude" / "settings.json"
EST_LE_KIT = (ROOT / ".agents" / "IS_THE_KIT").is_file()  # adopting-tree: le marqueur du kit ne voyage pas, son absence EST l'arbre adoptant

EMPREINTE_REELLE = "SHA256:n4w7327MLesanf4OzkMxW1UmZfZmvTDb0zuJDZRF7rk"
LIGNE_EPINGLE = "EMPREINTE='" + EMPREINTE_REELLE + "'"
#: sha256 des octets DÉCODÉS de message.oct — le texte n'est jamais écrit ici.
SHA256_DECODE = "72e684f4af520ac48f3cc8aa77d55941cb11a116422c5d874303b785b4728e11"
QUEUE_BANNIERE = 'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/session-banner.sh"'
QUEUE_SESSION_START = 'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/session-start.sh"'
MATCHER = "startup|resume|clear"
ESPACE = "cadre-banner"
#: La liste BLANCHE des clés `env` (décision pilote S-00004646), même règle que protect-paths.sh ; sa
#: source : les clés de télémétrie du bloc utilisateur recommandé (S-01M4X6HVWK2E67ARX45NV6FB17).
ENV_PERMISES = ("CLAUDE_CODE_ENABLE_TELEMETRY", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL",
                "OTEL_LOGS_EXPORTER", "OTEL_METRICS_EXPORTER", "OTEL_METRIC_EXPORT_INTERVAL")
RECOMMANDE = ROOT / "docs" / "settings-utilisateur-recommande.json"
#: Clés que Claude Code 2.1.299 IGNORE dans les réglages d'un projet (« project-scoped settings can't
#: set this key ») : les 5 mesurées à l'exécution (M2 du plan T-01M4WNKCBXS893CHPSKD1Z1PN9) et le
#: préfixe OTEL_EXPORTER_OTLP_. Un SOUS-ENSEMBLE borné de la liste `Din` du binaire (48 clés), jamais
#: cette liste entière ; comparé sans la casse, comme la garde (plus strict que l'hôte, voulu).
REFUSEES_PORTEE_PROJET = ("CLAUDE_CODE_ENABLE_TELEMETRY", "OTEL_METRICS_EXPORTER", "OTEL_LOGS_EXPORTER",
                          "OTEL_EXPORTER_OTLP_PROTOCOL", "OTEL_EXPORTER_OTLP_ENDPOINT")
PREFIXE_REFUSE = "OTEL_EXPORTER_OTLP_"
#: Le bloc `env` que portait le settings.json suivi AVANT T-01M4WNKCBXS893CHPSKD1Z1PN9 : posé sur la
#: COPIE seule par projet_gardes, il porte les ancres `otel`/`point` de cas_c14.
ENV_SYNTHETIQUE = {
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
    "OTEL_METRIC_EXPORT_INTERVAL": "5000",
}


def env_permise(k: str) -> bool:
    return k.upper() in ENV_PERMISES


def refusee_portee_projet(k: str) -> bool:
    k = k.upper()
    return k in REFUSEES_PORTEE_PROJET or k.startswith(PREFIXE_REFUSE)


LIGNES_MAX = 9
COLONNES_MAX = 70
#: Le jeu borné, sans aucun texte en clair (revue de sécurité S-00004661) : les
#: rangs ne portent que des points et des blancs, la signature que des lettres
#: ASCII et des blancs ; l'exactitude reste tenue par le sha256 épinglé.
RANG = set(". ")
SIGNATURE_RE = re.compile(r" *[A-Za-z]+(?: [A-Za-z]+)*")
#: Annexe D, étape 2, sans sa redirection : la sortie est écrite par Python.
ANNEXE_D_JETON = "printf 'kind=banner-off\\nscope=global\\nid=%s\\nexpires=20341007\\n' \"$(date -u +%Y%m%dT%H%M%SZ)\""
#: Annexe D, étape 6 : la ligne que le pilote recopie dans `revoked`.
ANNEXE_D_ID = "grep '^id=' \"$HOME/.config/cadre/banner/off\""
TETE_CLE_RE = re.compile(r"^  tete_cle='banner@cadre namespaces=\"([^\"]+)\" ssh-ed25519 '$", re.M)

SSH = shutil.which("ssh-keygen")
SSH_HOOK = next((p for p in ("/usr/bin/ssh-keygen", "/bin/ssh-keygen") if Path(p).is_file()), None)


def _bashes() -> list[str]:
    vus: set[str] = set()
    out: list[str] = []
    for b in ("/bin/bash", shutil.which("bash")):
        if b and Path(b).is_file():
            r = os.path.realpath(b)
            if r not in vus:
                vus.add(r)
                out.append(b)
    return out


BASHES = _bashes()


def _exiger_outils() -> None:
    manque = []
    if not (SSH and SSH_HOOK):
        manque.append("ssh-keygen (PATH du banc, ou /usr/bin:/bin du hook)")
    if not BASHES:
        manque.append("bash")
    if not manque:
        return
    msg = "absent : " + ", ".join(manque) + " — la vérification de signature n'est PAS mesurée"
    if EST_LE_KIT and os.environ.get("CI") == "true":
        pytest.fail("ÉCHEC NOMMÉ sous CI=true dans le kit — " + msg)
    pytest.skip(msg)


def _env(depot: Path, maison: Path | None, path: str | None = None) -> dict[str, str]:
    env = {"PATH": path or os.environ.get("PATH", "/usr/bin:/bin"), "CLAUDE_PROJECT_DIR": str(depot)}
    if maison is not None:
        env["HOME"] = str(maison)
    for k in ("SYSTEMROOT", "TEMP", "TMP"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def _ssh(*args: str, entree: bytes | None = None, maison: Path | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    if maison is not None:
        env["HOME"] = str(maison)
    return subprocess.run([SSH, *args], input=entree, capture_output=True, env=env, timeout=60, check=False)


def _empreinte(cle_publique: str) -> str:
    p = _ssh("-lf", "-", entree=(cle_publique + "\n").encode("ascii"))
    assert p.returncode == 0, p.stderr
    return p.stdout.decode("ascii").split()[1]


def _decoder(ligne: str) -> bytes:
    assert re.fullmatch(r"(?:\\0[0-7]{3})+", ligne), "message.oct hors de la grammaire \\0NNN"
    return bytes(int(ligne[i + 2:i + 5], 8) for i in range(0, len(ligne), 5))


def _decoder_fichier(chemin: Path) -> bytes:
    return _decoder(chemin.read_bytes().decode("ascii").split("\n", 1)[0])


def _jour(delta: int = 0) -> str:
    j = datetime.datetime.now(datetime.timezone.utc).date() + datetime.timedelta(days=delta)
    return j.strftime("%Y%m%d")


def _jeton(ident: str = "20261008T000000Z", expires: str = "20341007") -> bytes:
    return f"kind=banner-off\nscope=global\nid={ident}\nexpires={expires}\n".encode("ascii")


@dataclass
class Cle:
    prive: Path
    blob: str
    empreinte: str


@dataclass
class Banc:
    racine: Path
    depot: Path
    maison: Path
    hook: Path
    bash: str
    cles: dict[str, Cle]
    espace_hook: str

    @property
    def dossier(self) -> Path:
        return self.depot / ".agents" / "security" / "banner"

    @property
    def off(self) -> Path:
        return self.maison / ".config" / "cadre" / "banner" / "off"

    def attendu(self) -> bytes:
        return _decoder_fichier(self.dossier / "message.oct")

    def ligne_signer(self, cle: str, espace: str | None = None) -> str:
        return f'banner@cadre namespaces="{espace or self.espace_hook}" ssh-ed25519 {self.cles[cle].blob}'

    def signers(self, *lignes: str) -> None:
        (self.dossier / "allowed_signers").write_text("".join(x + "\n" for x in lignes), encoding="utf-8")

    def poser(self, contenu: bytes, cle: str = "pilote", espace: str = ESPACE) -> None:
        """Annexe D, étape 3 : `ssh-keygen -Y sign -f <clé> -n <espace> <off>`."""
        self.off.parent.mkdir(parents=True, exist_ok=True)
        self.off.write_bytes(contenu)
        sig = self.off.with_name("off.sig")
        if sig.exists():
            sig.unlink()
        p = _ssh("-Y", "sign", "-f", str(self.cles[cle].prive), "-n", espace, str(self.off), maison=self.racine)
        assert p.returncode == 0 and sig.is_file(), p.stderr

    def poser_annexe_d(self, cle: str = "pilote") -> bytes:
        """Annexe D, étapes 2 et 3 : la commande `printf` EXACTE (à `\\n` final)."""
        p = subprocess.run([self.bash, "-c", ANNEXE_D_JETON], env=_env(self.depot, self.maison),
                           capture_output=True, timeout=30, check=False)
        assert p.returncode == 0 and p.stdout.endswith(b"\n"), p.stderr
        self.poser(p.stdout, cle)
        return p.stdout

    def revoquer(self) -> None:
        """Annexe D, étape 6 : la ligne rendue par `grep '^id='`, ajoutée telle quelle."""
        p = subprocess.run([self.bash, "-c", ANNEXE_D_ID], env=_env(self.depot, self.maison),
                           capture_output=True, timeout=30, check=False)
        assert p.returncode == 0 and p.stdout.startswith(b"id=") and p.stdout.endswith(b"\n"), p.stderr
        rev = self.dossier / "revoked"
        rev.write_bytes(rev.read_bytes() + p.stdout)

    def jouer(self, *, hook: Path | None = None, maison: bool = True, path: str | None = None,
              delai: int = 60) -> subprocess.CompletedProcess:
        env = _env(self.depot, self.maison if maison else None, path)
        return subprocess.run([self.bash, "-p", str(hook or self.hook)], env=env, stdin=subprocess.DEVNULL,
                              capture_output=True, timeout=delai, check=False)


def fabriquer(racine: Path, bash: str, cles: dict[str, Cle], texte_hook: str | None = None) -> Banc:
    """Un arbre jetable : la copie du hook (épingle → clé jetable `pilote`), les
    données réelles, allowed_signers à la forme que le hook ATTEND."""
    texte = HOOK.read_text(encoding="utf-8") if texte_hook is None else texte_hook
    assert texte.count(LIGNE_EPINGLE) == 1, "l'épingle réelle n'est pas une ligne unique du hook"
    texte = texte.replace(LIGNE_EPINGLE, "EMPREINTE='" + cles["pilote"].empreinte + "'")
    espaces = TETE_CLE_RE.findall(texte)
    assert len(espaces) == 1, "la forme attendue de allowed_signers est introuvable dans le hook"
    depot = racine / "depot"
    hook = depot / ".claude" / "hooks" / "session-banner.sh"
    hook.parent.mkdir(parents=True)
    hook.write_text(texte, encoding="utf-8")
    dossier = depot / ".agents" / "security" / "banner"
    dossier.mkdir(parents=True)
    for nom in ("message.oct", "revoked"):
        shutil.copyfile(DONNEES / nom, dossier / nom)
    maison = racine / "maison"
    maison.mkdir()
    b = Banc(racine=racine, depot=depot, maison=maison, hook=hook, bash=bash, cles=cles, espace_hook=espaces[0])
    b.signers(b.ligne_signer("pilote"))
    return b


def _affiche(b: Banc, p: subprocess.CompletedProcess, quoi: str) -> None:
    assert p.returncode == 0, f"{quoi} : rc {p.returncode}, stderr={p.stderr[-200:]!r}"
    assert p.stdout == b.attendu(), f"{quoi} : bannière attendue, stdout={p.stdout[:120]!r}"


def _tait(p: subprocess.CompletedProcess, quoi: str) -> None:
    assert p.returncode == 0, f"{quoi} : rc {p.returncode}, stderr={p.stderr[-200:]!r}"
    assert p.stdout == b"", f"{quoi} : silence attendu, stdout={p.stdout[:120]!r}"


# ---------------------------------------------------------------------------
# LES CAS — des fonctions, pour être rejoués sur chaque mutant
# ---------------------------------------------------------------------------
def cas_c1(b: Banc) -> None:
    p = b.jouer()
    _affiche(b, p, "C1 sans jeton")
    assert list(json.loads(p.stdout)) == ["systemMessage"], "C1 : la ligne n'est pas un JSON de clé unique systemMessage"


def cas_c2(b: Banc) -> None:
    b.poser_annexe_d()
    _tait(b.jouer(), "C2 jeton valide (annexe D)")


def cas_c3(b: Banc) -> None:
    b.poser(_jeton(expires=_jour(0)))
    _affiche(b, b.jouer(), "C3 expires = aujourd'hui")
    b.poser(_jeton(expires=_jour(1)))
    _tait(b.jouer(), "C3 contrôle : expires = demain")


def cas_c4(b: Banc) -> None:
    jeton = b.poser_annexe_d()
    _tait(b.jouer(), "C4 contrôle : jeton non révoqué")
    rev = b.dossier / "revoked"
    vierge = rev.read_bytes()
    b.revoquer()
    _affiche(b, b.jouer(), "C4 id révoqué")
    # Revue de sécurité S-00004661 : une ligne collée depuis un éditeur Windows
    # (CRLF) ou indentée révoque quand même ; une AUTRE ligne ne révoque pas.
    ligne = next(x for x in jeton.split(b"\n") if x.startswith(b"id="))
    for nom, forme in (("CRLF", ligne + b"\r\n"), ("blancs de tête", b"  \t" + ligne + b"\n"),
                       ("blancs de fin et CR", ligne + b" \t\r\n")):
        rev.write_bytes(vierge + forme)
        _affiche(b, b.jouer(), f"C4 id révoqué ({nom})")
    rev.write_bytes(vierge + b"  id=autre-t1228\r\n")
    _tait(b.jouer(), "C4 contrôle : une autre ligne, même tolérée, ne révoque pas")


def cas_c5(b: Banc) -> None:
    b.poser(_jeton())
    b.off.write_bytes(_jeton(expires="20341008"))
    _affiche(b, b.jouer(), "C5 charge altérée après signature")


def cas_c6(b: Banc) -> None:
    b.poser(_jeton(), espace="autre")
    _affiche(b, b.jouer(), "C6 autre espace de noms")


def cas_c7(b: Banc) -> None:
    b.poser(_jeton(), cle="attaquant")
    _affiche(b, b.jouer(), "C7 autre clé")


def cas_c7b(b: Banc) -> None:
    b.signers(b.ligne_signer("attaquant"))
    b.poser(_jeton(), cle="attaquant")
    _affiche(b, b.jouer(), "C7b allowed_signers d'attaquant (épingle)")


def cas_c8(b: Banc) -> None:
    b.signers(b.ligne_signer("pilote"), b.ligne_signer("attaquant"))
    b.poser(_jeton(), cle="attaquant")
    _affiche(b, b.jouer(), "C8 seconde ligne d'attaquant")


def _copie_path(b: Banc, nom: str, outils: list[str]) -> Path:
    dossier = b.racine / nom
    dossier.mkdir()
    for o in outils:
        src = shutil.which(o, path="/usr/bin:/bin")
        assert src, f"{o} absent de /usr/bin:/bin"
        try:
            (dossier / o).symlink_to(src)
        except OSError as e:
            pytest.skip(f"C9 : lien symbolique impossible ici ({e})")
    texte = b.hook.read_text(encoding="utf-8")
    assert texte.count("PATH=/usr/bin:/bin\n") == 1, "C9 : la ligne PATH figée est introuvable"
    copie = b.racine / f"{nom}.sh"
    copie.write_text(texte.replace("PATH=/usr/bin:/bin\n", f"PATH={dossier}\n"), encoding="utf-8")
    return copie


def cas_c9(b: Banc) -> None:
    b.poser(_jeton())
    avec = _copie_path(b, "outils-avec", ["date", "grep", "sed", "ssh-keygen"])
    _tait(b.jouer(hook=avec), "C9 contrôle : PATH réécrit AVEC ssh-keygen")
    sans = _copie_path(b, "outils-sans", ["date", "grep", "sed"])
    _affiche(b, b.jouer(hook=sans), "C9 ssh-keygen absent")


GRAMMAIRE = {
    "ligne en trop": _jeton() + b"extra=1\n",
    "ligne manquante": b"kind=banner-off\nscope=global\nid=x\n",
    "expires non numérique": _jeton(expires="2034100A"),
    "kind=autre": _jeton().replace(b"kind=banner-off", b"kind=autre"),
    "scope=local": _jeton().replace(b"scope=global", b"scope=local"),
    "clés réordonnées": b"scope=global\nkind=banner-off\nid=x\nexpires=20341007\n",
    "sans saut final": _jeton()[:-1],
    "CRLF": _jeton().replace(b"\n", b"\r\n"),
    "id vide": _jeton(ident=""),
}


def cas_c10(b: Banc) -> None:
    b.poser(_jeton())
    _tait(b.jouer(), "C10 contrôle : grammaire exacte")
    for nom, contenu in GRAMMAIRE.items():
        b.poser(contenu)
        _affiche(b, b.jouer(), f"C10 {nom}")


def _repli(p: subprocess.CompletedProcess, quoi: str) -> None:
    assert p.returncode == 0, f"{quoi} : rc {p.returncode}"
    try:
        d = json.loads(p.stdout)
    except ValueError:
        raise AssertionError(f"{quoi} : le repli n'est pas une ligne JSON — stdout={p.stdout[:120]!r}") from None
    assert list(d) == ["systemMessage"] and "message.oct" in d["systemMessage"], f"{quoi} : repli hors forme {d!r}"


def cas_c11(b: Banc) -> None:
    msg = b.dossier / "message.oct"
    reel = msg.read_bytes()
    msg.unlink()
    _repli(b.jouer(), "C11 message.oct absent")
    msg.write_bytes(reel.replace(b"\\0173", b"\\0133", 1))
    _repli(b.jouer(), "C11 message.oct altéré (forme)")
    msg.write_bytes(reel.replace(b"\\0056", b"\\0012", 1))
    _repli(b.jouer(), "C11 message.oct à saut de ligne brut")


def cas_c15(chemin: Path) -> None:
    brut = chemin.read_bytes()
    assert brut.endswith(b"\n") and brut.count(b"\n") == 1, "C15 : message.oct n'est pas UNE ligne"
    octets = _decoder(brut[:-1].decode("ascii"))
    assert hashlib.sha256(octets).hexdigest() == SHA256_DECODE, "C15 : le décodage a changé (sha256 épinglé)"
    d = json.loads(octets)
    assert list(d) == ["systemMessage"]
    texte = d["systemMessage"]
    lignes = texte.split("\n")
    assert texte.startswith("\n"), "C15 : le message n'ouvre pas par \\n (préfixe de l'hôte)"
    assert len(lignes) <= LIGNES_MAX and max(len(x) for x in lignes) <= COLONNES_MAX
    rangs = [x for x in lignes[1:-1] if x]
    assert len(rangs) == 5, f"C15 : {len(rangs)} rangs pointillés au lieu de 5"
    assert all(set(x) <= RANG for x in rangs), "C15 : un rang porte autre chose que des points et des blancs"
    assert SIGNATURE_RE.fullmatch(lignes[-1]), "C15 : la dernière ligne n'est pas une signature en lettres ASCII"


def cas_c17(hook: Path, depot: Path, bash: str, maison: Path) -> None:
    p = subprocess.run([bash, "-p", str(hook)], env=_env(depot, maison), stdin=subprocess.DEVNULL,
                       capture_output=True, timeout=60, check=False)
    assert p.returncode == 0, f"C17 : rc {p.returncode}"
    attendu = _decoder_fichier(depot / ".agents" / "security" / "banner" / "message.oct")
    assert p.stdout == attendu, f"C17 : bannière attendue sur l'arbre, HOME vide — stdout={p.stdout[:120]!r}"


def cas_c17_banc(b: Banc) -> None:
    cas_c17(b.hook, b.depot, b.bash, b.maison)


def cas_c18(b: Banc) -> None:
    b.poser(_jeton())
    p = b.jouer(maison=False)
    _affiche(b, p, "C18 HOME absent")
    assert b"unbound" not in p.stderr, f"C18 : avortement bruyant {p.stderr[-160:]!r}"


def cas_c19(b: Banc) -> None:
    shim = b.racine / "shim"
    shim.mkdir()
    faux = shim / "ssh-keygen"
    faux.write_text("#!/bin/sh\n/bin/cat >/dev/null\necho \"256 " + b.cles["pilote"].empreinte
                    + " shim (ED25519)\"\nexit 0\n", encoding="utf-8")
    faux.chmod(0o755)
    b.poser(_jeton(), cle="attaquant")
    p = b.jouer(path=str(shim) + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin"))
    _affiche(b, p, "C19 ssh-keygen factice en tête du PATH")


def cas_c20(b: Banc) -> None:
    """Constat 1 de l'exec-critic (S-00004625) : un jeton NON SIGNÉ de 1 Mio à
    en-tête valide. Sans borne, l'expansion de motif bash est superlinéaire
    (plus de 90 s mesurées) : l'hôte tuerait le hook, la bannière serait perdue.
    Attendu : bannière en moins de 2 s ; délai du sous-processus 10 s."""
    gros = b"kind=banner-off\nscope=global\nid=" + b"a" * (1 << 20) + b"\nexpires=20341007\n"
    b.off.parent.mkdir(parents=True, exist_ok=True)
    b.off.write_bytes(gros)
    b.off.with_name("off.sig").write_bytes(b"x\n")
    debut = time.monotonic()
    try:
        p = b.jouer(delai=10)
    except subprocess.TimeoutExpired:
        raise AssertionError("C20 : le hook ne rend pas en 10 s sur un jeton de 1 Mio") from None
    duree = time.monotonic() - debut
    _affiche(b, p, "C20 jeton de 1 Mio")
    assert duree < 2, f"C20 : {duree:.1f} s sur un jeton de 1 Mio (attendu < 2 s)"


def cas_c21(b: Banc) -> None:
    """allowed_signers borné à 64 lignes (exec-critic it. 2, survivant N4) : 65
    lignes commentées + la ligne de clé ⇒ bannière ; contrôle : 63 + 1 ⇒ silence."""
    ligne = b.ligne_signer("pilote")
    b.poser(_jeton())
    (b.dossier / "allowed_signers").write_text("# c\n" * 63 + ligne + "\n", encoding="utf-8")
    _tait(b.jouer(), "C21 contrôle : 64 lignes en tout")
    (b.dossier / "allowed_signers").write_text("# c\n" * 65 + ligne + "\n", encoding="utf-8")
    _affiche(b, b.jouer(), "C21 allowed_signers de 66 lignes")


CAS: dict[str, Callable[[Banc], None]] = {
    "C1": cas_c1, "C2": cas_c2, "C3": cas_c3, "C4": cas_c4, "C5": cas_c5, "C6": cas_c6,
    "C7": cas_c7, "C7b": cas_c7b, "C8": cas_c8, "C9": cas_c9, "C10": cas_c10, "C11": cas_c11,
    "C17": cas_c17_banc, "C18": cas_c18, "C19": cas_c19, "C20": cas_c20, "C21": cas_c21,
}


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def cles(tmp_path_factory) -> dict[str, Cle]:
    _exiger_outils()
    d = tmp_path_factory.mktemp("cles")
    out: dict[str, Cle] = {}
    for nom in ("pilote", "attaquant"):
        k = d / nom
        p = _ssh("-q", "-t", "ed25519", "-N", "", "-C", f"banc {nom}", "-f", str(k), maison=d)
        assert p.returncode == 0, p.stderr
        blob = k.with_name(nom + ".pub").read_text(encoding="utf-8").split()[1]
        out[nom] = Cle(prive=k, blob=blob, empreinte=_empreinte("ssh-ed25519 " + blob))
    assert out["pilote"].empreinte != out["attaquant"].empreinte
    return out


@pytest.fixture(params=BASHES or ["<aucun bash>"])
def banc(request, tmp_path, cles) -> Banc:
    return fabriquer(tmp_path, request.param, cles)


# ---------------------------------------------------------------------------
# LES TESTS
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nom", sorted(CAS))
def test_cas(nom, banc):
    CAS[nom](banc)


def test_c12_enregistrement():
    d = json.loads(SETTINGS.read_text(encoding="utf-8"))
    blocs = d["hooks"]["SessionStart"]
    trouves = [(b.get("matcher"), h) for b in blocs for h in b.get("hooks", [])
               if h.get("command", "").endswith(QUEUE_BANNIERE)]
    assert len(trouves) == 1, f"C12 : {len(trouves)} jambe(s) session-banner.sh au SessionStart"
    matcher, h = trouves[0]
    assert matcher == MATCHER, f"C12 : matcher {matcher!r}"
    assert h.get("type") == "command" and h.get("shell") == "bash", f"C12 : {h.get('type')!r}/{h.get('shell')!r}"
    assert set(h) == {"type", "shell", "command"}, f"C12 : clés {sorted(h)!r} (liste blanche : type, shell, command)"
    hors = [k for k in d.get("env", {}) if not env_permise(k)]
    assert hors == [], f"C12 : settings.json porte {hors!r} dans env, hors de la liste blanche (S-00004646)"
    # (b) tout arbre, adoptant compris : aucune clé que l'hôte ignore en portée projet. AVANT (a) : un `env`
    # à la seule clé d'intervalle (non ignorée) rougit alors par (a), preuve que (b) est passé.
    ignorees = [k for k in d.get("env", {}) if refusee_portee_projet(k)]
    assert ignorees == [], (f"C12 : settings.json porte {ignorees!r} dans env, que Claude Code 2.1.299 ignore en "
                            "portée projet ; la télémétrie se pose en portée UTILISATEUR (T-01M4WNKCBXS893CHPSKD1Z1PN9)")
    # (a) le kit seul : vacuité ÉPINGLÉE À DESSEIN, son settings.json suivi ne porte AUCUN env.
    if EST_LE_KIT:
        assert d.get("env", {}) == {}, (f"C12 : le settings.json suivi du kit porte env={d.get('env')!r} ; il n'en "
                                        "porte aucun (T-01M4WNKCBXS893CHPSKD1Z1PN9)")
    anciens = [b for b in blocs if b.get("matcher") is None
               and any(x.get("command", "").endswith(QUEUE_SESSION_START) for x in b.get("hooks", []))]
    assert len(anciens) == 1, "C12 : le bloc session-start.sh (sans matcher) n'est plus intact"


def test_liste_blanche_env_egale_bloc_recommande():
    """Source de ENV_PERMISES (S-01M4X6HVWK2E67ARX45NV6FB17) : la liste du banc ET celle relevée dans
    protect-paths.sh sont ÉGALES aux clés de télémétrie du bloc utilisateur recommandé ;
    CONTEXT_RETRO_PCT et CLAUDE_CODE_SHELL, du même bloc, restent hors liste."""
    if not RECOMMANDE.is_file():
        assert not EST_LE_KIT, f"{RECOMMANDE.relative_to(ROOT)} absent du kit"
        pytest.skip(f"SAUT ANNONCÉ : {RECOMMANDE.relative_to(ROOT)} absent (arbre adoptant), source de la "
                    "liste blanche non jugée")
    env = json.loads(RECOMMANDE.read_text(encoding="utf-8"))["env"]
    telemetrie = {k for k in env if k == "CLAUDE_CODE_ENABLE_TELEMETRY" or k.startswith("OTEL_")}
    blocs = re.findall(r"^ENV_PERMISES = \(([^)]*)\)", PROTECT.read_text(encoding="utf-8"), flags=re.M)
    assert len(blocs) == 1, f"{len(blocs)} bloc(s) ENV_PERMISES dans protect-paths.sh (1 attendu)"
    garde = set(re.findall(r'"([^"]*)"', blocs[0]))
    assert set(ENV_PERMISES) == telemetrie, f"banc : écart {sorted(set(ENV_PERMISES) ^ telemetrie)!r} avec la source"
    assert garde == telemetrie, f"protect-paths.sh : écart {sorted(garde ^ telemetrie)!r} avec la source"
    assert not {"CONTEXT_RETRO_PCT", "CLAUDE_CODE_SHELL"} & (set(ENV_PERMISES) | garde), \
        "CONTEXT_RETRO_PCT et CLAUDE_CODE_SHELL restent hors de la liste blanche (S-01M4X6HVWK2E67ARX45NV6FB17)"


def test_c15_message_reel():
    cas_c15(DONNEES / "message.oct")


def test_c16_epingle():
    _exiger_outils()
    pubs = sorted(DONNEES.glob("*.pub"))
    assert len(pubs) == 1, f"C16 : {len(pubs)} clé(s) publique(s) sous le dossier de la bannière"
    champs = pubs[0].read_text(encoding="utf-8").split()
    fp_pub = _empreinte(champs[0] + " " + champs[1])
    lignes = [x for x in (DONNEES / "allowed_signers").read_text(encoding="utf-8").splitlines()
              if x.strip() and not x.lstrip().startswith("#")]
    assert len(lignes) == 1, "C16 : allowed_signers ne porte pas UNE ligne"
    morceaux = lignes[0].split(" ")
    assert morceaux[:2] == ["banner@cadre", 'namespaces="cadre-banner"'], f"C16 : ligne hors forme {morceaux[:2]!r}"
    fp_signers = _empreinte(" ".join(morceaux[2:4]))
    epingles = re.findall(r"^EMPREINTE='(SHA256:[A-Za-z0-9+/]+)'$", HOOK.read_text(encoding="utf-8"), re.M)
    assert epingles == [EMPREINTE_REELLE], f"C16 : épingle du hook {epingles!r}"
    assert fp_pub == fp_signers == EMPREINTE_REELLE, f"C16 : .pub {fp_pub} / allowed_signers {fp_signers}"


@pytest.mark.parametrize("bash", BASHES or ["<aucun bash>"])
def test_c17_arbre_reel(bash, tmp_path):
    _exiger_outils()
    vide = tmp_path / "maison-vide"
    vide.mkdir()
    cas_c17(HOOK, ROOT, bash, vide)


@pytest.mark.skipif(not Path("/bin/bash").is_file(), reason="pas de /bin/bash sur cet hôte")
def test_parse_bash_systeme():
    """Le filet bash-parse-oldest, rejoué ici sur ce seul fichier : /bin/bash
    (3.2 sur macOS) le parse. Le RUNTIME 3.2 est couvert par les cas, joués sous
    chaque bash disponible."""
    p = subprocess.run(["/bin/bash", "-n", str(HOOK)], capture_output=True, timeout=30, check=False)
    assert p.returncode == 0, p.stderr


def _injecter_avortement(texte: str) -> str:
    assert texte.count("  maison=${HOME:-}\n") == 1
    return texte.replace("  maison=${HOME:-}\n", "  exit 3\n  maison=${HOME:-}\n")


def test_avortement_en_tete_affiche_quand_meme(tmp_path, cles):
    """C3 du plan-critic : un avortement AU MILIEU de la chaîne (forme bash >= 4
    sous 3.2, variable non liée…) sort par le trap EXIT — la bannière s'affiche
    et le rc reste 0. Simulé par un `exit 3` en tête de `jeton_valide`."""
    _exiger_outils()
    texte = _injecter_avortement(HOOK.read_text(encoding="utf-8"))
    for i, bash in enumerate(BASHES):
        b = fabriquer(tmp_path / f"b{i}", bash, cles, texte)
        b.poser(_jeton())
        cas_c1(b)
        cas_c17_banc(b)


# ---------------------------------------------------------------------------
# LES MUTANTS — chacun doit faire rougir au moins un cas désigné
# ---------------------------------------------------------------------------
def _remplacer(*paires: tuple[str, str]) -> Callable[[str], str]:
    def f(texte: str) -> str:
        for avant, apres in paires:
            assert texte.count(avant) == 1, f"mutation inapplicable : {avant!r} présent {texte.count(avant)} fois"
            texte = texte.replace(avant, apres)
        return texte
    return f


def _repli_muet(texte: str) -> str:
    out, n = re.subn(r"^REPLI='.*'$", "REPLI=''", texte, flags=re.M)
    assert n == 1, "mutation inapplicable : ligne REPLI"
    return out


def _espace_autre(texte: str) -> str:
    assert texte.count("cadre-banner") >= 2, "mutation inapplicable : espace de noms"
    return texte.replace("cadre-banner", "autre")


def _trap_retire(texte: str) -> str:
    return _remplacer(("trap afficher EXIT\n", ":\n"), ("fi\nexit 0\n", "fi\nafficher\n"))(_injecter_avortement(texte))


MUTANTS_HOOK: dict[str, tuple[Callable[[str], str], list[str]]] = {
    "M1 expiration ignorée": (_remplacer(('[ "$aujourdhui" -lt "$expires" ] || return 1', ":")), ["C3"]),
    "M2 révocation ignorée": (_remplacer(('[ "$rc" -eq 1 ] || return 1', ":")), ["C4"]),
    "M3 présence tenue pour validité": (_remplacer(('[ -f "$off.sig" ] || return 1\n',
                                                     '[ -f "$off.sig" ] || return 1\n  return 0\n')),
                                        ["C5", "C6", "C7", "C10"]),
    "M4 épingle retirée": (_remplacer(('[ "$fp" = "$EMPREINTE" ] || return 1', ":")), ["C7b"]),
    "M5 espace de noms non imposé": (_espace_autre, ["C6"]),
    "M6 repli muet": (_repli_muet, ["C11"]),
    "M7 unicité de ligne retirée": (_remplacer(('[ "$n" -eq 1 ] || return 1', ":")), ["C8"]),
    "M11 trap retiré, avortement en tête de chaîne": (_trap_retire, ["C1", "C17"]),
    "M11b false en tête de chaîne": (_remplacer(("  maison=${HOME:-}\n", "  false || return 1\n  maison=${HOME:-}\n")),
                                     ["C2"]),
    "M13 PATH non figé": (_remplacer(("PATH=/usr/bin:/bin\n", ":\n")), ["C19"]),
    "M32 révocation intolérante (CR, blancs de bord)": (_remplacer(
        ("  revues=$(sed -e \"s/$CR//g\" -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \"$DOSSIER/revoked\" 2>/dev/null) || return 1\n"
         "  printf '%s\\n' \"$revues\" | grep -qxF -- \"id=$id\"\n",
         "  grep -qxF -- \"id=$id\" \"$DOSSIER/revoked\"\n")), ["C4"]),
    "M19 borne des 64 lignes d'allowed_signers retirée": (_remplacer(('    [ "$lus" -le 64 ] || return 1\n', "    :\n")),
                                                          ["C21"]),
    "M15 borne du jeton retirée": (_remplacer(("IFS= read -r -n 257 -d '' tok < \"$off\" || true\n"
                                               "  [ \"${#tok}\" -le 256 ] || return 1\n",
                                               "IFS= read -r -d '' tok < \"$off\" || true\n")), ["C20"]),
}


@pytest.mark.parametrize("nom", sorted(MUTANTS_HOOK))
def test_mutant_hook_tue(nom, tmp_path, cles):
    _exiger_outils()
    muter, designes = MUTANTS_HOOK[nom]
    texte = muter(HOOK.read_text(encoding="utf-8"))
    rouges = []
    for c in designes:
        b = fabriquer(tmp_path / c, BASHES[0], cles, texte)
        try:
            CAS[c](b)
        except AssertionError:
            rouges.append(c)
    assert rouges, f"{nom} SURVIT : aucun de {designes} ne rougit"


def test_mutant_m8_point_bascule(tmp_path):
    """M8 : un point basculé en espace dans message.oct ⇒ C15 rougit."""
    reel = (DONNEES / "message.oct").read_bytes()
    assert reel.count(b"\\0056") > 0
    mute = tmp_path / "message.oct"
    mute.write_bytes(reel.replace(b"\\0056", b"\\0040", 1))
    with pytest.raises(AssertionError):
        cas_c15(mute)


# ---------------------------------------------------------------------------
# LE VERROU (plan, étape 5) — C13, C14, la dérivation safe-bash, M9, M10, M12, M14.
# Les gardes sont rejouées sur un projet JETABLE (copie de protect-paths.sh, de
# safe-bash.sh, d'emit-event.sh et de settings.json), AGENTS_EVENTS_DIR pointé
# sur un dossier jetable : aucun `hook.deny` ne s'écrit sous `.agents/state/`.
# ---------------------------------------------------------------------------
GARDES = (".claude/hooks/protect-paths.sh", ".claude/hooks/emit-event.sh", ".claude/hooks/safe-bash.sh")
PROTECT = ROOT / ".claude" / "hooks" / "protect-paths.sh"
DENY_BANNIERE = ("Edit(./.agents/security/banner/**)", "Edit(./.claude/hooks/session-banner.sh)")
QUEUE_PROTECT = 'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/protect-paths.sh"'
# T-01M4JRFS0T : une jambe de garde se repère par son SUFFIXE, nue ou enveloppée sous garde-fermee.
SUFFIXE_PROTECT = '/.claude/hooks/protect-paths.sh"'
SUFFIXE_SAFE = '/.claude/hooks/safe-bash.sh"'
QUEUE_HOOKS = 'exec bash -p "$CLAUDE_PROJECT_DIR/.claude/hooks/'
LANCEUR_ENVELOPPE = 'AGENTS_HOOK_HOST=claude exec bash -p "$CLAUDE_PROJECT_DIR/.agents/security/garde-fermee.sh" --echeance='
ARMES_DONNEES = "donnée de la bannière de marque"
ARMES_HOOK = "hook de la bannière de marque"
ARMES_LANCEUR = "lanceur des jambes de garde enveloppées"


@dataclass
class Projet:
    depot: Path
    maison: Path
    evenements: Path
    bash: str

    def env(self) -> dict[str, str]:
        e = _env(self.depot, self.maison)
        e["AGENTS_EVENTS_DIR"] = str(self.evenements)
        return e

    def edit(self, charge: dict) -> subprocess.CompletedProcess:
        return subprocess.run([self.bash, "-p", str(self.depot / ".claude/hooks/protect-paths.sh")],
                              input=json.dumps(charge).encode("utf-8"), env=self.env(), cwd=str(self.depot),
                              capture_output=True, timeout=60, check=False)

    def bash_cmd(self, commande: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.bash, "-p", str(self.depot / ".claude/hooks/safe-bash.sh")],
                              input=json.dumps({"tool_input": {"command": commande}}).encode("utf-8"),
                              env=self.env(), cwd=str(self.depot), capture_output=True, timeout=60, check=False)

    @property
    def reglages(self) -> Path:
        return self.depot / ".claude" / "settings.json"


def _sans_cle_double(paires: list[tuple[str, object]]) -> dict:
    cles = [k for k, _ in paires]
    assert len(cles) == len(set(cles)), f"C14 : clé en double dans la copie de settings.json : {cles}"
    return dict(paires)


def _poser_env_synthetique(reglages: Path) -> None:
    """ENV_SYNTHETIQUE inséré juste après le `{` initial de la COPIE, une fois. Le settings.json suivi
    n'a plus d'`env` (T-01M4WNKCBXS893CHPSKD1Z1PN9) : le reste est recopié octet pour octet. Chez un
    adoptant dont le settings.json projet en porte un, cet `env` est REMPLACÉ — la copie est
    re-sérialisée sans lui (indent 2, la forme du fichier suivi) avant l'insertion —, jamais doublé :
    json.loads accepterait la clé en double en silence, d'où le contrôle par object_pairs_hook."""
    brut = reglages.read_bytes()
    doc = json.loads(brut)
    if "env" in doc:
        del doc["env"]
        brut = (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    tete = b"{\n"
    assert brut.startswith(tete), "C14 : la copie de settings.json n'ouvre pas sur « {\\n »"
    bloc = '  "env": ' + json.dumps(ENV_SYNTHETIQUE, indent=2).replace("\n", "\n  ") + ",\n"
    reglages.write_bytes(tete + bloc.encode("utf-8") + brut[len(tete):])
    pose = json.loads(reglages.read_bytes(), object_pairs_hook=_sans_cle_double)
    assert pose["env"] == ENV_SYNTHETIQUE, "C14 : env synthétique mal inséré"


def projet_gardes(racine: Path, bash: str, texte_protect: str | None = None) -> Projet:
    depot = racine / "projet"
    depot.mkdir(parents=True)
    p = subprocess.run(["git", "init", "-q", str(depot)], capture_output=True, timeout=60, check=False,
                       env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(racine)})
    assert p.returncode == 0, p.stderr
    for rel in GARDES:
        dst = depot / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, dst)
    if texte_protect is not None:
        (depot / ".claude" / "hooks" / "protect-paths.sh").write_text(texte_protect, encoding="utf-8")
    reglages = depot / ".claude" / "settings.json"
    shutil.copyfile(SETTINGS, reglages)
    _poser_env_synthetique(reglages)
    maison = racine / "maison"
    maison.mkdir()
    evenements = racine / "evenements"
    evenements.mkdir()
    return Projet(depot=depot, maison=maison, evenements=evenements, bash=bash)


def _sans_banniere(d: dict) -> dict:
    d["hooks"]["SessionStart"] = [b for b in d["hooks"]["SessionStart"]
                                  if not any(h.get("command", "").endswith(QUEUE_BANNIERE) for h in b.get("hooks", []))]
    return d


def _jambe(d: dict) -> dict:
    return next(h for b in d["hooks"]["SessionStart"] for h in b.get("hooks", [])
                if h.get("command", "").endswith(QUEUE_BANNIERE))


def _muter_jambe(cle: str, valeur) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        h = _jambe(d)
        if valeur is None:
            del h[cle]
        else:
            h[cle] = valeur
        return d
    return f


def _commande_neutralisee(d: dict) -> dict:
    _jambe(d)["command"] = "true # " + QUEUE_BANNIERE
    return d


def _prefixe_coherent(d: dict) -> dict:
    """La borne DITE : une réécriture cohérente du préfixe de TOUTES les jambes
    (T-964) passe — la jambe de la bannière suit les gardes."""
    prefixe = _prefixe_garde(_jambe_protect(d)["command"])
    for blocs in d["hooks"].values():
        for b in blocs:
            for h in b["hooks"]:
                h["command"] = h["command"].replace(prefixe, prefixe + ": ; ", 1)
    d["statusLine"]["command"] = d["statusLine"]["command"].replace(prefixe, prefixe + ": ; ", 1)
    return d


def _garde_factice(d: dict) -> dict:
    """Le vecteur fermé par le préfixe UNIQUE : une jambe protect-paths FACTICE
    au préfixe neutre est ajoutée (la vraie reste), et la bannière s'y aligne."""
    d["hooks"]["PreToolUse"].append({"matcher": "Edit|Write", "hooks": [
        {"type": "command", "shell": "bash", "command": "exit 0; " + QUEUE_PROTECT}]})
    _jambe(d)["command"] = "exit 0; " + QUEUE_BANNIERE
    return d


def _migration_une_jambe(d: dict) -> dict:
    """Le coût DIT : la jambe protect-paths seule change de préfixe ⇒ deux
    préfixes ⇒ l'enregistrement n'est plus porté ⇒ refus."""
    for b in d["hooks"]["PreToolUse"]:
        for h in b["hooks"]:
            if h["command"].endswith(SUFFIXE_PROTECT):
                h["command"] = ": ; " + h["command"]
    return d


def _matcher_banniere(valeur: str) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        for b in d["hooks"]["SessionStart"]:
            if any(h.get("command", "").endswith(QUEUE_BANNIERE) for h in b.get("hooks", [])):
                b["matcher"] = valeur
        return d
    return f


def _bloc_protect(d: dict) -> dict:
    return next(b for b in d["hooks"]["PreToolUse"] if any(h["command"].endswith(SUFFIXE_PROTECT) for h in b["hooks"]))


def _jambe_protect(d: dict) -> dict:
    return next(h for h in _bloc_protect(d)["hooks"] if h["command"].endswith(SUFFIXE_PROTECT))


def _prefixe_garde(commande: str) -> str:
    """Le préfixe d'une jambe de garde, pris devant `AGENTS_HOOK_HOST=claude exec bash -p` (enveloppée)
    ou devant `exec bash -p` (nue) — jamais coupé par une longueur de queue (T-01M4JRFS0T, C4)."""
    for queue in (LANCEUR_ENVELOPPE, QUEUE_HOOKS):
        i = commande.rfind(queue)
        if i >= 0:
            return commande[:i]
    raise AssertionError(f"C14 : jambe de garde sans queue reconnue : {commande[-120:]!r}")


def _formes_gardes(enveloppe: bool, echeance: int = 7, delai: int = 10) -> Callable[[dict], dict]:
    """Les jambes protect-paths et safe-bash réécrites sous UNE forme : enveloppée (garde-fermee,
    `--echeance=N`, clé `timeout`) ou nue (trois clés). L'état de départ se CONSTRUIT : la copie
    suivie peut porter l'une ou l'autre (T-01M4JRFRSM), un témoin ne s'y fie pas (C5)."""
    def f(d: dict) -> dict:
        for b in d["hooks"]["PreToolUse"]:
            for h in b["hooks"]:
                for suffixe in (SUFFIXE_PROTECT, SUFFIXE_SAFE):
                    if h["command"].endswith(suffixe):
                        cible = '"$CLAUDE_PROJECT_DIR' + suffixe
                        if enveloppe:
                            h["command"] = _prefixe_garde(h["command"]) + LANCEUR_ENVELOPPE + f"{echeance} {cible}"
                            h["timeout"] = delai
                        else:
                            h["command"] = _prefixe_garde(h["command"]) + "exec bash -p " + cible
                            h.pop("timeout", None)
        return d
    return f


def _muter_protect(cle: str, valeur) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        h = _jambe_protect(d)
        if valeur is None:
            del h[cle]
        else:
            h[cle] = valeur
        return d
    return f


def _commande_protect(avant: str, apres: str) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        h = _jambe_protect(d)
        assert h["command"].count(avant) == 1, f"C14 : {avant!r} absent ou multiple dans la jambe protect-paths"
        h["command"] = h["command"].replace(avant, apres)
        return d
    return f


def _prefixe_ouvert(ajout: str) -> Callable[[dict], dict]:
    """Clôture T-01M4JRFS0T : `ajout` collé derrière le préfixe de TOUTES les jambes qui le portent
    (bannière et gardes, réécriture cohérente). `env -u ` fait sortir une garde enveloppée rc 125,
    lue comme un accord : le préfixe unique doit rester CLOS (PREFIXE_CLOS)."""
    def f(d: dict) -> dict:
        p = _prefixe_garde(_jambe_protect(d)["command"])
        for blocs in d["hooks"].values():
            for b in blocs:
                for h in b["hooks"]:
                    if h["command"].startswith(p):
                        h["command"] = p + ajout + h["command"][len(p):]
        return d
    return f


def _sans_protect(d: dict) -> dict:
    """Constat 4 : la jambe protect-paths retirée (safe-bash reste) éteindrait la
    règle de contenu au tour suivant — c'est une garantie, refusée."""
    b = _bloc_protect(d)
    b["hooks"] = [h for h in b["hooks"] if not h["command"].endswith(SUFFIXE_PROTECT)]
    return d


def _matcher_protect(valeur: str) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        _bloc_protect(d)["matcher"] = valeur
        return d
    return f


def _bloc_safe(d: dict) -> dict:
    return next(b for b in d["hooks"]["PreToolUse"] if any(h["command"].endswith(SUFFIXE_SAFE) for h in b["hooks"]))


def _sans_safe(d: dict) -> dict:
    """Constat 4 de l'it. 2 : la jambe safe-bash retirée laisserait passer, au
    tour suivant, les redirections vers les fichiers de la bannière."""
    b = _bloc_safe(d)
    b["hooks"] = [h for h in b["hooks"] if not h["command"].endswith(SUFFIXE_SAFE)]
    return d


def _matcher_safe(valeur: str) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        _bloc_safe(d)["matcher"] = valeur
        return d
    return f


def _async_protect(d: dict) -> dict:
    _jambe_protect(d)["async"] = True
    return d


def _poser(cle: str, valeur) -> Callable[[dict], dict]:
    def f(d: dict) -> dict:
        d[cle] = valeur
        return d
    return f


def cas_c14(pr: Projet) -> None:
    """protect-paths.sh, rejoué. Chaque ligne : (étiquette, charge, rc attendu, aiguille de stderr)."""
    reel = pr.reglages.read_text(encoding="utf-8")
    doc = json.loads(reel)
    reg = str(pr.reglages)
    hors = str(pr.maison / ".claude-op" / "settings.json")
    hors_local = str(pr.maison / ".claude-op" / "settings.local.json")
    queue_json = 'exec bash -p \\"$CLAUDE_PROJECT_DIR/.claude/hooks/session-banner.sh\\"'
    assert reel.count(queue_json) == 1, "C14 : la queue de la jambe n'est pas unique dans settings.json"
    deny_json = '"Edit(./.agents/security/banner/**)",\n'
    assert reel.count(deny_json) == 1, "C14 : la ligne deny de la bannière n'est pas unique"
    otel = '"OTEL_METRIC_EXPORT_INTERVAL": "5000"'
    point = '"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318"'
    permissions = '"permissions": {'
    assert all(reel.count(a) == 1 for a in (otel, point, permissions, '"Bash(docker rm*)"')), "C14 : ancres d'Edit introuvables"

    def ecrire(chemin: str, contenu: str) -> dict:
        return {"tool_name": "Write", "tool_input": {"file_path": chemin, "content": contenu}}

    def ecrire_doc(muter: Callable[[dict], dict]) -> dict:
        return ecrire(reg, json.dumps(muter(json.loads(reel)), indent=2, ensure_ascii=False) + "\n")

    def editer(avant: str, apres: str, chemin: str = reg) -> dict:
        return {"tool_name": "Edit", "tool_input": {"file_path": chemin, "old_string": avant, "new_string": apres}}

    lignes = [
        ("revoked", ecrire(".agents/security/banner/revoked", "id=x\n"), 2, ARMES_DONNEES),
        ("allowed_signers", ecrire(".agents/security/banner/allowed_signers", "x\n"), 2, ARMES_DONNEES),
        ("message.oct", ecrire(".agents/security/banner/message.oct", "x\n"), 2, ARMES_DONNEES),
        ("une .pub, tout nom", ecrire(".agents/security/banner/x.pub", "x\n"), 2, ARMES_DONNEES),
        ("le hook", editer("a", "b", ".claude/hooks/session-banner.sh"), 2, ARMES_HOOK),
        ("casse", ecrire(".AGENTS/Security/Banner/REVOKED", "x\n"), 2, ARMES_DONNEES),
        ("antislashs NT", ecrire(".agents\\security\\banner\\revoked", "x\n"), 2, ARMES_DONNEES),
        ("point final NT", ecrire(".agents/security/banner/revoked.", "x\n"), 2, ARMES_DONNEES),
        ("hook en casse", ecrire(".claude/hooks/SESSION-BANNER.SH", "x\n"), 2, ARMES_HOOK),
        ("absolu", ecrire(str(pr.depot / ".agents/security/banner/revoked"), "x\n"), 2, ARMES_DONNEES),
        ("copie hors dépôt", ecrire(str(pr.maison / "copie/.agents/security/banner/revoked"), "x\n"), 2, ARMES_DONNEES),
        ("voisin banner-notes", ecrire(".agents/security/banner-notes.md", "x\n"), 0, ""),
        ("voisin banners/", ecrire(".agents/security/banners/x", "x\n"), 0, ""),
        ("voisin session-start.sh", ecrire(".claude/hooks/session-start.sh", "x\n"), 0, ""),
        # Revue de sécurité S-01M5Y0WXYETFX3KY8A58A4FAKZ : le lanceur des jambes enveloppées réécrit en `exit 0`.
        ("lanceur garde-fermee.sh : Write exit 0", ecrire(str(pr.depot / ".agents/security/garde-fermee.sh"),
                                                          "#!/bin/bash\nexit 0\n"), 2, ARMES_LANCEUR),
        ("lanceur garde-fermee.sh : Edit", editer("a", "b", ".agents/security/garde-fermee.sh"), 2, ARMES_LANCEUR),
        ("voisin garde-fermee.sh.md", ecrire(".agents/security/garde-fermee.sh.md", "x\n"), 0, ""),
        ("Write sans l'enregistrement", ecrire_doc(_sans_banniere), 2, "banniere-enregistrement"),
        ("Edit : true # …session-banner.sh", editer(queue_json, "true # " + queue_json), 2, "banniere-enregistrement"),
        ("Write : commande = true # …session-banner.sh", ecrire_doc(_commande_neutralisee), 2, "banniere-enregistrement"),
        ("Edit : matcher compact", editer('"matcher": "startup|resume|clear"', '"matcher": "compact"'), 2,
         "banniere-enregistrement"),
        ("Write : timeout posé", ecrire_doc(_muter_jambe("timeout", 1)), 2, "banniere-enregistrement"),
        ("Write : shell retiré", ecrire_doc(_muter_jambe("shell", None)), 2, "banniere-enregistrement"),
        ("Edit : une ligne deny retirée", editer(deny_json, ""), 2, "banniere-enregistrement"),
        ("Write : disableAllHooks au projet", ecrire_doc(_poser("disableAllHooks", True)), 2, "banniere-disable-all-hooks"),
        ("Write : disableAllHooks sous ~/.claude-op", ecrire(hors, '{"disableAllHooks": true}\n'), 2,
         "banniere-disable-all-hooks"),
        ("Write : disableAllHooks sous ~/.claude-op local", ecrire(hors_local, '{"disableAllHooks": true}\n'), 2,
         "banniere-disable-all-hooks"),
        ("Write anodin sous ~/.claude-op", ecrire(hors, '{"model": "x"}\n'), 0, ""),
        ("Write : disableAllHooks false explicite", ecrire_doc(_poser("disableAllHooks", False)), 0, ""),
        ("Edit sans rapport", editer('"OTEL_METRIC_EXPORT_INTERVAL": "5000"', '"OTEL_METRIC_EXPORT_INTERVAL": "6000"'), 0, ""),
        ("charge MultiEdit", {"tool_name": "MultiEdit", "tool_input": {"file_path": reg, "edits": [
            {"old_string": queue_json, "new_string": "true"}]}}, 2, "banniere-outil-inconnu"),
        ("charge sans tool_name", {"tool_input": {"file_path": reg, "content": "{}"}}, 2, "banniere-outil-inconnu"),
        ("Edit introuvable", editer("ce texte n'existe pas", "x"), 2, "banniere-edit-non-simulable"),
        ("Write : JSON illisible", ecrire(reg, "{ pas du json\n"), 2, "banniere-reglages-illisibles"),
        ("borne : préfixe réécrit sur TOUTES les jambes", ecrire_doc(_prefixe_coherent), 0, ""),
        ("jambe de garde factice + bannière alignée", ecrire_doc(_garde_factice), 2, "banniere-enregistrement"),
        ("coût : migration du préfixe jambe par jambe", ecrire_doc(_migration_une_jambe), 2, "banniere-enregistrement"),
        ("Write : async true sur la jambe", ecrire_doc(_muter_jambe("async", True)), 2, "banniere-enregistrement"),
        ("Write : matcher 'startup |resume|clear'", ecrire_doc(_matcher_banniere("startup |resume|clear")), 2,
         "banniere-enregistrement"),
        ("Write : matcher 'startup,resume'", ecrire_doc(_matcher_banniere("startup,resume")), 2, "banniere-enregistrement"),
        ("Write : jambe protect-paths retirée", ecrire_doc(_sans_protect), 2, "banniere-enregistrement"),
        ("Write : matcher protect-paths neutralisé (Bash)", ecrire_doc(_matcher_protect("Bash")), 2,
         "banniere-enregistrement"),
        ("Write : async sur la jambe protect-paths", ecrire_doc(_async_protect), 2, "banniere-enregistrement"),
        ("Write : matcher protect-paths élargi Edit|Write|NotebookEdit", ecrire_doc(_matcher_protect("Edit|Write|NotebookEdit")),
         0, ""),
        # Exec-critic it. 2.
        ("Edit : env.PATH ajouté", editer(otel, otel + ',\n    "PATH": "/tmp/faux-t1228:/usr/bin:/bin"'), 2,
         "banniere-env-hors-liste"),
        ("Edit : env.BASH_ENV ajouté", editer(otel, otel + ',\n    "BASH_ENV": "/tmp/faux-t1228.sh"'), 2,
         "banniere-env-hors-liste"),
        ("Write neuf sous ~/.claude-op : env.PATH", ecrire(hors, '{"env": {"PATH": "/inexistant"}}\n'), 2,
         "banniere-env-hors-liste"),
        # It. 3 (S-00004646) : liste BLANCHE — SHELLOPTS=noexec n'exécutait AUCUN hook.
        ("Edit : env.SHELLOPTS ajouté", editer(otel, otel + ',\n    "SHELLOPTS": "noexec"'), 2, "banniere-env-hors-liste"),
        ("Edit : env.BASHOPTS ajouté", editer(otel, otel + ',\n    "BASHOPTS": "extdebug"'), 2, "banniere-env-hors-liste"),
        ("Edit : env.IFS ajouté", editer(otel, otel + ',\n    "IFS": "/"'), 2, "banniere-env-hors-liste"),
        ("Edit : env.Path (casse mixte)", editer(otel, otel + ',\n    "Path": "/tmp/faux-t1228"'), 2, "banniere-env-hors-liste"),
        ("Edit : env.FOO_T1228 ajouté", editer(otel, otel + ',\n    "FOO_T1228": "1"'), 2, "banniere-env-hors-liste"),
        # Revue de sécurité S-00004661 : noms EXACTS, aucun préfixe ; point de collecte en boucle locale.
        ("Edit : env.OTEL_FOO_T1228 ajouté (préfixe seul)", editer(otel, otel + ',\n    "OTEL_FOO_T1228": "1"'), 2,
         "banniere-env-hors-liste"),
        ("Edit : env.OTEL_EXPORTER_OTLP_HEADERS ajouté", editer(otel, otel + ',\n    "OTEL_EXPORTER_OTLP_HEADERS": "a=b"'), 2,
         "banniere-env-hors-liste"),
        ("Edit : env.otel_logs_exporter (minuscules, nom permis)", editer(otel, otel + ',\n    "otel_logs_exporter": "otlp"'),
         0, ""),
        ("Edit : point de collecte vers un tiers", editer(point, '"OTEL_EXPORTER_OTLP_ENDPOINT": "https://collecte.example.com:4318"'),
         2, "banniere-otel-hors-boucle"),
        ("Edit : point de collecte 127.0.0.1@tiers", editer(point, '"OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1@collecte.example.com"'),
         2, "banniere-otel-hors-boucle"),
        ("Edit : point de collecte vers localhost", editer(point, '"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"'), 0, ""),
        # Clôture du lot 95d6220a..c964c9a6, F2 : forme stricte par re.fullmatch — urlsplit lisait
        # l'hôte 127.0.0.1 derrière l'antislash (échappé ici en JSON) ; et hors projet, sur ajout.
        ("Edit : point de collecte tiers\\@127.0.0.1",
         editer(point, r'"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collecte.example.com\\@127.0.0.1"'), 2, "banniere-otel-hors-boucle"),
        # Revue de sécurité S-00004713 : re.I seul replie ſ (U+017F) sur s ; re.I | re.A, la casse ASCII reste admise.
        ("Edit : point de collecte localhoſt (U+017F)",
         editer(point, '"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localho\u017ft:4318"'), 2, "banniere-otel-hors-boucle"),
        ("Edit : point de collecte httpſ:// (U+017F)",
         editer(point, '"OTEL_EXPORTER_OTLP_ENDPOINT": "http\u017f://127.0.0.1:4318"'), 2, "banniere-otel-hors-boucle"),
        ("Edit : point de collecte HTTP://LOCALHOST (casse ASCII)",
         editer(point, '"OTEL_EXPORTER_OTLP_ENDPOINT": "HTTP://LOCALHOST:4318"'), 0, ""),
        ("Write neuf sous ~/.claude-op : point de collecte vers un tiers",
         ecrire(hors, '{"env": {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://collecte.example.com:4318"}}\n'), 2,
         "banniere-otel-hors-boucle"),
        # Revue de sécurité S-00004661 : JSON que l'hôte (JSON.parse) rejette.
        ("Edit : NaN ajouté", editer(permissions, '"zz": NaN,\n  ' + permissions), 2, "banniere-reglages-illisibles"),
        ("Edit : Infinity ajouté", editer(permissions, '"zz": Infinity,\n  ' + permissions), 2, "banniere-reglages-illisibles"),
        ("Edit : -Infinity ajouté", editer(permissions, '"zz": -Infinity,\n  ' + permissions), 2, "banniere-reglages-illisibles"),
        # Revue de sécurité S-00004661 : replace_all doit être un booléen JSON.
        ("Edit : replace_all \"true\" (chaîne)", {**editer(deny_json, ""), "tool_input": {**editer(deny_json, "")["tool_input"],
                                                                                         "replace_all": "true"}}, 2,
         "banniere-edit-non-simulable"),
        ("Edit : replace_all 1", {**editer(otel, otel), "tool_input": {**editer(otel, otel)["tool_input"], "replace_all": 1}}, 2,
         "banniere-edit-non-simulable"),
        ("Edit : replace_all \"yes\"", {**editer(otel, otel), "tool_input": {**editer(otel, otel)["tool_input"], "replace_all": "yes"}},
         2, "banniere-edit-non-simulable"),
        ("Edit : replace_all true (booléen) sans rapport", {**editer(otel, otel), "tool_input": {**editer(otel, otel)["tool_input"],
                                                                                                 "replace_all": True}}, 0, ""),
        ("Edit : replace_all false (booléen) sans rapport", {**editer(otel, otel), "tool_input": {**editer(otel, otel)["tool_input"],
                                                                                                  "replace_all": False}}, 0, ""),
        # Décision pilote S-00004662 : le matcher couvre startup ET resume ET clear.
        ("Write : matcher réduit à startup", ecrire_doc(_matcher_banniere("startup")), 2, "banniere-enregistrement"),
        ("Write : matcher startup|resume", ecrire_doc(_matcher_banniere("startup|resume")), 2, "banniere-enregistrement"),
        ("Write : matcher élargi startup|resume|clear|compact", ecrire_doc(_matcher_banniere("startup|resume|clear|compact")),
         0, ""),
        ("Write : matcher bannière (?i)STARTUP|resume", ecrire_doc(_matcher_banniere("(?i)STARTUP|resume")), 2,
         "banniere-enregistrement"),
        ("Write : matcher protect-paths (?i)edit|write", ecrire_doc(_matcher_protect("(?i)edit|write")), 2,
         "banniere-enregistrement"),
        ("Write : matcher protect-paths = Edit seul", ecrire_doc(_matcher_protect("Edit")), 2, "banniere-enregistrement"),
        ("Write : jambe safe-bash retirée", ecrire_doc(_sans_safe), 2, "banniere-enregistrement"),
        ("Write : matcher safe-bash neutralisé (Edit)", ecrire_doc(_matcher_safe("Edit")), 2, "banniere-enregistrement"),
        ("légitime : Edit ajout d'une permission allow", editer('"Bash(docker rm*)"', '"Bash(docker rm*)",\n      "Bash(echo t1228:*)"'),
         0, ""),
        ("légitime : Write réindentation seule (indent=4)", ecrire(reg, json.dumps(json.loads(reel), indent=4) + "\n"), 0, ""),
    ]
    assert isinstance(doc, dict)
    ecarts: list[str] = []

    def juger(serie: list) -> None:
        for etiquette, charge, rc, aiguille in serie:
            p = pr.edit(charge)
            err = p.stderr.decode("utf-8", "replace")
            if p.returncode != rc or (aiguille and aiguille not in err):
                ecarts.append(f"{etiquette} : rc {p.returncode} (attendu {rc}) — {err.strip()[:160]!r}")

    juger(lignes)
    # Clés env hors liste PRÉEXISTANTES (posées à la main, S-00004646) : au projet,
    # toujours refusées ; dans des réglages utilisateur, tolérées tant qu'elles
    # ne sont ni ajoutées ni modifiées par l'écriture.
    utilisateur = pr.maison / ".claude-preexistant" / "settings.json"
    utilisateur.parent.mkdir(parents=True)
    utilisateur.write_text('{"env": {"FOO_MAIN": "1"}, "model": "x"}\n', encoding="utf-8")
    otel_tiers = pr.maison / ".claude-otel" / "settings.json"
    otel_tiers.parent.mkdir(parents=True)
    otel_tiers.write_text('{"env": {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://collecte.example.com:4318"}, "model": "x"}\n',
                          encoding="utf-8")
    # Revue de sécurité S-00004713 : la même valeur, sous une clé minuscule INERTE ; la renommer
    # l'active — hors_boucle compare des couples (clé exacte, valeur), plus la valeur seule.
    otel_min = pr.maison / ".claude-otel-min" / "settings.json"
    otel_min.parent.mkdir(parents=True)
    otel_min.write_text('{"env": {"otel_exporter_otlp_endpoint": "https://collecte.example.com:4318"}, "model": "x"}\n',
                        encoding="utf-8")
    sale = json.loads(reel)
    sale["env"]["FOO_MAIN"] = "1"
    pr.reglages.write_text(json.dumps(sale, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        juger([
            ("projet : clé hors liste préexistante + Edit sans rapport",
             editer(otel, '"OTEL_METRIC_EXPORT_INTERVAL": "6000"'), 2, "banniere-env-hors-liste"),
            ("utilisateur : clé hors liste préexistante + Edit sans rapport",
             editer('"model": "x"', '"model": "y"', str(utilisateur)), 0, ""),
            ("utilisateur : clé hors liste ajoutée",
             editer('"FOO_MAIN": "1"', '"FOO_MAIN": "1", "BAR_T1228": "1"', str(utilisateur)), 2, "banniere-env-hors-liste"),
            ("utilisateur : valeur d'une clé hors liste changée",
             editer('"FOO_MAIN": "1"', '"FOO_MAIN": "2"', str(utilisateur)), 2, "banniere-env-hors-liste"),
            ("utilisateur : point de collecte hors boucle préexistant + Edit sans rapport",
             editer('"model": "x"', '"model": "y"', str(otel_tiers)), 0, ""),
            ("utilisateur : point de collecte hors boucle sous clé minuscule préexistant + Edit sans rapport",
             editer('"model": "x"', '"model": "y"', str(otel_min)), 0, ""),
            ("utilisateur : clé minuscule renommée OTEL_EXPORTER_OTLP_ENDPOINT, valeur hors boucle inchangée",
             editer('"otel_exporter_otlp_endpoint"', '"OTEL_EXPORTER_OTLP_ENDPOINT"', str(otel_min)), 2,
             "banniere-otel-hors-boucle"),
        ])
    finally:
        pr.reglages.write_text(reel, encoding="utf-8")
    # T-01M4JRFS0T (S-01M5DJH0BQWAWZ8FS7A947ZXDT) : une jambe de garde est garantie NUE ou ENVELOPPÉE.
    # L'état de départ est CONSTRUIT, nu puis enveloppé, quelle que soit la forme de la copie suivie (C5).
    def ecrire_depuis(depart: dict, muter: Callable[[dict], dict]) -> dict:
        return ecrire(reg, json.dumps(muter(json.loads(json.dumps(depart))), indent=2, ensure_ascii=False) + "\n")

    nu = _formes_gardes(False)(json.loads(reel))
    enveloppe = _formes_gardes(True)(json.loads(reel))
    lanceur = '"$CLAUDE_PROJECT_DIR/.agents/security/garde-fermee.sh"'
    refus = "banniere-enregistrement"
    series = (
        (nu, [
            ("nu : Write des deux jambes enveloppées (N=7, timeout 10)", ecrire_depuis(nu, _formes_gardes(True)), 0, ""),
            ("nu : timeout sur la jambe protect-paths nue", ecrire_depuis(nu, _muter_protect("timeout", 10)), 2, refus),
            # Témoin de M43 : depuis l'enveloppé, la règle monotone refuse déjà la perte du timeout.
            ("nu : Write de la jambe protect-paths enveloppée sans timeout", ecrire_depuis(
                nu, lambda d: _muter_protect("timeout", None)(_formes_gardes(True)(d))), 2, refus),
        ]),
        (enveloppe, [
            ("enveloppé : Write identique", ecrire_depuis(enveloppe, lambda d: d), 0, ""),
            # Clôture T-01M4JRFS0T : la règle est MONOTONE, une garde enveloppée le reste.
            ("enveloppé : retour à la forme nue", ecrire_depuis(enveloppe, _formes_gardes(False)), 2, refus),
            ("enveloppé : préfixe + env -u", ecrire_depuis(enveloppe, _prefixe_ouvert("env -u ")), 2, refus),
            ("enveloppé : timeout 600 (borne haute)", ecrire_depuis(enveloppe, _muter_protect("timeout", 600)), 0, ""),
            ("enveloppé : bannière retirée", ecrire_depuis(enveloppe, _sans_banniere), 2, refus),
            ("enveloppé : jambe protect-paths retirée", ecrire_depuis(enveloppe, _sans_protect), 2, refus),
            ("enveloppé : jambe safe-bash retirée", ecrire_depuis(enveloppe, _sans_safe), 2, refus),
            ("enveloppé : timeout 8 pour N=7", ecrire_depuis(enveloppe, _muter_protect("timeout", 8)), 2, refus),
            ("enveloppé : timeout 601", ecrire_depuis(enveloppe, _muter_protect("timeout", 601)), 2, refus),
            ("enveloppé : timeout true", ecrire_depuis(enveloppe, _muter_protect("timeout", True)), 2, refus),
            ("enveloppé : timeout 10.5", ecrire_depuis(enveloppe, _muter_protect("timeout", 10.5)), 2, refus),
            ("enveloppé : sans timeout", ecrire_depuis(enveloppe, _muter_protect("timeout", None)), 2, refus),
            ("enveloppé : lanceur à un autre chemin", ecrire_depuis(enveloppe, _commande_protect(
                lanceur, '"$CLAUDE_PROJECT_DIR/.agents/security/autre-lanceur.sh"')), 2, refus),
            ("enveloppé : AGENTS_HOOK_HOST=claude retiré", ecrire_depuis(enveloppe, _commande_protect(
                "AGENTS_HOOK_HOST=claude exec", "exec")), 2, refus),
            # Revue S-01M5Y1S1MF7625AN624DCSN8P0 : une ligne par clause de garde_exacte, chacune avec son mutant.
            ("enveloppé : jambe Edit|Write pointée sur safe-bash.sh", ecrire_depuis(enveloppe, _commande_protect(
                SUFFIXE_PROTECT, SUFFIXE_SAFE)), 2, refus),
            ("enveloppé : type prompt", ecrire_depuis(enveloppe, _muter_protect("type", "prompt")), 2, refus),
            ("enveloppé : shell powershell", ecrire_depuis(enveloppe, _muter_protect("shell", "powershell")), 2, refus),
        ]),
    )
    try:
        for depart, serie in series:
            pr.reglages.write_text(json.dumps(depart, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            juger(serie)
    finally:
        pr.reglages.write_text(reel, encoding="utf-8")
    assert ecarts == [], "C14 : " + " | ".join(ecarts)


def cas_derivation_safe_bash(pr: Projet) -> None:
    """La sonde du plan (Tests), rejouée sur le safe-bash.sh DU banc : il DÉRIVE
    les bras ; une extraction cassée refuserait TOUTE redirection
    (`redirect-stage-broken`), d'où les témoins rc 0."""
    sondes = [
        ("echo x > /tmp/probe-banner", 0),
        ("ls 2>&1", 0),
        ("echo x > .agents/security/banner-notes.md", 0),
        ("echo x > .agents/security/banner/revoked", 2),
        ("echo x > .claude/hooks/session-banner.sh", 2),
        ("echo x > .agents/security/garde-fermee.sh", 2),
        ("echo x > " + str(pr.maison / "copie/.agents/security/banner/revoked"), 2),
    ]
    ecarts = []
    for commande, rc in sondes:
        p = pr.bash_cmd(commande)
        if p.returncode != rc:
            ecarts.append(f"{commande} : rc {p.returncode} (attendu {rc}) — {p.stderr.decode('utf-8', 'replace').strip()[:120]!r}")
    assert ecarts == [], "dérivation safe-bash : " + " | ".join(ecarts)


def test_c13_deny():
    deny = json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["deny"]
    assert [d for d in DENY_BANNIERE if d not in deny] == [], "C13 : une ligne deny de la bannière manque"


@pytest.mark.parametrize("bash", BASHES or ["<aucun bash>"])
def test_c14_protect_paths(bash, tmp_path):
    _exiger_outils()
    cas_c14(projet_gardes(tmp_path, bash))


@pytest.mark.parametrize("bash", BASHES[:1] or ["<aucun bash>"])
def test_c14_env_preexistant_adoptant(bash, tmp_path, monkeypatch):
    """C14 chez un adoptant dont le settings.json PROJET porte déjà un `env` : la copie le voit
    REMPLACÉ par ENV_SYNTHETIQUE (ni assertion, ni fusion), et C14 reste vert. L'env préexistant
    porte une clé d'ENV_SYNTHETIQUE à une autre valeur et une clé hors liste : une fusion
    laisserait l'une ou l'autre et rougirait ici."""
    _exiger_outils()
    doc = json.loads(SETTINGS.read_text(encoding="utf-8"))
    env_adoptant = {"OTEL_METRIC_EXPORT_INTERVAL": "9999", "ADOPTANT_CLE_T0": "1"}
    source = tmp_path / "settings-adoptant.json"
    source.write_text(json.dumps({"env": env_adoptant, **{k: v for k, v in doc.items() if k != "env"}},
                                 indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "SETTINGS", source)
    pr = projet_gardes(tmp_path / "adoptant", bash)
    copie = json.loads(pr.reglages.read_text(encoding="utf-8"))
    assert copie["env"] == ENV_SYNTHETIQUE, "C14 adoptant : l'env préexistant n'a pas été remplacé"
    assert {k: v for k, v in copie.items() if k != "env"} == {k: v for k, v in doc.items() if k != "env"}, \
        "C14 adoptant : la copie a perdu ou changé autre chose que l'env"
    cas_c14(pr)


@pytest.mark.parametrize("bash", BASHES or ["<aucun bash>"])
def test_derivation_safe_bash(bash, tmp_path):
    _exiger_outils()
    cas_derivation_safe_bash(projet_gardes(tmp_path, bash))


MUTANTS_GARDE: dict[str, tuple[Callable[[str], str], list[Callable[[Projet], None]]]] = {
    "M9 bras juger retirés": (_remplacer(("    *.agents/security/banner/*)\n", "    *.agents/security/banner/m9-retire)\n"),
                                         ("    *.claude/hooks/session-banner.sh)\n", "    *.claude/hooks/m9-retire.sh)\n")),
                              [cas_c14, cas_derivation_safe_bash]),
    "M10 règle de contenu retirée": (_remplacer(("then\n  garder_enregistrement_banniere\nfi\n", "then\n  :\nfi\n")),
                                     [cas_c14]),
    "M12 enregistrement jugé par sous-chaîne": (_remplacer(('h.get("command") == attendu',
                                                            '"session-banner.sh" in str(h.get("command"))')),
                                                [cas_c14]),
    "M14 préfixe non unique accepté": (_remplacer(
        ("    if len(vus) == 1 and all(", "    if vus and all(")), [cas_c14]),
    "M16 garantie de la jambe protect-paths retirée": (_remplacer(
        ('    (ANCRES[0], ("Edit", "Write"), "jambe protect-paths.sh sur Edit et Write"),\n', "")), [cas_c14]),
    "M20 matcher regex accepté pour une jambe garantie": (_remplacer(
        ('        return valeur in m.split("|")\n    return False\n',
         '        return valeur in m.split("|")\n    return re.search(m, valeur) is not None\n')), [cas_c14]),
    "M21 matcher protect-paths : Edit seul suffit": (_remplacer(
        ('(ANCRES[0], ("Edit", "Write"), ', '(ANCRES[0], ("Edit",), ')), [cas_c14]),
    "M22 garantie de la jambe safe-bash retirée": (_remplacer(
        ('    (ANCRES[1], ("Bash",), "jambe safe-bash.sh sur Bash"),\n', "")), [cas_c14]),
    "M23 liste blanche rendue à la liste noire d'origine": (_remplacer(
        ("    return k in ENV_PERMISES\n",
         '    return k not in ("PATH", "BASH_ENV", "ENV", "CDPATH", "GLOBIGNORE")\n')), [cas_c14]),
    "M27 parse_constant retiré (NaN accepté)": (_remplacer(
        ("apres = json.loads(texte, parse_constant=_constante)", "apres = json.loads(texte)")), [cas_c14]),
    "M28 replace_all non booléen accepté": (_remplacer(
        ('        if "replace_all" in ti and not isinstance(ti["replace_all"], bool):\n', "        if False:\n")), [cas_c14]),
    "M29 matcher bannière : startup seul suffit": (_remplacer(
        ("all(couvre(b.get(\"matcher\"), v) for v in SOURCES)", "couvre(b.get(\"matcher\"), \"startup\")")), [cas_c14]),
    "M30 préfixe OTEL_ rétabli": (_remplacer(
        ("    return k in ENV_PERMISES\n", '    return k in ENV_PERMISES or k.startswith("OTEL_")\n')), [cas_c14]),
    "M31 point de collecte hors boucle accepté": (_remplacer(
        ("        if est_projet(formes) and hors_boucle(apres):\n", "        if False:\n")), [cas_c14]),
    "M33 point de collecte hors boucle accepté hors projet": (_remplacer(
        ("        if not est_projet(formes) and ajoutes:\n", "        if False:\n")), [cas_c14]),
    "M34 BOUCLE_URL sans re.A (ſ replié sur s)": (_remplacer(
        ('[A-Za-z0-9._~/-]*)?", re.I | re.A)', '[A-Za-z0-9._~/-]*)?", re.I)')), [cas_c14]),
    "M35 point de collecte comparé par valeur seule (renommage de clé admis)": (_remplacer(
        ("ajoutes = [c for c in hors_boucle(apres) if c not in hors_boucle(avant)]",
         "ajoutes = [c for c in hors_boucle(apres) if c[1] not in [d[1] for d in hors_boucle(avant)]]")), [cas_c14]),
    "M24 comparaison avant/après retirée": (_remplacer(
        ("hors_liste(apres) if est_projet(formes) else hors_liste(apres) - hors_liste(avant)", "hors_liste(apres)")),
        [cas_c14]),
    "M25 casse des clés env": (_remplacer(("    k = str(k).upper()\n", "    k = str(k)\n")), [cas_c14]),
    "M26 réglages du projet jugés en delta": (_remplacer(
        ("hors_liste(apres) if est_projet(formes) else hors_liste(apres) - hors_liste(avant)",
         "hors_liste(apres) - hors_liste(avant)")), [cas_c14]),
    "M17 clés en liste noire (pas de timeout)": (_remplacer(("set(h) == CLES and ", '"timeout" not in h and ')), [cas_c14]),
    "M18 liste exacte à espaces et virgules": (_remplacer(
        ('LISTE_EXACTE = re.compile(r"[A-Za-z0-9_|]*")', 'LISTE_EXACTE = re.compile(r"[A-Za-z0-9_ ,|-]*")'),
        ('return valeur in m.split("|")', 'return valeur in [t.strip() for t in re.split(r"[|,]", m)]')), [cas_c14]),
    # T-01M4JRFS0T : la forme enveloppée des jambes de garde.
    "M36 borne N+2 <= timeout retirée": (_remplacer(
        ("int(m.group(2)) + 2 <= t <= DELAI_MAX", "t <= DELAI_MAX")), [cas_c14]),
    "M37 lanceur quelconque admis": (_remplacer(
        ("[$]CLAUDE_PROJECT_DIR/[.]agents/security/garde-fermee[.]sh", ".*")), [cas_c14]),
    "M38 forme enveloppée ignorée par prefixes": (_remplacer(
        ("        m = ENVELOPPE.fullmatch(c) if isinstance(c, str) else None\n        if m is not None:\n"
         "            vus.add(m.group(1))\n", "")), [cas_c14]),
    # M39 n'admet le timeout QUE sur la jambe nue : la forme enveloppée reste jugée telle quelle,
    # seule la ligne « nu : timeout sur la jambe protect-paths nue » rougit.
    "M39 timeout admis sur la jambe nue": (_remplacer(
        ("    if set(h) == CLES:\n        return jambe_exacte(h, p + queue)\n",
         '    if set(h) == CLES | {"timeout"} and h.get("command") == p + queue:\n        return True\n'
         "    if set(h) == CLES:\n        return jambe_exacte(h, p + queue)\n")), [cas_c14]),
    "M40 timeout non entier admis": (_remplacer(
        ("    if not isinstance(t, int):\n", "    if False:\n")), [cas_c14]),
    "M41 borne haute 600 retirée": (_remplacer(("<= t <= DELAI_MAX", "<= t")), [cas_c14]),
    "M42 AGENTS_HOOK_HOST=claude facultatif": (_remplacer(
        ("(.*)AGENTS_HOOK_HOST=claude exec", "(.*?)(?:AGENTS_HOOK_HOST=claude )?exec")), [cas_c14]),
    "M43 enveloppée sans timeout admise (délai par défaut)": (_remplacer(
        ("    if set(h) == CLES:\n        return jambe_exacte(h, p + queue)\n",
         '    if set(h) == CLES and ENVELOPPE.fullmatch(str(h.get("command"))) is None:\n'
         "        return jambe_exacte(h, p + queue)\n    if set(h) == CLES:\n        h = dict(h, timeout=600)\n")),
        [cas_c14]),
    # Revue de sécurité S-01M5Y0WXYETFX3KY8A58A4FAKZ : le bras du lanceur garde-fermee.sh.
    "M44 bras du lanceur garde-fermee.sh retiré": (_remplacer(
        ("    *.agents/security/garde-fermee.sh)\n", "    *.agents/security/m44-retire.sh)\n")),
        [cas_c14, cas_derivation_safe_bash]),
    # Revue S-01M5Y1S1MF7625AN624DCSN8P0 : une clause de garde_exacte par mutant, chacun tué par sa ligne.
    "M45 garde visée non comparée à la garde garantie": (_remplacer(
        (r' and QUEUE + m.group(3) + "\"" == queue', "")), [cas_c14]),
    "M46 type de la jambe enveloppée non jugé": (_remplacer(
        ('    return h.get("type") == "command" and h.get("shell") == "bash" and QUEUE',
         '    return h.get("shell") == "bash" and QUEUE')), [cas_c14]),
    "M47 shell de la jambe enveloppée non jugé": (_remplacer(
        ('    return h.get("type") == "command" and h.get("shell") == "bash" and QUEUE',
         '    return h.get("type") == "command" and QUEUE')), [cas_c14]),
    # Clôture T-01M4JRFS0T : préfixe clos et règle monotone.
    "M48 préfixe ouvert admis (env -u)": (_remplacer(
        (" and all(PREFIXE_CLOS.fullmatch(x) for x in vus)", "")), [cas_c14]),
    "M49 retour à la forme nue admis (règle non monotone)": (_remplacer(
        ("                        if set(h) != CLES:\n"
         "                            g.add(nom + \" (enveloppée sous garde-fermee.sh)\")\n", "")), [cas_c14]),
}


@pytest.mark.parametrize("nom", sorted(MUTANTS_GARDE))
def test_mutant_garde_tue(nom, tmp_path):
    _exiger_outils()
    muter, designes = MUTANTS_GARDE[nom]
    texte = muter(PROTECT.read_text(encoding="utf-8"))
    rouges = []
    for i, cas in enumerate(designes):
        try:
            cas(projet_gardes(tmp_path / str(i), BASHES[0], texte))
        except AssertionError:
            rouges.append(cas.__name__)
    assert rouges, f"{nom} SURVIT : aucun de {[c.__name__ for c in designes]} ne rougit"
