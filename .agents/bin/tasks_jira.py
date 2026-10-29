# tasks_jira.py — PARTIE de tasks.py : Jira Cloud REST v3, chargé à l'appel.
# Aucun import de tracabilite_jira à la définition : des arbres de test et des
# adoptants copient seulement tasks*.py et chargent pourtant tous les verbes.
from __future__ import annotations


_JIRA_KEY = re.compile(r"[A-Z][A-Z0-9_]{1,9}-[1-9][0-9]*\Z")
_JIRA_PROJECT = re.compile(r"[A-Z][A-Z0-9_]{1,9}\Z")
_JIRA_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_JIRA_FIELDS = "summary,created,updated,parent,issuetype"
_JIRA_LABEL = re.compile(r"pris-par-[a-z0-9-]{1,60}\Z")


def _jira_transport() -> Any:
    import tracabilite_jira
    return tracabilite_jira


def _jira_config(*, keychain: bool = True) -> tuple[str, bool, str]:
    """Resolve public site/email first, then a token; never expose the token."""
    if (os.environ.get("CADRE_JIRA_SITE") or os.environ.get("CADRE_JIRA_EMAIL")) and \
            _jira_transport().agent_appelant():
        raise BoardError("JIRA: configuration d'environnement refusée sous agent")
    config: dict[str, Any] = {}
    if not os.environ.get("CADRE_JIRA_SITE") or not os.environ.get("CADRE_JIRA_EMAIL"):
        path = Path.home() / ".config" / "cadre" / "jira.json"
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    config = loaded
            except (OSError, ValueError):
                raise BoardError("JIRA: configuration locale illisible") from None
    site = str(os.environ.get("CADRE_JIRA_SITE") or config.get("site") or "").strip()
    email = str(os.environ.get("CADRE_JIRA_EMAIL") or config.get("email") or "").strip()
    if not site or not email:
        raise BoardError("JIRA: site et e-mail absents (CADRE_JIRA_SITE, CADRE_JIRA_EMAIL)")
    transport = _jira_transport()
    try:
        base, local = transport.base_url(site)
    except transport.Refus:
        raise BoardError("JIRA: site refusé") from None
    from urllib.parse import urlsplit
    parsed = urlsplit(base)
    if parsed.path or (not local and (parsed.scheme != "https" or
                                      not (parsed.hostname or "").endswith(".atlassian.net"))):
        raise BoardError("JIRA: site Jira Cloud refusé")
    if not local:
        if parsed.port not in (None, 443):
            raise BoardError("JIRA: port refusé")
        base = f"https://{parsed.hostname}"
    if "@" not in email or ":" in email or any(c.isspace() for c in email):
        raise BoardError("JIRA: e-mail refusé")
    token = os.environ.get("JIRA_API_TOKEN", "").strip()
    if not token and keychain:
        if local:
            raise BoardError("JIRA: trousseau refusé pour site local")
        if not config.get("site") or not config.get("email") or site != str(config["site"]).strip() \
                or email != str(config["email"]).strip():
            raise BoardError("JIRA: trousseau réservé à la configuration locale")
        import subprocess
        try:
            result = subprocess.run(["/usr/bin/security", "find-generic-password", "-s", "cadre-jira",
                                     "-a", email, "-w"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                token = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not token:
        raise BoardError("JIRA: jeton absent (JIRA_API_TOKEN ou trousseau cadre-jira)")
    import base64
    auth = "Basic " + base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("ascii")
    return base, local, auth


def _jira_label_ops(body: Any) -> tuple[list[str], list[str]] | None:
    """(ajouts, retraits) d'un corps qui touche aux labels, None s'il n'y touche pas.
    Un remplacement (`fields.labels`, opération `set`) retirerait n'importe quel label : refusé."""
    if not isinstance(body, dict):
        return None
    fields, update = body.get("fields"), body.get("update")
    if isinstance(fields, dict) and "labels" in fields:
        raise BoardError("JIRA: labels remplacés refusés (ajout ou retrait seulement)")
    if not isinstance(update, dict) or "labels" not in update:
        return None
    ops = update["labels"]
    adds: list[str] = []
    removes: list[str] = []
    if not isinstance(ops, list):
        raise BoardError("JIRA: opérations de labels illisibles")
    for op in ops:
        if not isinstance(op, dict) or len(op) != 1 or not set(op) <= {"add", "remove"} or \
                not isinstance(next(iter(op.values())), str):
            raise BoardError("JIRA: opérations de labels illisibles")
        (adds if "add" in op else removes).append(next(iter(op.values())))
    return adds, removes


def jira_request(method: str, path: str, *, body: Any = None,
                 config: tuple[str, bool, str] | None = None,
                 transfert: dict[str, Any] | None = None) -> tuple[int, bytes]:
    """One bounded, no-redirect Jira request. `path` is relative to the site.
    `transfert` : l'enregistrement de la tâche dont l'intention autorise un retrait de label."""
    from http.client import HTTPException
    if not path.startswith("/rest/api/3/") or path.startswith("//"):
        raise BoardError("JIRA: chemin REST refusé")
    write = method.upper() != "GET"
    key = path.removeprefix("/rest/api/3/issue/")
    ops = _jira_label_ops(body) if write else None
    if write and _jira_transport().agent_appelant():
        if (ops is None or not _JIRA_KEY.fullmatch(key) or method.upper() != "PUT" or
                set(body) != {"update"} or set(body["update"]) != {"labels"} or len(ops[0]) != 1 or
                not _JIRA_LABEL.fullmatch(ops[0][0])):
            raise BoardError("JIRA: écriture refusée sous agent")
        if ops[1]:
            # S-01M5HN38ES : un transfert de propriété est un geste du pilote, jamais d'un agent.
            raise BoardError("JIRA: retrait de label refusé sous agent")
    if ops is not None and ops[1]:
        identity = jira_issue_for_task(transfert) if isinstance(transfert, dict) else None
        allowed = transfert.get("jira_claim_retrait") if identity is not None else None
        allowed = [item for item in allowed if isinstance(item, str)] if isinstance(allowed, list) else []
        # Chaque label du PUT est REVALIDÉ : une intention fusionnée d'une autre copie n'est qu'une donnée.
        if (identity is None or identity[1] != key or method.upper() != "PUT" or
                not set(ops[1]) <= set(allowed) or ops[0] != [transfert.get("jira_claim_label")] or
                not all(isinstance(lab, str) and _JIRA_LABEL.fullmatch(lab) for lab in [*ops[0], *ops[1]])):
            raise BoardError("JIRA: retrait de label refusé hors transfert de cette tâche")
    base, local, auth = config if config is not None else _jira_config()
    try:
        return _jira_transport().appel(method, base + path, auth, local, body)
    except (OSError, HTTPException):
        raise BoardError("JIRA: transport indisponible") from None


def jira_issue_for_task(task: dict[str, Any]) -> tuple[str, str] | None:
    """Return (site, key) for an imported task, without inventing an identity."""
    site, key = task.get("jira_site"), task.get("jira_key")
    return (site, key) if isinstance(site, str) and isinstance(key, str) and _JIRA_KEY.fullmatch(key) else None


def _jira_ulid(created: str, site: str, issue_id: str) -> str:
    import datetime as _dt
    try:
        instant = _dt.datetime.fromisoformat(created.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError
        ms = int(instant.timestamp() * 1000)
    except (ValueError, OverflowError):
        raise BoardError("JIRA: date created illisible") from None
    if not 0 <= ms < (1 << 48):
        raise BoardError("JIRA: date created hors plage")
    entropy = int.from_bytes(hashlib.sha256(f"{site}|{issue_id}".encode()).digest()[:10], "big")
    value = (ms << 80) | entropy
    chars = []
    for _ in range(26):
        chars.append(_JIRA_ALPHABET[value & 31])
        value >>= 5
    return "T-" + "".join(reversed(chars))


def _jira_utc(value: str) -> str:
    import datetime as _dt
    try:
        instant = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError
        return instant.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        raise BoardError("JIRA: date illisible") from None


def _jira_title(key: str, summary: Any) -> str:
    import unicodedata
    clean = "".join(" " if unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"} else ch
                    for ch in str(summary))
    clean = " ".join(clean.replace("|", "\\|").split())[:180]
    return f"Jira {key} — {clean or '(sans résumé)'}"


def _jira_record(issue: dict[str, Any], site: str, project: str) -> tuple[dict[str, Any], str]:
    import uuid as _uuid
    key, issue_id = issue.get("key"), issue.get("id")
    if not isinstance(key, str) or not _JIRA_KEY.fullmatch(key) or not key.startswith(project + "-"):
        raise BoardError("JIRA: clé de ticket refusée")
    if not isinstance(issue_id, str) or not re.fullmatch(r"[0-9]+", issue_id):
        raise BoardError("JIRA: id de ticket refusé")
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        raise BoardError("JIRA: fields absents")
    created, updated = fields.get("created"), fields.get("updated")
    if not isinstance(created, str) or not isinstance(updated, str):
        raise BoardError("JIRA: dates absentes")
    canonical_created = _jira_utc(created)
    _jira_utc(updated)
    tid = _jira_ulid(created, site, issue_id)
    parent = fields.get("parent")
    parent_key = parent.get("key") if isinstance(parent, dict) else None
    if parent_key is not None and (not isinstance(parent_key, str) or not _JIRA_KEY.fullmatch(parent_key)):
        parent_key = None
    issue_type = fields.get("issuetype")
    type_name = issue_type.get("name") if isinstance(issue_type, dict) else ""
    # Jira text remains untrusted; only its bounded title is displayed to agents.
    if not isinstance(type_name, str):
        type_name = ""
    import unicodedata
    type_name = " ".join("".join(" " if unicodedata.category(ch) in {"Cc", "Cf", "Zl", "Zp"}
                                 else ch for ch in type_name).replace("|", "\\|").split())
    record = {"id": tid, "state": "pending", "task": _jira_title(key, fields.get("summary", "")),
              "owner": "", "stage": "", "updated": canonical_created[:10],
              "pas_un_defaut": "ticket Jira importé, sans mesure locale",
              "jira_site": site, "jira_key": key, "jira_issue_id": issue_id,
              "jira_url": f"{site}/browse/{key}", "jira_created": canonical_created,
              "jira_type": type_name[:80]}
    if parent_key:
        record["jira_parent_key"] = parent_key
    operation = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"jira:{site}|{issue_id}"))
    return record, operation


def jira_import(root: str, project: str, *, issue_key: str | None = None,
                dry_run: bool = False) -> tuple[str, bool]:
    """Fetch every page before writing; each ticket then imports atomically."""
    from urllib.parse import urlencode
    if not _JIRA_PROJECT.fullmatch(project):
        raise BoardError("JIRA: clé de projet refusée")
    if issue_key is not None and (not _JIRA_KEY.fullmatch(issue_key) or
                                  not issue_key.startswith(project + "-")):
        raise BoardError("JIRA: clé de ticket refusée")
    config = _jira_config()  # fails before network when site/email are missing
    site = config[0]
    jql = f'project = "{project}" AND statusCategory != Done'
    if issue_key:
        jql += f' AND key = "{issue_key}"'
    token: str | None = None
    seen_tokens: set[str] = set()
    issues: list[dict[str, Any]] = []
    for _page_number in range(50):
        query = {"jql": jql, "fields": _JIRA_FIELDS, "maxResults": "100"}
        if token is not None:
            query["nextPageToken"] = token
        code, body = jira_request("GET", "/rest/api/3/search/jql?" + urlencode(query), config=config)
        if code != 200:
            raise BoardError(f"JIRA: recherche refusée (HTTP {code})")
        try:
            page = json.loads(body)
            batch = page["issues"]
            if not isinstance(batch, list) or not all(isinstance(item, dict) for item in batch) \
                    or not isinstance(page["isLast"], bool):
                raise ValueError
            issues.extend(batch)
            if page["isLast"]:
                break
            token = page["nextPageToken"]
            if not isinstance(token, str) or not token or token in seen_tokens:
                raise ValueError
            seen_tokens.add(token)
        except (ValueError, KeyError, TypeError):
            raise BoardError("JIRA: page de recherche illisible") from None
    else:
        raise BoardError("JIRA: recherche limitée à 50 pages ; import refusé")
    records = sorted((_jira_record(issue, site, project) for issue in issues),
                     key=lambda pair: (pair[0]["jira_created"], pair[0]["jira_key"]))
    if dry_run:
        return f"JIRA: dry-run {len(records)} ticket(s), aucun board écrit", False
    results = []
    collision = False
    for record, operation in records:
        try:
            results.append(new_jira_task(root, record, operation))
        except JiraCollision as exc:
            collision = True
            results.append(str(exc))
    return "\n".join(results) or "JIRA: aucun ticket", collision


def _jira_label(actor: dict[str, Any] | None) -> str | None:
    import unicodedata
    author = actor.get("auteur") if isinstance(actor, dict) else None
    value = (author.get("email") or author.get("nom")) if isinstance(author, dict) else None
    if not isinstance(value, str) or not value.strip():
        return None
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub("[^a-z0-9]+", "-", ascii_value).strip("-")[:40].strip("-") or "acteur"
    suffix = hashlib.sha256(value.encode()).hexdigest()[:10]
    return f"pris-par-{slug}-{suffix}"


def jira_prepare_claim(task: dict[str, Any], actor: dict[str, Any] | None) -> None:
    if jira_issue_for_task(task) is None:
        return
    if os.environ.get("JIRA_AGENT_CLAIM") == "0":
        task["jira_claim_status"] = "desactive"
        return
    label = _jira_label(actor)
    if label is None:
        task["jira_claim_status"] = "attente-acteur"
        return
    # TRANSFERT (S-01M5HH8QMC) : l'ancien label part dans l'intention, retiré par le même PUT
    # que l'ajout du nouveau ; la liste ne nomme que des labels que CETTE tâche a portés.
    previous = task.get("jira_claim_label")
    stored = task.get("jira_claim_retrait")
    pending = ([item for item in stored if isinstance(item, str) and _JIRA_LABEL.fullmatch(item)]
               if isinstance(stored, list) else [])
    if isinstance(previous, str) and _JIRA_LABEL.fullmatch(previous) and previous != label:
        pending.append(previous)
    pending = sorted(set(pending) - {label})
    if pending:
        task["jira_claim_retrait"] = pending
    else:
        task.pop("jira_claim_retrait", None)
    if (not pending and task.get("jira_claim_label") == label and task.get("jira_claim_actor") == actor
            and task.get("jira_claim_status") == "acquitte"
            and task.get("jira_claim_acquitte") == label):
        return
    task["jira_claim_label"] = label
    task["jira_claim_actor"] = copy.deepcopy(actor)
    # The keychain is resolved after the board lock, by jira_claim_retry.
    task["jira_claim_status"] = "attente"


def jira_claim_retry(root: str, tid: str, *, dry_run: bool = False) -> str:
    task = find(load(root), tid)
    identity = jira_issue_for_task(task)
    if identity is None:
        raise BoardError("JIRA: tâche sans identité Jira")
    if task.get("state") != "running":
        return f"JIRA: {tid} non running, aucun PUT"
    if os.environ.get("JIRA_AGENT_CLAIM") == "0":
        return f"JIRA: {tid} prise desactivee"
    label = task.get("jira_claim_label")
    actor = task.get("jira_claim_actor")
    retrait = task.get("jira_claim_retrait")
    if not isinstance(label, str) or not _JIRA_LABEL.fullmatch(label):
        raise BoardError("JIRA: aucune prise en attente")
    if dry_run:
        return f"JIRA: {tid} dry-run, aucun PUT"
    if retrait and _jira_transport().agent_appelant():
        return (f"JIRA: {tid} transfert en attente : retrait de label réservé au pilote, "
                f"jira-claim --retry {tid} depuis son terminal")
    ops = [{"remove": item} for item in retrait or []] + [{"add": label}]
    try:
        config = _jira_config(keychain=True)
        if config[0] != identity[0]:
            raise BoardError("JIRA: site configuré différent du ticket")
        code, _body = jira_request("PUT", f"/rest/api/3/issue/{identity[1]}",
                                   body={"update": {"labels": ops}}, config=config, transfert=task)
    except BoardError:
        return f"JIRA: {tid} prise en attente (configuration ou transport)"
    if code != 204:
        return f"JIRA: {tid} prise en attente (HTTP {code})"
    try:
        with board_lock(root):
            data = load(root)
            current = find(data, tid)
            if (current.get("jira_claim_label") != label or current.get("jira_claim_actor") != actor
                    or current.get("jira_claim_retrait") != retrait or current.get("state") != "running"):
                return f"JIRA: {tid} prise changée, accusé ignoré"
            before = copy.deepcopy(current)
            current["jira_claim_status"] = "acquitte"
            current["jira_claim_acquitte"] = label
            current.pop("jira_claim_retrait", None)
            enqueue_sync_intent(data, tid, before, current)
            save(root, data)
    except BoardError:
        return f"JIRA: {tid} label posé, accusé non écrit (verrou) — jira-claim --retry {tid}"
    return f"JIRA: {tid} prise acquittee"


def jira_claim_after_start(root: str, tid: str) -> str:
    task = find(load(root), tid)
    if jira_issue_for_task(task) is None:
        return ""
    if task.get("jira_claim_status") != "attente":
        return f"JIRA: {tid} prise {task.get('jira_claim_status', 'en attente')}"
    return jira_claim_retry(root, tid)
