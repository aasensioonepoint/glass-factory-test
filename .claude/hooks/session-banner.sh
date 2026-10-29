#!/usr/bin/env bash
# SessionStart — la bannière de marque (T-00001228 ; décisions pilote
# S-00004529, S-00004530, S-00004606, S-00004618).
#
# L'AFFICHAGE EST LE CHEMIN PAR DÉFAUT. Le hook imprime sur stdout UNE ligne
# JSON `{"systemMessage":…}` : c'est le SEUL canal que Claude Code montre à
# l'écran au SessionStart (mesuré, plan T-00001228 annexe A2 — stdout nu et
# `additionalContext` vont au modèle, jamais à l'écran, L-00000136). Le texte
# n'existe qu'ENCODÉ dans `.agents/security/banner/message.oct`, un octet par
# séquence `\0NNN`, décodé par le builtin `printf '%b'` (S-00004606).
#
# IL NE SE TAIT QUE SI TOUT TIENT, et rien d'autre ne le fait taire :
#   - le jeton `$HOME/.config/cadre/banner/off` (+ `off.sig`) existe et porte
#     EXACTEMENT 4 lignes : `kind=banner-off`, `scope=global`, `id=…`,
#     `expires=AAAAMMJJ`, chacune finie par un saut de ligne ;
#   - la date UTC du jour est STRICTEMENT avant `expires` ;
#   - la ligne `id=<id>` est absente de `revoked` (ligne entière) ;
#   - `allowed_signers` porte UNE seule ligne non commentée, de la forme
#     `banner@cadre namespaces="cadre-banner" ssh-ed25519 <blob>`, dont
#     l'empreinte vaut l'épingle `EMPREINTE` ci-dessous ;
#   - `ssh-keygen -Y verify` rend 0 sur les octets du jeton lus UNE fois.
#
# ÉCHOUER FERMÉ, PAR STRUCTURE (plan-critic it. 1, C3) : la bannière est
# imprimée par le `trap … EXIT`, et `SILENT=1` n'est posé qu'APRÈS toutes les
# vérifications. Un avortement en cours de route — variable non liée sous
# `set -u`, forme bash ≥ 4 lue par /bin/bash 3.2, outil absent — sort par le
# trap, donc AFFICHE. Aucune forme bash ≥ 4 ici : ce fichier est parsé par
# /bin/bash 3.2 (filet bash-parse-oldest).
#
# PATH FIGÉ (C4) : `ssh-keygen`, `date` et `grep` sont pris dans /usr/bin et
# /bin, jamais devant eux — un `ssh-keygen` factice posé en tête du PATH de
# l'utilisateur n'éteint pas la bannière. Le `bash` qui lance ce fichier reste
# résolu par le PATH des réglages de l'hôte, comme pour tous les hooks du kit :
# un `env.PATH` posé dans les réglages le remplacerait (mesuré, exec-critic
# it. 2 : un bash factice est atteint), d'où son REFUS par la règle de contenu
# de protect-paths.sh (garder_enregistrement_banniere).
#
# CE QUE CE HOOK NE TIENT PAS (guardrails/SKILL.md § Bannière de marque) : un
# humain qui arrache le code, `claude --bare`, `disableAllHooks` dans des
# réglages hors `.claude*/`, les sessions où les hooks sont coupés. La
# signature empêche de DÉSACTIVER par configuration ; elle n'empêche pas
# d'ARRACHER le code.
PATH=/usr/bin:/bin
export PATH
LC_ALL=C
export LC_ALL
set -uo pipefail

# Empreinte de la clé publique du pilote, épinglée ici et nulle part ailleurs
# (la `.pub` suivie se lit par glob, son nom n'est jamais cité).
EMPREINTE='SHA256:n4w7327MLesanf4OzkMxW1UmZfZmvTDb0zuJDZRF7rk'
REPLI='{"systemMessage":"[cadre] Banniere de marque illisible (.agents/security/banner/message.oct) : restaurer le fichier depuis git, ou signaler au pilote (T-00001228)."}'
NL='
'
CR=$(printf '\r')
SILENT=0
BANNIERE=$REPLI
DOSSIER="${CLAUDE_PROJECT_DIR:-}/.agents/security/banner"

# Appelée par le trap EXIT seul, jamais directement (SC2329 est un faux
# « jamais invoquée ») :
# shellcheck disable=SC2329
afficher() {
  if [ "$SILENT" != 1 ]; then
    printf '%s' "$BANNIERE"
  fi
  exit 0
}
trap afficher EXIT

# Le message : une ligne d'octal, décodée, puis contrôlée sur le DÉCODÉ — une
# ligne JSON de clé unique `systemMessage`, sans saut de ligne brut. Toute
# autre forme garde le REPLI, lui aussi un `systemMessage` (C6 : un repli en
# texte nu serait invisible).
lire_message() {
  local fichier ligne decode
  fichier="$DOSSIER/message.oct"
  [ -f "$fichier" ] || return 1
  ligne=
  IFS= read -r -n 8193 ligne < "$fichier" || [ -n "$ligne" ] || return 1
  [ "${#ligne}" -le 8192 ] || return 1
  decode=$(printf '%b' "$ligne")
  case "$decode" in
    '{"systemMessage":"'*'"}') ;;
    *) return 1 ;;
  esac
  case "$decode" in
    *"$NL"*) return 1 ;;
  esac
  BANNIERE=$decode
  return 0
}

# La chaîne des conditions du silence. Elle rend 0 seulement si TOUT tient ;
# chaque étape rend 1 au premier écart.
jeton_valide() {
  local maison off tok sig tete reste id expires attendu aujourdhui revues rc signers lus n l cle tete_cle blob fp
  maison=${HOME:-}
  case "$maison" in
    /*) ;;
    *) return 1 ;;
  esac
  off="$maison/.config/cadre/banner/off"
  [ -f "$off" ] || return 1
  [ -f "$off.sig" ] || return 1

  # Les octets du jeton, lus UNE fois. `IFS=` est porteur (C1, mesuré) : sans
  # lui, `read` retire le saut de ligne final et la signature ne vérifie plus.
  # BORNÉS AVANT TOUTE EXPANSION DE MOTIF (exec-critic, S-00004625) : une
  # expansion de motif bash est superlinéaire — jeton non signé de 256 Kio :
  # 16 s, de 1 Mio : plus de 90 s, SIGTERM sans effet — l'hôte tuerait le hook
  # et la bannière serait perdue. Un jeton légitime fait ~66 octets.
  tok=
  IFS= read -r -n 257 -d '' tok < "$off" || true
  [ "${#tok}" -le 256 ] || return 1
  sig=
  IFS= read -r -n 4097 -d '' sig < "$off.sig" || true
  [ "${#sig}" -le 4096 ] || return 1

  # Grammaire stricte : le jeton est RECONSTRUIT à partir de ses champs, puis
  # comparé octet pour octet — une ligne en trop, en moins, réordonnée, un
  # `kind` ou un `scope` autre, un `expires` non numérique : bannière.
  tete="kind=banner-off${NL}scope=global${NL}id="
  case "$tok" in
    "$tete"*) ;;
    *) return 1 ;;
  esac
  reste=${tok#"$tete"}
  id=${reste%%"$NL"*}
  case "$id" in
    ''|*[!A-Za-z0-9._:-]*) return 1 ;;
  esac
  reste=${reste#*"$NL"}
  case "$reste" in
    expires=[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]"$NL") ;;
    *) return 1 ;;
  esac
  expires=${reste#expires=}
  expires=${expires%"$NL"}
  attendu="${tete}${id}${NL}expires=${expires}${NL}"
  [ "$tok" = "$attendu" ] || return 1

  # Expiration : le jour UTC doit être STRICTEMENT avant `expires`.
  aujourdhui=$(date -u +%Y%m%d 2>/dev/null) || return 1
  case "$aujourdhui" in
    [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]) ;;
    *) return 1 ;;
  esac
  [ "$aujourdhui" -lt "$expires" ] || return 1

  # Révocation : la ligne ENTIÈRE `id=<id>` (C2), comparée après retrait des
  # `\r` et des blancs de bord — une ligne collée depuis un éditeur Windows,
  # ou indentée, révoque quand même (revue de sécurité S-00004661). sed puis
  # grep, outils externes : aucun motif bash sur le contenu du fichier. grep
  # rend 1 = absente, la seule issue qui laisse continuer ; 0 = révoqué ;
  # tout autre statut (illisible, tube rompu) = bannière.
  [ -f "$DOSSIER/revoked" ] || return 1
  revues=$(sed -e "s/$CR//g" -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' "$DOSSIER/revoked" 2>/dev/null) || return 1
  printf '%s\n' "$revues" | grep -qxF -- "id=$id"
  rc=$?
  [ "$rc" -eq 1 ] || return 1

  # allowed_signers : UNE seule ligne non commentée — une seconde ligne de
  # même principal, à clé d'attaquant, ferait vérifier une signature
  # d'attaquant pendant que l'épingle de la première tient (mesuré, A3).
  signers="$DOSSIER/allowed_signers"
  [ -f "$signers" ] || return 1
  # Bornée elle aussi avant tout motif : 64 lignes, 512 octets par ligne.
  lus=0
  n=0
  cle=
  while IFS= read -r -n 513 l || [ -n "$l" ]; do
    lus=$((lus + 1))
    [ "$lus" -le 64 ] || return 1
    [ "${#l}" -le 512 ] || return 1
    case "$l" in
      ''|'#'*) ;;
      *)
        n=$((n + 1))
        if [ "$n" -eq 1 ]; then
          cle=$l
        fi
        ;;
    esac
  done < "$signers"
  [ "$n" -eq 1 ] || return 1

  # L'épingle : l'empreinte de CETTE ligne vaut celle de la clé du pilote.
  tete_cle='banner@cadre namespaces="cadre-banner" ssh-ed25519 '
  case "$cle" in
    "$tete_cle"*) ;;
    *) return 1 ;;
  esac
  blob=${cle#"$tete_cle"}
  case "$blob" in
    ''|*[!A-Za-z0-9+/=]*) return 1 ;;
  esac
  fp=$(printf 'ssh-ed25519 %s\n' "$blob" | ssh-keygen -lf - 2>/dev/null) || return 1
  fp=${fp#* }
  fp=${fp%% *}
  [ "$fp" = "$EMPREINTE" ] || return 1

  # La signature, sur les octets lus plus haut — jamais une relecture du
  # fichier. ssh-keygen écrit « Good signature » sur stdout : jeté, sinon il
  # polluerait la ligne JSON.
  printf '%s' "$tok" | ssh-keygen -Y verify -f "$signers" -I banner@cadre -n cadre-banner -s "$off.sig" >/dev/null 2>&1 || return 1
  return 0
}

lire_message || BANNIERE=$REPLI
if jeton_valide; then
  SILENT=1
fi
exit 0
