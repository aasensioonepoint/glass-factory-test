#!/usr/bin/env bash
# Statusline — current model | active task from the board | context % | session cost.
# The board parse is folded into the SAME python call that parses the input JSON:
# this runs every `refreshInterval` seconds (5s), so a second process would be
# pure waste. tasks.py is imported by path; a missing/broken board degrades to
# "no active task" rather than breaking the line.
INPUT=$(cat)
# CAPTEUR DU RÉGIME ATTERRISSAGE (T-00000534) — cette ligne est la SEULE raison
# pour laquelle la statusline écrit quelque chose, et elle mérite sa justification.
#
# POURQUOI ICI, ET NULLE PART AILLEURS. Le remplissage du contexte n'existe dans
# AUCUNE charge de hook : l'union des champs consommés par les 25 hooks de ce
# dépôt ne porte ni `context_window` ni rien d'équivalent. La charge statusLine
# est la seule qui l'expose (`context_window.used_percentage`), et elle repasse
# toutes les 5 s. `PreCompact` arriverait trop tard — la compaction y est déjà
# décidée.
#
# CE QUE ÇA COÛTE, DIT PLUTÔT QUE DÉCOUVERT : la statusline devient
# side-effecting, ce qu'elle n'était pas. Elle n'écrit que dans
# `.agents/state/local/` (seau jetable, git-ignoré), au plus DEUX fichiers par
# session — `.armed` puis le relevé `.palier2` de T-00000588 — chacun sous son
# `O_EXCL`, et dans son propre `try/except` — elle ne peut jamais coûter
# la ligne d'état. Aucun `eval`, aucun process de plus : le bloc est fusionné
# dans l'appel python qui parse déjà la charge (correctif T-00000490).
# DÉFAUT PORTÉ DE 80 À 90 le 2026-09-13, décision pilote. LE SEUIL RESTE UN
# NOMBRE DU PILOTE : rien dans ce dépôt n'établit 90 plutôt que 85 ou 95.
#
# CE QUI EST MESURÉ, ET CE QUI NE L'EST PAS — la première rédaction de ce
# commentaire affirmait « il a gelé une session qui a ensuite bouclé trois
# cycles » : le transcript de la nuit du 12→13/09 l'INFIRME. Armement à ~795k
# tokens (fenêtre 1M) ; DEUX clôtures avant, UNE seule après ; et le seul refus
# jamais émis par le filet fut un FAUX POSITIF (T-00000579). Le régime n'a gelé
# aucun travail légitime. Ce qui EST mesuré : compaction observée à 958–966k,
# donc marge à 90 ≈ 65k, contre une passe rétro relevée à 14–21k — elle tient.
#
# BORNE : ces chiffres valent pour une fenêtre de 1M. Sur 200k, la marge
# tomberait à ~13k, SOUS le coût de la passe rétro — non mesuré, et c'est la
# décision à reprendre le jour où ce kit tourne sur une fenêtre plus courte.
# Reste surchargeable par l'environnement.
CONTEXT_RETRO_PCT="${CONTEXT_RETRO_PCT:-90}"
# printf %f follows LC_NUMERIC: under a fr_FR locale "1.2" is an invalid number
# and the output would read "$1,00". Costs are dot-decimal.
export LC_NUMERIC=C
PY=""; for c in python3 python py; do if "$c" --version >/dev/null 2>&1; then PY="$c"; break; fi; done
# T-00001191 : aucun .pyc (tasks.py chargé par chemin, toutes les 5 s). L'env seul, sans -B : le banc
# test_context_retro_contract.py repère l'appel python plus bas par sa sous-chaîne exacte, que -B casserait.
export PYTHONDONTWRITEBYTECODE=1
# SECURITY (T-00000490) — AUCUN `eval` ici, et c'est le point.
# La forme d'origine faisait `eval "$(python … )"` sur des valeurs interpolees
# CRUES entre apostrophes manuelles. Mesure du 2026-09-06 : un JSON dont
# `display_name` vaut  X'; touch /tmp/PWNED; #  creait bien le fichier — rc=0,
# ligne d'etat d'apparence normale, execution SILENCIEUSE. Le premier correctif
# (shlex.quote sur les trois valeurs) fermait l'injection mais LAISSAIT le
# `eval`, et le hook SAST le refusait toujours : il a raison, une chaine rendue
# etanche reste une chaine qu'on execute. Ici python emet les quatre champs
# separes par NUL et le shell les LIT — il n'y a plus rien a interpreter, donc
# plus rien a echapper. NUL est le seul octet qu'un champ ne peut pas contenir ;
# une lecture par LIGNES se ferait decaler par un titre de tache multiligne.
# `read -r -d ''` est mesure identique sous bash 3.2.57 et 5.3.15.
{ IFS= read -r -d '' MODEL; IFS= read -r -d '' COST; IFS= read -r -d '' PCT
  IFS= read -r -d '' TASK; } < <(
printf '%s' "$INPUT" | PROJ="$CLAUDE_PROJECT_DIR" SEUIL="$CONTEXT_RETRO_PCT" "$PY" -c "
import sys,json,os,pathlib,importlib.util
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
d=json.load(sys.stdin)
root=os.environ.get('PROJ') or '.'
task='no active task'
try:
    spec=importlib.util.spec_from_file_location('tasks', pathlib.Path(root)/'.agents'/'bin'/'tasks.py')
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    task=mod.statusline(root)
except Exception:
    pass
# CAPTEUR — arme le regime atterrissage au premier passage au-dessus du seuil.
# O_EXCL fait l'idempotence GRATUITEMENT : la statusline repasse toutes les 5 s
# et le FileExistsError la fait n'armer qu'une fois. Tout est sous try/except :
# une ecriture impossible ne doit jamais couter la ligne d'etat.
# AUCUN ACCENT GRAVE DANS CE BLOC, et ce n'est pas une preference : on est DANS
# la chaine double-quotee passee a python, donc le shell y fait une substitution
# de commande avant que python ne voie un octet. Mesure du 2026-09-13, ma propre
# faute : trois lignes de commentaire ont fait naitre << .libere : commande
# introuvable >>, et le 2>/dev/null de l'appel l'aurait rendue MUETTE en usage
# reel. Les commentaires voisins n'en portent aucun — c'est la raison.
#
# Le SECOND PALIER, plus bas, se sert de key et mk. Ils sont calcules dans le
# bloc ci-dessous, qui peut lever AVANT de les poser — et une valeur qui fuit
# d'un try est une dependance tacite. Elles sont donc nommees ici, et le second
# palier refuse de tourner sans elles plutot que de compter sur un NameError.
pct=0.0; seuil=90.0; key=None; mk=None; deja_arme=False
try:
    pct=float((d.get('context_window') or {}).get('used_percentage') or 0)
    sid=d.get('session_id') or d.get('transcript_path') or ''
    _s=(os.environ.get('SEUIL') or '').strip()
    seuil=float(_s) if _s.replace('.','',1).isdigit() else 90.0
    if pct >= seuil and sid:
        import hashlib
        pre='s-' if d.get('session_id') else 't-'
        key=pre+hashlib.sha256(str(sid).encode()).hexdigest()[:16]
        mk=pathlib.Path(root)/'.agents'/'state'/'local'/'context-retro'
        mk.mkdir(parents=True, exist_ok=True)
        # << DEJA LA >> NE SUFFIT PAS, ET C'ETAIT MA PREMIERE REDACTION. La ligne
        # d'etat repasse toutes les 5 s, donc la sentinelle existe des la passe
        # suivante sans qu'aucun pourcentage n'ait monte : mesure du binome, deux
        # passes a 95 % posaient le marqueur sur une session qui n'avait rien
        # poursuivi — et une session reprise (--resume, ou l'apres-compaction)
        # DEMARRE haute. Le temoin de poursuite est donc le pct d'ARMEMENT, qui
        # doit etre SOUS le palier : on mesure la MONTEE, jamais la duree.
        # Lire la charge ferme au passage deux trous : un .armed vide ou efface a
        # la main ne vaut plus temoignage.
        try:
            _a=json.loads((mk/(key+'.armed')).read_text(encoding='utf-8'))
            deja_arme=float(_a.get('pct') or 0) < seuil + 5
        except Exception:
            deja_arme=False
        fd=os.open(mk/(key+'.armed'), os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o644)
        # 'instrument' DATE l'armement du cote de l'instrument, et c'est ce qui
        # rend le denominateur comptable : les armements anterieurs a T-00000588
        # n'ont jamais pu poser de palier2, les compter rejouerait la tautologie.
        os.write(fd, json.dumps({'pct':pct,'capteur':'statusline','statut':'MESURE',
                                 'instrument':'T-00000588'}).encode())
        os.close(fd)
except Exception:
    pass
# SECOND PALIER — c'est un INSTRUMENT, pas un regime. Il n'arme rien, ne refuse
# rien, et le hook ne le lit pas : il pose UN fichier le jour ou la question de
# T-00000588 se pose reellement, pour qu'elle cesse d'etre une opinion.
#
# LA QUESTION. Le regime d'atterrissage ne se rearme jamais : .armed est pose
# sous O_EXCL, donc une fois par session, et .libere est irreversible. Une
# session qui franchit le seuil, capitalise, repart et monte jusqu'a 97 % ne
# verra plus AUCUNE seconde passe reclamee — precisement la ou la compaction est
# imminente.
#
# POURQUOI CE FICHIER PLUTOT QU'UN CORRECTIF. Le ticket exigeait une mesure
# AVANT de coder, et ma premiere mesure etait une TAUTOLOGIE : j'avais compte
# les .libere — zero — donc conclu << ferme sans geste >>. L'instrument ne
# pouvait pas observer la question : .libere n'existe que depuis le 13/09
# 11:32 et le seuil est passe de 80 a 90 le meme jour a 09:52, or les sessions
# armees sur disque precedent les deux. Zero PAR CONSTRUCTION, population VIDE
# et non nulle. Le binome a alors trouve le contre-exemple dans mon propre
# echantillon : s-81c1a8fe4d1e88d3 porte .armed a 05:16 et ecrit encore a
# 12:24 — SEPT HEURES apres son armement.
#
# CE QUE J'ELARGIS PAR RAPPORT A LA PISTE DU BINOME, et pourquoi. Il proposait
# de conditionner le marqueur a l'existence de .libere. Mesure a l'instant :
# ZERO .libere sur disque, y compris pour la session qui ecrit cette ligne —
# l'instrument serait donc reste muet sur une population vide, la faute exacte
# qu'il corrige. La condition posee ici est donc le franchissement du SECOND
# PALIER par une session qui etait ARMEE PLUS BAS, et l'etat de liberation part
# dans la CHARGE.
#
# ET .libere NE MESURE PAS LA CAPITALISATION — trouvaille du binome, et elle
# corrige le SENS du releve. Ce marqueur n'est ecrit qu'au SITE DE REFUS : il
# faut qu'un demarrage de tache hors agenda ait ete TENTE pour que le sas soit
# seulement consulte. Une session qui capitalise puis continue SUR son agenda
# n'en a donc jamais — c'est le cas nominal, et c'est celui de la session qui
# ecrit cette ligne (retro-done pose, ligne de base ecrite, zero .libere). Lire
# libere=false comme << gelee sans capitaliser >> aurait range le cas nominal du
# cote qui FERME le ticket. La charge porte donc aussi retro_done et la ligne de
# base, qui sont les faits de la capitalisation elle-meme — et ce sont des
# LECTURES DE FICHIER : la ligne d'etat n'ouvre aucun process, l'instrument ne
# doit rien couter au pilote.
#
# LECTURE DU VERDICT, pour que personne n'ait a la deviner, et le binome a
# montre que ma premiere version la rendait FAUSSE. Le denominateur ne compte
# QUE les *.armed portant le champ 'instrument' : QUATRE sessions sont armees
# sur disque au 13/09 et TROIS precedent cette ligne — elles n'ont jamais pu
# poser de palier2, et les compter serait exactement la tautologie que ce ticket
# a deja payee une fois. ROUVRE LE TICKET : un palier2 portant libere=true, OU
# portant retro_done=true avec un compte de taches ou de lecons SUPERIEUR a sa
# ligne de base — c'est-a-dire une session qui avait bel et bien capitalise puis
# a continue. Pour la moitie libere=true seule,
# le denominateur est le nombre de *.libere — il vaut ZERO au 13/09, donc aucun
# nombre de palier2 sans liberation ne ferme cette moitie tant qu'une liberation
# n'a pas ete observee. Rythme mesure : 4 armements en 5 jours.
#
# CE QUI PEUT INVALIDER LE RELEVE SANS TRACE : rien ne purge ce repertoire, mais
# il est git-ignore, donc un effacement manuel de .agents/state/local remet
# numerateur ET denominateur a zero en silence. Un zero se lit avec cette borne.
#
# LE PALIER EST SEUIL + 5, ET CE +5 N'EST PAS FONDE — je l'ecris plutot que de
# le laisser paraitre mesure. Il manque le nombre de points qui separent
# l'armement de la compaction observee, et la seule note existante (compaction a
# 958-966k, marge a 90 % environ 65k) ne vaut que pour une fenetre de 1M : sur
# 200k, cinq points ne designent pas le meme moment. L'instrument mesure donc la
# meme GRADUATION partout, pas la meme DISTANCE a la compaction.
try:
    if key and mk and deja_arme and pct >= seuil + 5:
        # LA CHARGE EST CONSTRUITE AVANT L'OUVERTURE, et le fd ferme sous
        # finally : O_EXCL ne repare jamais un fichier de 0 octet, donc une
        # exception entre les deux laissait un marqueur que le glob compte et que
        # json.loads refuse — un releve illisible pour toujours.
        try:
            _b=json.loads((mk/(key+'.baseline')).read_text(encoding='utf-8'))
        except Exception:
            _b=None
        # STATUT « MESURE », ET IL LE RESTE — relevé du 2026-09-14, qui a
        # CORRIGÉ une première lecture trop rapide. Ce marqueur reste un
        # INSTRUMENT : il relève le franchissement et n agit sur rien.
        #
        # POURQUOI IL N EST PAS PASSÉ À « ARME », alors que le relevé semblait
        # le justifier. Un premier palier2 a bien été posé (pct 95 pour un seuil
        # de 90, retro_done vrai, 28 leçons contre 24 de ligne de base), et j en
        # ai conclu que le cas visé par T-00000588 existait. LE BINÔME A MONTRÉ
        # QUE C ÉTAIT LE MAUVAIS ÉVÉNEMENT : la garde ne peut mordre que sur une
        # session qui a DÉJÀ été libérée, or ce relevé porte libere=false et il
        # n existe AUCUN marqueur de libération sur disque. Population du
        # déclencheur : ZÉRO, pas un. J avais mesuré le précurseur et codé sur
        # le déclencheur.
        #
        # CE QUE ÇA DEMANDE AVANT DE RECODER : un palier2 portant libere=true.
        # Il en faut un seul. Tant qu il n en existe pas, agir ici reviendrait à
        # refuser du travail sur une population vide — et le banc
        # test_the_instrument_reads_no_hook_and_arms_nothing tient cette borne
        # par une liste FERMÉE de consommateurs, qui refuse tout hook lisant ce
        # marqueur.
        _p=json.dumps({'pct':pct,'seuil':seuil,'capteur':'statusline',
                       'statut':'MESURE','ticket':'T-00000588',
                       'libere':(mk/(key+'.libere')).exists(),
                       'retro_done':(mk/(key+'.retro-done')).exists(),
                       'baseline':_b,
                       # LA FENETRE, parce que +5 POINTS ne designent pas le meme
                       # moment a 200k et a 1M : sans elle un zero ne se lit pas.
                       'context_window':d.get('context_window')}).encode()
        fd=os.open(mk/(key+'.palier2'), os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o644)
        try:
            os.write(fd, _p)
        finally:
            os.close(fd)
except Exception:
    pass
fields=[str(d.get('model',{}).get('display_name','?')),
        str(d.get('cost',{}).get('total_cost_usd',0)),
        str((d.get('context_window') or {}).get('used_percentage') or 0),
        task]
sys.stdout.write('\0'.join(f.replace('\0','') for f in fields) + '\0')
" 2>/dev/null )
printf '%s | %s | %.0f%% ctx | $%.2f' "${MODEL:-?}" "${TASK:-no active task}" "${PCT:-0}" "${COST:-0}"
