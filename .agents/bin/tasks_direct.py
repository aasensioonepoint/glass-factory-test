# tasks_direct.py — PARTIE de `tasks.py` (T-00001178) : LA VOIE DIRECTE — le
# verbe `direct`, son prédicat UNIQUE `refus_direct`, et les deux jambes qui le
# REJOUENT là où l'estampille franchit une garde ARMÉE : `start` sous la chaîne
# de plan (`PLAN_CHAIN_REQUIRED`), `done` sous la cible de plan
# (`PLAN_CIBLE_REQUIRED`, sans plan résolu). Exécutée dans l'espace de noms de
# `tasks` par `_charger_parties()`, jamais importée seule : ses noms libres
# viennent de la façade et des parties amont (`tasks_requetes.py`,
# `tasks_mesure.py`, `tasks_gardes.py`). Elle OUVRE SUR UN COMMENTAIRE, jamais
# sur une docstring : exécutée dans l'espace de `tasks`, une docstring de partie
# écraserait `tasks.__doc__` (test_tasks_decoupe.py, témoin (d)).
#
# DÉCISIONS (pilote) : S-00004109 (mode direct général, kit et adoptants),
# S-00004114 (la voie directe saute aussi la porte humaine ; le mécanique prime
# sur la prose), S-00004135 (5 fichiers OU MOINS ; le plan est requis à partir
# de 6), S-00004146 (arbitrages de la rév. 5 du plan).
#
# CE QUI VOYAGE NE PORTE AUCUN ID DU KIT : la marque, les clés de l'estampille,
# l'aide et les causes de refus sont lues sur le board de chaque adoptant, qui
# n'a pas les décisions du kit. Les ids ne vivent que dans ces commentaires.
#
# PORTÉE, DITE (L-00000079) : `direct` vérifie TOUJOURS ; `start` et `done` ne
# rejouent que là où l'estampille FRANCHIT une garde armée. Là où rien n'est
# armé, rien n'est franchi : l'estampille y est inerte, aucune marque n'est
# écrite. Une directe NE CONSOMME JAMAIS une trace de chaîne de plan.
#
# RÉSIDU NON MÉCANISABLE (nommé, borné) : (i) une décision ouverte ou une nature
# de sécurité que ni le titre ni le stage n'écrivent avec les lexiques fermés ;
# (ii) un verdict de sécurité tracé sur un AUTRE id que la tâche ; (iii) le diff
# réel au-delà du write-set déclaré, jusqu'au contrôle de retour mécanique ;
# (iv) une chaîne jouée pour une tâche ensuite estampillée reste NON consommée
# et couvre le prochain `start` planifié pendant `PLAN_TRACE_TTL_HEURES` ;
# (v) la liste de garde est fermée : « petit » est prouvé, « inoffensif » ne
# l'est jamais. La revue de sécurité du diff reste OBLIGATOIRE après tout dev
# direct — c'est le filet de (i), (ii) et (v), et c'est de la PROSE.

from __future__ import annotations

#: LE SEUIL, UNE SEULE DÉFINITION (S-00004135) : 5 INCLUS passe en direct, le
#: plan est requis à partir de 6. `kickoff_guard.SEUIL_CLASSE` la LIT à travers
#: `tasks` (aucune parité de valeurs à tenir) ; la prose qui répète le nombre est
#: épinglée à cette constante par le banc de doctrine.
MAX_FICHIERS_DIRECT = 5

#: C2 — LA LISTE DE GARDE, FERMÉE, PAR CLASSES. Un chemin du write-set est un
#: chemin de garde s'il est couvert À LA FRONTIÈRE DE SEGMENT par une entrée
#: (casse repliée, `canonical_writeset_path`), s'il en est un ANCÊTRE (déclarer
#: `.claude` couvrirait `.claude/hooks/`), s'il satisfait un motif ANCRÉ de
#: `MOTIFS_GARDE`, ou si son NOM DE FICHIER porte un mot de `NOMS_GARDE`.
#:
#: BORNE, DITE : la liste couvre les hooks câblés et les scripts de la porte
#: (DÉRIVÉS : `test_direct_mode_garde.py` relit les configs et la porte, W27 —
#: UN niveau : ce que la config CITE, jamais ce que le script appelle ni ce qu'il
#: charge), la voie directe, le board, le canal des graines, les juges (défs
#: d'hôte, sources `agents/`, roster JSON) et leur générateur, et l'IaC
#: du projet (`*.tf`, `*.tf.json`, `*.tfvars[.json]`, `.agents/deploy/targets.json`). Elle ne
#: couvre PAS : les défs `dev-*`, `documenter`… ; `AGENTS.md` ; `.gitignore` et
#: son gabarit ; les manifestes de dépendances (security-orchestrator les voit) ;
#: `.claude/commands/*.md` (prose du pipeline) ; les modules frères de
#: sync_template.py (sync_template_proc.py…), outil d'équipe du kit qui ne voyage
#: pas chez l'adoptant (décision pilote S-00004146) ; `checks.manifest.json`, lu
#: aujourd'hui par des bancs seulement, à rouvrir quand un script de porte le
#: lira ; ni un banc qui teste une garde sans le dire dans son nom — relevés le
#: 2026-10-05, NON exhaustif : `.agents/bin/test_tasks.py`,
#: `test_tasks_decoupe.py`, `test_tasks_sans_chaine.py`, `test_tasks_mesure.py`,
#: `.agents/evals/test_plan_cible_star.py`, `.agents/bin/test_sync_template_seed.py`.
#: Une entrée sans barre finale qui désigne un RÉPERTOIRE existant est refusée
#: par C1 (système de fichiers) : la couverture ci-dessous reste TEXTUELLE.
CHEMINS_GARDE = (
    # G1 — hooks, lanceurs, armement. De JUGEMENT, non dérivés : kickoff_arm,
    # board_bridge et night_approve (rév. 5 du plan).
    ".claude/hooks/",
    ".codex/hooks/",
    ".gemini/hooks/",
    ".github/hooks/",
    ".githooks/",
    ".claude/settings.json",
    ".codex/hooks.json",
    ".agents/hooks.json",
    ".kimi-code/hooks.json",
    ".agents/pyrun.sh",
    ".agents/pyrun.ps1",
    ".agents/bin/post-task-done-index.sh",
    ".agents/bin/dev_shard_reindex.py",
    ".agents/bin/kickoff_arm.py",
    "agentic_v3/reconciliation/board_bridge.py",
    # T-01M5BXTGX5YN8XEXTG1PP7A5ZX : l'emplacement NEUF des paquets du kit, en union
    # STATIQUE avec l'ancien (jamais par le résolveur `vendor_paths`).
    ".agents/vendor/agentic_v3/reconciliation/board_bridge.py",
    ".agents/bin/night_approve.py",
    # G2 — porte et CI, et les bancs de garde que leur nom ne dit pas (rév. 5).
    "core-scripts/verify.sh",
    ".github/workflows/",
    "pytest.ini",
    "conftest.py",
    "src/cadre/data/gabarits/pytest.ini.tmpl",
    ".agents/vendor/cadre/data/gabarits/pytest.ini.tmpl",
    ".agents/security/",
    ".agents/evals/python_file_length_cliquet.json",
    ".agents/evals/test_python_file_length.py",
    ".agents/evals/test_seed_protection.py",
    # Le banc du registre d'exceptions du scanner Unicode (T-01M5CN9FM2MPY8Z00AS7FTXXWH) :
    # son nom ne dit pas la garde. Le registre lui-même est couvert par `.agents/security/`.
    ".agents/evals/test_unicode_allowlist_protection.py",
    ".agents/bin/tasks.test.sh",
    # La porte de l'adoptant (T-00001183) : le marqueur qui choisit le mode de
    # la porte (verify.sh, ci.yml) et le script qui rend son verdict.
    ".agents/IS_THE_KIT",
    ".agents/bin/porte_adoptant.py",
    # G3 — board, journal, plan (la façade et ses parties : `MOTIFS_GARDE`) ; le
    # STORE du board aussi (F7) : `tasks.py` seul l'écrit, jamais une édition.
    ".agents/state/board/",
    ".agents/bin/specs.py",
    ".agents/bin/plan_cible.py",
    ".agents/bin/plan_depends.py",
    ".agents/bin/plan_trace.py",
    # La grammaire des lots de la fournée : elle décide quels write-sets naissent
    # au board et quels lots tentent la voie directe.
    ".agents/bin/plan_lots.py",
    # G4 — marqueurs, graines, canal des graines.
    ".agents/state/gates/",
    ".agents/adopter-seed/",
    ".template-exclude",
    ".agents/bin/sync_template.py",
    # G5 — le GÉNÉRATEUR des défs d'hôte et ses deux bancs (T-01M5C1NXE5JWY6A0C2XWEGDPCC,
    # décision pilote S-01M5CD56VRE6MBVEKWB2FR7MWN) : il réécrit les défs des juges.
    # BORNE (security-code-review S-01M5CNJ6BNSAKKNR0Y0ZC7BMFF) : G5 ne couvre PAS ce que le
    # générateur LIT ou IMPORTE et qui décide aussi de ce qu'il écrit — `core-scripts/apply-mode.py`
    # (la table hôte -> répertoire), `.agents/vendor/cadre/roster.py` (la validation FORMAT 1),
    # `.agents/vendor/cadre/config.py` (la liste HOTES), `.agents/vendor/cadre/workspace.py` (l'E/S
    # du roster ; l'ancien lieu `src/cadre/` reste en liste, avec le nouveau) ;
    # une directe qui ne touche qu'eux passe. Laissés hors liste en attente d'une décision pilote.
    "src/cadre/renderers/",
    ".agents/vendor/cadre/renderers/",
    ".agents/bin/render_hosts.py",
    ".agents/bin/test_render_hosts.py",
    ".agents/evals/test_cadre_renderers.py",
)

#: Motifs ANCRÉS des deux côtés (sauf les extensions G7, ancrées à la fin seule, voir
#: plus bas), sur la forme canonique (minuscules) : `re.search`,
#: donc l'ancre `^` refuse `vendor/.agents/bin/tasks.py` et l'ancre `$` refuse
#: `.agents/bin/tasks_x.py.orig`. G2 : scripts `run-*`/`check-*` de la porte ; G3 :
#: la façade `tasks.py` et ses parties (`tasks_direct.py` comprise) ; G5 : les
#: défs de la chaîne et des juges sur les cinq hôtes, leurs SOURCES `agents/<nom>.md`
#: et leur roster JSON `.agents/vendor/cadre/data/roster/<nom>.json` (décision pilote
#: S-01M5CD56VRE6MBVEKWB2FR7MWN ; le générateur `render_hosts.py` et
#: `.agents/vendor/cadre/renderers/` sont en liste fermée, G5 de `CHEMINS_GARDE`, l'ancien lieu
#: `src/cadre/` gardé à côté) ; G6 : les bancs de la voie
#: directe. G7 (T-01M52X1W3WPKCWX1DC36NMKJB6, décision pilote S-01M55NC83Z3ZWMWKDP5F6FFDDG) :
#: l'IaC du PROJET — l'approbation du plan reste le seul contrôle humain avant
#: qu'elle existe. Ses trois motifs d'extension ne sont ancrés qu'à la FIN, à
#: dessein : l'IaC vit n'importe où dans l'arbre ; le registre des cibles l'est des
#: deux côtés. Consommateurs (une seule liste) : `kickoff_guard.armed_by_class` arme
#: une tâche `running` qui en porte, `plan_lots.predire_route` prédit « planifiée ».
MOTIFS_GARDE = (
    r"^core-scripts/(run|check)-[^/]+\.sh$",
    r"^\.agents/bin/tasks(_[a-z0-9_]+)?\.py$",
    r"^\.(claude|gemini|kimi-code|codex|github)/agents/(orchestrator|planner|plan-critic|critic-|exec-critic|design-review|security-|sca-)[^/]*\.(md|toml)$",
    r"^agents/(orchestrator|planner|plan-critic|critic-|exec-critic|design-review|security-|sca-)[^/]*\.md$",
    r"^src/cadre/data/roster/(orchestrator|planner|plan-critic|critic-|exec-critic|design-review|security-|sca-)[^/]*\.json$",
    r"^\.agents/vendor/cadre/data/roster/(orchestrator|planner|plan-critic|critic-|exec-critic|design-review|security-|sca-)[^/]*\.json$",
    r"^\.agents/evals/test_direct_mode[a-z0-9_]*\.py$",
    r"\.tf$",
    r"\.tf\.json$",
    r"\.tfvars(\.json)?$",
    r"^\.agents/deploy/targets\.json$",
)

#: Un NOM DE FICHIER (dernier segment, casse repliée) qui contient l'un de ces
#: mots est un fichier de garde. `gate` (rév. 5) attrape aussi `aggregate`,
#: `delegate`… : le sens sûr de l'erreur (renvoi au plan), coût mesuré au board.
NOMS_GARDE = ("guard", "garde", "gate")

#: C3 — le lexique d'une DÉCISION OUVERTE, en mots bornés (`\b`), sur le titre et
#: le stage NORMALISÉS (NFKD, diacritiques retirés, `casefold`).
LEXIQUE_DECISION = ("option", "options", "decision", "decisions", "a trancher", "arbitrer", "instruire", "ne pas coder avant")

#: C4 — le lexique d'une NATURE DE SÉCURITÉ, au titre seul, sans aucune exemption.
LEXIQUE_SECURITE = ("securite", "security", "cve", "vulnerabilite", "vulnerability", "secret", "secrets")

#: Les motifs de la garde de mesure (`MOTIFS`) qu'une directe ADMET. Liste
#: FERMÉE CROISÉE : tout AUTRE motif non vide refuse PAR DÉFAUT — un motif futur
#: ne passe pas sans que personne l'ait décidé.
MOTIFS_ADMIS_DIRECT = ("sans-fournee",)

#: L'étiquette de cause d'un motif refusé ; un motif absent d'ici est « inconnu » (C1).
DIRECT_CLASSE_DES_MOTIFS = {"garde": "C2", "securite": "C4", "decision-pilote": "C3", "gros": "C1"}

#: Les coupures de SEGMENT du titre et du stage : une décision tranchée ne
#: s'exempte que si le MÊME segment la cite.
DIRECT_COUPURES = re.compile(r"[.;!?|—]")
# T-00000726 (7bis) : sur le texte NORMALISÉ (casefold), `s-<ulid>` EN PREMIER, puis l'ancien.
DIRECT_S_ID = re.compile(r"\bs-([0-9a-hjkmnp-tv-z]{26}|[0-9]{8})\b")

#: C4, le DERNIER verdict de sécurité de la tâche (S-00004172, tranché du côté
#: SÛR) : son TITRE puis son TEXTE normalisés sont lus ; un motif OUVERT l'emporte
#: TOUJOURS — un jeton fermé (clean, go, pass, findings aucun) n'admet que si
#: AUCUN motif ouvert n'est présent : il n'est donc jamais lu. Le vocabulaire est
#: celui du contrat de `security-code-review` (FINDINGS(code)/CLEAN) plus NO_GO,
#: « N nouveau(x) HIGH », « un HIGH », « HIGH: N » et « HIGH @ <sha> » ; « 0 HIGH »,
#: « aucun HIGH », « no HIGH », « pas de HIGH @ » ne sont jamais ouverts. BORNE
#: MESURÉE le 2026-10-05 sur le SPECS du kit (248 verdicts titrés sécurité, 23
#: bloquants à la lecture titre et texte) : 23 vus ; 15 refus du côté sûr hors de
#: ces 23 (14 disent aussi clean/GO : « 2 HIGH fermés », « rouge »/« bloque » de la
#: prose, « findings=N medium ») ; aucune tâche `pending` du board nouvellement
#: refusée. Rejouée après « un HIGH » et « HIGH: N » (binôme ter) : 38 lus, 0 neuf,
#: 0 `pending` refusée sur 585 ; puis après « nouvelle(s) » (binôme quater) : 38 lus,
#: 0 neuf, 0 `pending` refusée sur 585. Ça empêche d'OUBLIER, pas de TRICHER.
DIRECT_SECU_OUVERT = re.compile(
    r"\bno[_ -]?go\b|findings ?\(code\)|\bfindings ?[=:]? ?[1-9]"
    r"|\b[1-9][0-9]* (?:nouveaux? |nouvelles? |new )?(?:high|critical)\b"
    r"|\b(?:un|une|one) (?:nouveau |nouvelle |new )?(?:high|critical)\b|\b(?:high|critical) ?[:=] ?[1-9]"
    r"|(?<!no )(?<!aucun )(?<!0 )(?<!de )\b(?:high|critical) @|\brouge\b|\bbloque\b")


def direct_normaliser(texte: Any) -> str:
    """NFKD, diacritiques retirés, `casefold` — la normalisation de la garde de
    mesure (`_normaliser_titre`), appelée ici par nom ; une valeur non textuelle
    vaut le vide."""
    return _normaliser_titre(texte if isinstance(texte, str) else "")


def direct_porte_lexique(texte: str, lexique: tuple[str, ...]) -> str | None:
    """Le premier mot de `lexique` présent dans `texte` (déjà normalisé), BORNÉ
    aux mots, ou None. Un lexique VIDE ne trouve RIEN : jamais une alternative
    vide qui attraperait tout."""
    for mot in lexique:
        if re.search(r"\b" + re.escape(mot) + r"\b", texte):
            return mot
    return None


def direct_segments(texte: str) -> list[str]:
    """Les segments non vides d'un texte déjà normalisé."""
    return [s for s in DIRECT_COUPURES.split(texte) if s.strip()]


def direct_garde_couvrante(chemin: str) -> str | None:
    """POURQUOI `chemin` est un chemin de garde (la règle qui le couvre), ou None.
    TEXTUEL : aucune lecture de disque."""
    canon = canonical_writeset_path(chemin)
    if not canon:
        return None
    for entree in CHEMINS_GARDE:
        e = canonical_writeset_path(entree)
        if canon == e or canon.startswith(e + "/"):
            return f"liste fermée : {entree}"
        if e.startswith(canon + "/"):
            return f"ancêtre de {entree}"
    for motif in MOTIFS_GARDE:
        if re.search(motif, canon):
            return f"motif {motif}"
    nom = canon.rsplit("/", 1)[-1]
    for mot in NOMS_GARDE:
        if mot in nom:
            return f"nom de fichier portant « {mot} »"
    return None


def est_chemin_de_garde(chemin: str) -> bool:
    """Vrai si `chemin` est couvert par la liste de garde (`direct_garde_couvrante`).
    Lu aussi par `kickoff_guard.armed_by_class`, à travers `tasks` : une seule
    liste, jamais dupliquée."""
    return direct_garde_couvrante(chemin) is not None


def direct_lien_symbolique(racine: Path, brut: str) -> bool:
    """Vrai si `brut`, ou l'un de ses ancêtres sous `racine`, est un lien symbolique :
    le chemin déclaré ne désigne alors pas le fichier écrit (C1, trou du binôme)."""
    courant = racine
    for segment in Path(brut).parts:
        courant = courant / segment
        if courant.is_symlink():
            return True
    return False


#: Le rang d'un S-id ILLISIBLE : sous tout rang lisible, ancien `(0, n)` comme ULID
#: `(1, corps)` — la valeur de `plan_cible._clef_sid` (T-00001040), jamais un `int`.
DIRECT_RANG_ILLISIBLE = (-1, 0)


def direct_rang_specs(entree: dict[str, Any]) -> tuple[int, int | str]:
    """Le rang d'une entrée SPECS par son S-id : la clé d'ORDRE `sort_key` (`S-00000042`
    → `(0, 42)`, `S-<ULID>` → `(1, <ULID>)`, tout ULID après tout ancien), pour un S-id
    BIEN FORMÉ seulement ; `DIRECT_RANG_ILLISIBLE` sinon (T-00000726, 7bis)."""
    sid = str(entree.get("id") or "")
    if not re.fullmatch(r"S-(?:" + ULID_BODY + r"|[0-9]{1,15})", sid):
        return DIRECT_RANG_ILLISIBLE
    return sort_key(sid)


def direct_causes_securite(task: dict[str, Any], entrees: list[dict[str, Any]]) -> list[str]:
    """C4 hors motif : le TITRE (lexique fermé, aucune exemption) et le DERNIER
    verdict de sécurité de la tâche (`kind=verdict`, plus grand S-id, titre
    portant `securite`/`security`) quand son TITRE ou son TEXTE porte un motif
    `DIRECT_SECU_OUVERT`, qui l'emporte sur tout jeton fermé. `entrees` : les
    entrées SPECS de la tâche seule."""
    causes: list[str] = []
    mot = direct_porte_lexique(direct_normaliser(task.get("task")), LEXIQUE_SECURITE)
    if mot is not None:
        causes.append(f"C4 nature de sécurité au titre (« {mot} ») : aucune exemption, "
                      "le chemin planifié et la revue de sécurité d'abord")
    verdicts = [e for e in entrees if e.get("kind") == "verdict"
                and direct_porte_lexique(direct_normaliser(e.get("title")), ("securite", "security"))]
    if verdicts:
        dernier = max(verdicts, key=direct_rang_specs)
        for champ, nom in (("title", "titre"), ("text", "texte")):
            ouvert = DIRECT_SECU_OUVERT.search(direct_normaliser(dernier.get(champ)))
            if ouvert:
                causes.append(f"C4 le dernier verdict de sécurité de la tâche est bloquant ({nom} : "
                              f"« {ouvert.group(0)} ») : corrige puis fais rejouer la revue de sécurité, "
                              "ou, verdict clos, fais retracer par `security-code-review` un verdict au vocabulaire fermé (CLEAN, 0 HIGH) ; "
                              "sinon le chemin planifié")
                break
    return causes


def refus_direct(root: str, task: dict[str, Any], instantane: bool = False) -> list[str]:
    """LE SEUL PRÉDICAT DE LA VOIE DIRECTE : TOUTES les causes de refus, jamais la
    première seule ; une liste VIDE vaut admission. Rejoué par `estampiller`
    (`instantane=False`) et par les jambes `start` et `done` (`instantane=True`)
    là où l'estampille franchit une garde armée.

    C1 taille : write-set DÉCLARÉ, 1 à `MAX_FICHIERS_DIRECT` chemins EXACTS (ni
    `*`, ni barre finale, ni répertoire existant, `writeset_path_refusal` None) ;
    motif `gros` ou inconnu. C2 garde : `direct_garde_couvrante`, ou motif
    `garde`. C3 décision ouverte : motif `decision-pilote` (sans exemption) ; un
    SEGMENT du titre ou du stage portant `LEXIQUE_DECISION`, sauf si ce MÊME
    segment cite un `S-<8 chiffres>` ou un `S-<ULID>` qui est une décision (`kind=decision`) DE
    CETTE tâche, toute graphie de son id (`entrees_de`). C4 sécurité : motif
    `securite`, puis `direct_causes_securite`. C5 instantané (`instantane=True`) :
    write-set courant ⊆ celui de l'estampille. C6 : tâche non close.

    SPECS est lu TOUJOURS, par `plan_cible_module()` : ABSENT vaut `[]` (store
    frais) ; PRÉSENT ET ILLISIBLE, ou `plan_cible.py` inchargeable, est un refus
    même sans lexique. Ça empêche d'OUBLIER, pas de TRICHER : titre, stage et
    motif sont écrits par qui ouvre la tâche."""
    causes: list[str] = []
    racine = Path(normalize_root(root))
    writeset = writeset_of(task)
    motif = task.get("motif")
    if task.get("state") == "done":
        causes.append(f"C6 tâche close : ré-estampiller ne la rouvre pas — `tasks.py reopen {task.get('id')} "
                      "--raison \"<pourquoi>\"`, puis `start`")
    if not writeset:
        causes.append("C1 aucun write-set déclaré : `tasks.py writeset <id> <chemins>` d'abord, "
                      "la voie directe ne s'infère jamais")
    elif len(writeset) > MAX_FICHIERS_DIRECT:
        causes.append(f"C1 {len(writeset)} chemins déclarés, au-delà de {MAX_FICHIERS_DIRECT} : "
                      f"le plan est requis à partir de {MAX_FICHIERS_DIRECT + 1}")
    for entree in writeset:
        brut = fold_writeset_path(entree)
        if "*" in brut or brut.endswith("/"):
            causes.append(f"C1 {entree} n'est pas un chemin exact (glob ou répertoire)")
        elif writeset_path_refusal(entree) is not None:
            causes.append(f"C1 {entree} est un chemin inadmissible au write-set")
        elif direct_lien_symbolique(racine, brut):
            causes.append(f"C1 {entree} est un lien symbolique (ou passe par un) : chemin non établi")
        elif (racine / brut).is_dir():
            causes.append(f"C1 {entree} désigne un répertoire existant : pas un chemin exact")
    if motif not in (None, "") and motif not in MOTIFS_ADMIS_DIRECT:
        classe = DIRECT_CLASSE_DES_MOTIFS.get(motif)
        if classe is None:
            causes.append(f"C1 motif inconnu de la voie directe : {motif!r} (admis : "
                          f"{', '.join(MOTIFS_ADMIS_DIRECT)}) — refus par défaut")
        else:
            causes.append(f"{classe} motif « {motif} » : il renvoie au chemin planifié")
    for entree in writeset:
        couvrante = direct_garde_couvrante(entree)
        if couvrante is not None:
            causes.append(f"C2 {entree} est un chemin de garde ({couvrante})")
    if instantane:
        tampon = task.get("direct")
        if not isinstance(tampon, dict) or not isinstance(tampon.get("writeset"), list):
            causes.append("C5 estampille absente ou illisible : `tasks.py direct <id>` la pose")
        else:
            vu = {canonical_writeset_path(p) for p in tampon["writeset"] if isinstance(p, str)}
            hors = [p for p in writeset if canonical_writeset_path(p) not in vu]
            if hors:
                causes.append(f"C5 write-set sorti de l'instantané de l'estampille : {', '.join(hors)}")
    entrees: list[dict[str, Any]] | None = None
    try:
        _pc = plan_cible_module()
    except Exception:  # un frère CASSÉ ne se lit pas comme un frère absent : refus
        _pc = None
    if _pc is None:
        causes.append("C3-C4 SPECS illisible : sécurité et décision non établies "
                      "(plan_cible.py inchargeable)")
    else:
        try:
            entrees = _pc.entrees_specs(racine)
        except (_pc.CibleError, OSError, ValueError) as exc:
            causes.append(f"C3-C4 SPECS illisible : sécurité et décision non établies ({exc})")
    taches_entrees: list[dict[str, Any]] = []
    decisions: set[str] = set()
    if entrees is not None:
        index = _pc.index_par_tache(entrees)
        taches_entrees = _pc.entrees_de(index, task.get("id"))
        decisions = _pc.decisions_existantes(taches_entrees)
    for champ, texte in (("titre", task.get("task")), ("stage", task.get("stage"))):
        for segment in direct_segments(direct_normaliser(texte)):
            mot = direct_porte_lexique(segment, LEXIQUE_DECISION)
            if mot is None:
                continue
            cites = {f"S-{n.upper()}" for n in DIRECT_S_ID.findall(segment)}
            if cites & decisions:
                continue
            causes.append(f"C3 décision ouverte au {champ} (« {mot} ») : « {segment.strip()} » — "
                          "tranche-la SUR la tâche (`kind=decision`, citée dans le même segment) "
                          "ou passe par le plan")
    causes += direct_causes_securite(task, taches_entrees)
    return causes


def marque_directe(courant: int, valides: int) -> str:
    """La marque VISIBLE au board, posée là où une garde armée a été franchie. Elle
    dit les DEUX comptes (S-00004175 (2)) : le write-set COURANT et l'instantané
    VALIDÉ par `direct` — ils divergent quand le write-set bouge après le `start`."""
    return f"[DIRECT SANS PLAN : {courant} fichier(s), {valides} validé(s) par direct]"


def direct_marque_de(task: dict[str, Any]) -> str:
    """La marque de `task`, ses deux comptes lus sur le board (instantané illisible : 0).
    UN LOT DE FOURNÉE (`fournee.parent`) n'est pas « sans plan » : il est un lot d'un
    plan approuvé que la voie directe a admis — sa marque nomme le lot et le plan
    (12 premiers signes de son empreinte), mêmes deux comptes."""
    tampon = task.get("direct")
    vus = tampon.get("writeset") if isinstance(tampon, dict) else None
    lien = task.get("fournee")
    if isinstance(lien, dict) and lien.get("parent") and lien.get("lot"):
        valides = len(vus) if isinstance(vus, list) else 0
        return (f"[DIRECT — lot {lien['lot']} du plan {str(lien.get('sha256') or '?')[:12]} : "
                f"{len(writeset_of(task))} fichier(s), {valides} validé(s) par direct]")
    return marque_directe(len(writeset_of(task)), len(vus) if isinstance(vus, list) else 0)


def direct_franchie(task: dict[str, Any]) -> bool:
    """Le `start` de `task` a-t-il franchi la chaîne (`direct.chaine_franchie`) ? Illisible : non."""
    tampon = task.get("direct")
    return isinstance(tampon, dict) and bool(tampon.get("chaine_franchie"))


def direct_message_refus(tid: str, causes: list[str], geste: str, franchie: bool = False) -> str:
    """Le refus qui liste TOUTES les causes et nomme les sorties EXÉCUTABLES :
    sur une franchie (`franchie=True`), `--retirer` est refusé tant qu'elle n'est
    pas close (binôme quater, F1), donc le remède ne le propose pas seul."""
    lignes = "".join(f"  - {c}\n" for c in causes)
    if geste == "estampiller":
        suite = ("La voie directe est réservée aux petites tâches que ce code VÉRIFIE ; "
                 "sinon, le chemin planifié : plan, critique de plan, porte humaine. "
                 "Rien n'a été écrit.")
    elif any(c.startswith("C6 ") for c in causes):
        # Une tâche CLOSE ne se rouvre ni en ré-estampillant (C6 le refuse) ni par
        # `--retirer` : le seul remède est `reopen`, puis `start` (binôme ter, T5).
        suite = (f"Remède : la tâche est close — `tasks.py reopen {tid} --raison \"<pourquoi>\"`, puis "
                 "`start`, qui rejoue les autres causes. "
                 "Jamais une bascule silencieuse vers la consommation de la chaîne de plan.")
    elif franchie:
        # Proposer `--retirer` ici serait un remède INEXÉCUTABLE (binôme quater, fable 2).
        suite = (f"Remède : `tasks.py direct {tid}` ré-estampille (revalide et remplace) ; son `start` a "
                 "franchi la chaîne, donc `--retirer` est refusé tant qu'elle n'est pas close — "
                 f"`tasks.py done {tid}`, puis `reopen` et `--retirer`, la rend au chemin planifié. "
                 "Jamais une bascule silencieuse vers la consommation de la chaîne de plan.")
    else:
        suite = (f"Remède : `tasks.py direct {tid}` ré-estampille (revalide et remplace), "
                 f"ou `tasks.py direct {tid} --retirer` rend la tâche au chemin planifié. "
                 "Jamais une bascule silencieuse vers la consommation de la chaîne de plan.")
    prep = "d'" if geste[:1] in "aeéiou" else "de "
    return (f"TASKS: refus {prep}{geste} {tid} en voie directe — {len(causes)} cause(s) :\n"
            f"{lignes}{suite}")


def estampiller(root: str, tid: str, retirer: bool = False) -> str:
    """Le verbe `direct` : VÉRIFIE (`refus_direct`) puis ESTAMPILLE la tâche,
    `task["direct"] = {"writeset": [...], "le": <date>}` ; ré-estampiller
    revalide et REMPLACE. `retirer=True` retire l'estampille : la seule sortie de
    la voie directe vers le chemin planifié. Un refus lève `BoardError` (rc ≠ 0)
    AVANT toute écriture. Patron de `set_writeset` : `board_lock`, `find` exact,
    `save`. N'appelle jamais `start`.

    UNE CHAÎNE FRANCHIE NE S'EFFACE PAS (binôme ter, T4 ; binôme quater, F1) : sur
    une tâche non close (`running`, mais aussi `blocked` ou rétrogradée en
    `pending` par le `start` d'une autre) dont le `start` a franchi la chaîne
    (`direct.chaine_franchie`), ré-estampiller GARDE la date, et `retirer` est
    REFUSÉ — retirée, la tâche se clorait sans marque alors que son `start` n'a
    payé aucune chaîne. Remède : `done`, ou `reopen` puis `--retirer`."""
    today = date.today().isoformat()
    with board_lock(root):
        data = load(root)
        task = find(data, tid)
        before = copy.deepcopy(task)
        tampon = task.get("direct")
        franchie = (tampon.get("chaine_franchie") if task.get("state") != "done"
                    and isinstance(tampon, dict) else None)
        if retirer:
            if "direct" not in task:
                return f"TASKS: {task['id']} ne porte aucune estampille directe — rien n'est écrit"
            if franchie:
                raise BoardError(
                    f"TASKS: refus de retirer l'estampille de {task['id']} — son `start` a franchi la chaîne "
                    f"de plan sans la payer (le {franchie}) : retirée, la tâche se clorait sans marque. "
                    f"Remède : `tasks.py done {task['id']} --raison \"<pourquoi>\"`, ou `tasks.py reopen` "
                    "après la clôture, puis `--retirer`. Rien n'a été écrit.")
            task.pop("direct")
            sortie = (f"TASKS: {task['id']} estampille directe retirée — chemin planifié "
                      "(la chaîne de plan redevient exigée là où elle est armée)")
        else:
            causes = refus_direct(root, task)
            if causes:
                raise BoardError(direct_message_refus(task["id"], causes, "estampiller"))
            task["direct"] = {"writeset": writeset_of(task), "le": today}
            if franchie:  # la chaîne franchie par le `start` en cours reste dite
                task["direct"]["chaine_franchie"] = franchie
            sortie = f"TASKS: {task['id']} estampillée directe {direct_marque_de(task)}"
        task["updated"] = today
        enqueue_sync_intent(data, task["id"], before, task)
        save(root, data)
    return sortie


def direct_jambe_start(root: str, tid: str, task: dict[str, Any], today: str) -> str:
    """La jambe `start` sous chaîne ARMÉE, appelée par `set_state` AVANT l'emprunt
    de groupe et la consommation : C1-C6 rejoués avec l'instantané ; admis →
    `chaine_franchie` posée, la marque rendue, AUCUNE trace consommée ; refusé →
    `BoardError` qui liste les causes — jamais une bascule vers la chaîne."""
    causes_directes = refus_direct(root, task, instantane=True)
    if causes_directes:
        raise BoardError(direct_message_refus(tid, causes_directes, "démarrer", direct_franchie(task)))
    task["direct"]["chaine_franchie"] = today
    return direct_marque_de(task)


def direct_jambe_done(root: str, tid: str, task: dict[str, Any], data: dict[str, Any],
                      _pc: Any) -> tuple[str | None, str, str]:
    """La jambe `done` du bloc cible : `(refus, note d'emprunt, marque)`. Sous cible
    ARMÉE pour la tâche, sans plan résolu (R3) et avec une estampille, C1-C6 sont
    rejoués sur le titre et le stage STOCKÉS : admis → `evaluer_done` n'est pas
    appelé, la marque est rendue ; refusé → le refus R3 PLUS les causes. Un plan
    résolu (R1/R2) est TOUJOURS contrôlé par `evaluer_done`."""
    if ("direct" in task and _pc._arme_pour_tache(root, tid, data, avertir=False) is not None
            and _pc.resoudre_plan(root, tid, data, slot=True) is None):
        causes_au_done = refus_direct(root, task, instantane=True)
        if not causes_au_done:
            return None, "", direct_marque_de(task)
        try:
            refus_r3, _note = _pc.evaluer_done(root, tid, data)
        except (_pc.CibleError, OSError, ValueError) as exc:  # une panne ne MASQUE pas les causes directes
            refus_r3 = str(exc)
        return ((refus_r3 or "") + "\n" + direct_message_refus(tid, causes_au_done, "clore", direct_franchie(task)),
                "", "")
    refus, note = _pc.evaluer_done(root, tid, data)
    return refus, note, ""


def direct_marque_franchie(task: dict[str, Any]) -> str:
    """Au `done`, la marque d'une chaîne FRANCHIE au `start` (`chaine_franchie`) :
    elle SURVIT à la clôture, que la cible soit désarmée ou hors chantier."""
    tampon = task.get("direct")
    if isinstance(tampon, dict) and tampon.get("chaine_franchie"):
        return direct_marque_de(task)
    return ""
