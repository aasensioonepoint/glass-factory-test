# core-scripts/attribution-locale.ps1 — T-01M4TRY5VZF9FGXRD3PH9AVNGE
#
# POSE L'IDENTITÉ DU PROJET DANS `.claude/settings.local.json`, SOUS WINDOWS,
# SANS jq. C'est l'équivalent PowerShell de la recette bash de docs/usage.html
# (`project_init.py --print-otel-env --format json`, puis
# `jq -s '.[0] * {env: …}'`) : la même clé, posée au même endroit, pour que les
# coûts Claude Code de CE clone soient attribués à CE projet.
#
# USAGE
#   pwsh -NoProfile -File core-scripts/attribution-locale.ps1 [-Root <racine>]
#   powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\attribution-locale.ps1
#   Racine par défaut : le dossier PARENT de core-scripts/ (celui du script).
#
# CE QUE LE SCRIPT FAIT, DANS CET ORDRE
#   0. agent : `CLAUDECODE` posé dans l'environnement, avec une valeur non
#      blanche ⇒ REFUS (code 7). Vide ou fait de blancs, il vaut ABSENT (même
#      doctrine que `.agents/bin/skills_github_fallback.py`, qui compte un
#      marqueur après strip). `.claude/settings.local.json` est un fichier
#      réservé au pilote (`.claude/hooks/protect-paths.sh`) : ce script se lance
#      à la main, dans un terminal, jamais par un agent (décision de
#      l'orchestrateur, passe de correction de T-01M4TRY5VZF9FGXRD3PH9AVNGE).
#      PORTÉE : c'est une GARDE, pas une frontière — `env -u CLAUDECODE` la
#      défait (le banc le fait à chaque cas) ; elle empêche d'oublier, pas de
#      tricher. Et seul Claude Code est détecté : un autre hôte d'agent (Codex,
#      Copilot, Gemini…) qui ne pose pas `CLAUDECODE` est un FAUX NÉGATIF
#      nommé, jamais couvert ;
#   1. racine : `-Root`, sinon le parent du dossier du script ; puis RAMENÉE à
#      la racine que `project_init.py` lira. Ce dernier ne lit pas son dossier
#      de lancement : il prend la racine GIT de son répertoire courant
#      (`init.py` resoudre_racine_projet → `paths.py` _git_toplevel du paquet
#      `cadre`, sous `.agents/vendor/cadre/` ou `src/cadre/` :
#      `git -C <dossier> rev-parse --show-toplevel`), repli sur le dossier
#      lui-même. Le script fait la MÊME chose, avec le même repli :
#      git absent, ou dossier hors dépôt ⇒ la racine donnée. Lancement de
#      project_init, contrôle de l'identité et écriture portent ensuite TOUS sur
#      cette racine : `-Root <dépôt>/sub` écrit sous `<dépôt>`, jamais sous sub.
#      Conséquence, la racine PAR DÉFAUT aussi y est ramenée : dans un dépôt où
#      le kit n'est pas à la racine git (un monodépôt), le script cherche
#      project_init.py à la racine git et refuse (code 2) s'il n'y est pas —
#      exactement ce que project_init.py lirait ;
#   2. identité : `.agents/state/project.json` doit exister sous cette racine.
#      Absent, le script REFUSE et renvoie à l'init du projet ; il ne le crée
#      ni ne le copie JAMAIS (une identité copiée est une identité héritée) ;
#   3. Python 3 : résolu comme `.agents/pyrun.ps1` — python3, python, puis
#      `py -3` sous Windows, chaque candidat SONDÉ (un stub du Store qui ne rend
#      pas un exécutable Python 3 est écarté). L'ordre de pyrun.ps1 est gardé à
#      dessein : le hook et ce script choisissent le même Python. pyrun.ps1
#      n'est pas APPELÉ : il hérite la sortie de l'enfant, on ne pourrait pas la
#      lire ; ses fonctions sont reprises ci-dessous, stderr capturé en plus. La
#      sonde écrit `sys.executable` en OCTETS UTF-8 : écrit en texte, il
#      sortirait dans l'encodage du pipe (cp1252 sous Windows) et un chemin
#      accentué (`C:\Users\<prénom-accentué>\…`) deviendrait introuvable ;
#   4. valeur : `project_init.py --print-otel-env --format json`. On n'en garde
#      QUE `env.OTEL_RESOURCE_ATTRIBUTES`, seule clé qu'il rend depuis
#      T-01M4WNKCBXS893CHPSKD1Z1PN9. Extraite par une expression régulière,
#      PAS par ConvertFrom-Json : la sortie d'un kit vendorisé antérieur
#      recopie l'env de `.claude/settings.json`, où un poste d'entreprise porte
#      `http_proxy` ET `HTTP_PROXY` — ConvertFrom-Json LÈVE alors une erreur
#      (mesuré sous pwsh 7.6.6 par le banc : témoin h2, mutant qui réintroduit
#      ConvertFrom-Json ; la version est relevée à chaque passage du banc).
#      La valeur doit tenir en entier dans
#      `agentkit.project_id=<sans guillemet, antislash ni blanc>` : c'est la
#      CLASSE `[^"\\\s]` qui refuse un saut de ligne final, même échappé
#      (code 5). L'ancre `\z` n'est qu'une redondance : une chaîne JSON brute ne
#      peut pas porter un vrai saut de ligne, la classe s'arrête avant ;
#   5. fusion : confiée à Python (`json` de la bibliothèque standard), PAS à
#      ConvertFrom-Json, qui accepte les commentaires, convertit les chaînes
#      horodatées en DateTime (un `+02:00` ramené à l'heure locale) et refuse
#      les deux proxies ci-dessus (doc Microsoft, ConvertFrom-Json 7.4 ; mesure
#      pwsh 7.6.6 du banc). Fichier absent ou vide (blancs seuls) : on part de `{}`.
#      Toutes les clés existantes sont gardées, dans leur ordre ; une valeur
#      ancienne de la clé est remplacée. Un `settings.local.json` LIEN
#      SYMBOLIQUE est refusé (le remplacer casserait le lien) : écrivez la cible ;
#   6. écriture ATOMIQUE : fichier temporaire dans le MÊME dossier, puis
#      `os.replace` (nouvel inode) ; UTF-8 SANS BOM (Windows PowerShell 5.1 en
#      met un par défaut, et Claude Code doit relire le fichier) ; un BOM hérité
#      est ôté ; sortie en JSON STRICT (`allow_nan=False` : un `1e400` lu comme
#      l'infini est refusé, jamais réécrit `Infinity`) ;
#   7. idempotent : valeur déjà posée dans un fichier sans BOM ⇒ AUCUNE
#      écriture, octets et inode inchangés ;
#   8. témoin : la valeur posée, sur la sortie standard.
#
# CODES DE SORTIE
#   0    valeur posée, ou déjà posée (fichier inchangé)
#   1    erreur PowerShell inattendue ; le fichier n'est écrit que par l'étape
#        Python, atomique, donc INTACT
#   2    usage : racine introuvable, ou `.agents/bin/project_init.py` absent
#        sous la racine résolue
#   3    identité absente (`.agents/state/project.json`) : lancer d'abord l'init
#   4    `settings.local.json` REFUSÉ — JSON invalide, racine ou `env` qui n'est
#        pas un objet, clé en double, NaN/Infinity ou nombre hors double,
#        encodage non UTF-8, lien symbolique ; fichier INTACT
#   5    `project_init.py` a échoué (son message est relayé), ou sa sortie ne
#        porte pas UNE valeur `agentkit.project_id=<id>` bien formée
#   6    lecture ou écriture impossible ; fichier INTACT
#   7    lancé par un agent (`CLAUDECODE` posé) : à lancer soi-même, dans un
#        terminal ; rien n'est lu ni écrit
#   127  Python 3 introuvable (même code que `.agents/pyrun.ps1`)
#
# COMPATIBILITÉ : PowerShell 7 (pwsh) ET Windows PowerShell 5.1. Donc ni `??`,
# ni `?.`, ni ternaire, ni `&&` / `||` de pipeline, ni `-AsHashtable`, ni
# `$IsWindows`. Toute ligne de CODE reste en ASCII : 5.1 lit un .ps1 sans BOM
# comme de l'ANSI, et certains octets UTF-8 y deviennent des guillemets
# typographiques, que PowerShell prend pour des délimiteurs. Les accents ne
# vivent que dans les commentaires `#` ; les messages sont en français sans
# accents. Le banc `core-scripts/attribution-locale.test.sh` tient ces règles
# par une LECTURE statique : 5.1 lui-même n'y est PAS exécuté.
[CmdletBinding()]
param(
    [string] $Root = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:Prefixe = 'attribution-locale:'

function Write-Refus {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Message
    )
    [Console]::Error.WriteLine($script:Prefixe + ' ' + $Message)
}

# --- Lancement d'un enfant natif : repris de .agents/pyrun.ps1 --------------
# ProcessStartInfo évite l'analyseur d'arguments natifs de PowerShell, qui
# change selon la version. ArgumentList quand il existe (PS 7), sinon une ligne
# de commande citée selon les règles MSVCRT (PS 5.1).

function ConvertTo-NativeArgument {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Value
    )

    if ($Value.Length -eq 0) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = New-Object System.Text.StringBuilder
    [void] $builder.Append('"')
    $backslashCount = 0

    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') {
            $backslashCount += 1
            continue
        }

        if ($character -eq '"') {
            if ($backslashCount -gt 0) {
                [void] $builder.Append([char] 92, (2 * $backslashCount))
            }
            [void] $builder.Append('\"')
            $backslashCount = 0
            continue
        }

        if ($backslashCount -gt 0) {
            [void] $builder.Append([char] 92, $backslashCount)
            $backslashCount = 0
        }
        [void] $builder.Append($character)
    }

    if ($backslashCount -gt 0) {
        [void] $builder.Append([char] 92, (2 * $backslashCount))
    }
    [void] $builder.Append('"')
    return $builder.ToString()
}

# AllowEmptyString : sans lui, un argument VIDE fait echouer la liaison de ce
# parametre obligatoire ("chaine vide") et le repli de 5.1 jette, alors que
# ArgumentList (pwsh 7) l'accepte et que ConvertTo-NativeArgument le cite en "".
# Meme defaut que core-scripts/setup.ps1, mesure par le cas (W9) de setup.test.sh.
function Join-NativeArguments {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]] $Values
    )

    $quotedValues = New-Object 'System.Collections.Generic.List[string]'
    foreach ($value in $Values) {
        [void] $quotedValues.Add((ConvertTo-NativeArgument -Value $value))
    }
    return [string]::Join(' ', $quotedValues.ToArray())
}

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FileName,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]] $ArgumentValues,

        [Parameter(Mandatory = $true)]
        [string] $WorkingDirectory
    )

    # Sorties lues en UTF-8 quelle que soit la page de code de la console :
    # l'enfant Python est lancé avec -X utf8, les deux bouts s'accordent.
    $utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $utf8
    $startInfo.StandardErrorEncoding = $utf8
    # Posé sur l'ENFANT seul, jamais dans la session de l'appelant.
    $startInfo.EnvironmentVariables['PYTHONDONTWRITEBYTECODE'] = '1'

    # ATTRIBUTION_LOCALE_FORCE_ARGUMENTS, non vide, force la voie 5.1 (ligne de
    # commande citée) sous PS 7 : c'est ainsi que le banc l'exerce (cas u), 5.1
    # n'étant pas exécutable sur son poste. Réservé au banc.
    $argumentListProperty = $startInfo.PSObject.Properties['ArgumentList']
    if ($null -ne $argumentListProperty -and [string]::IsNullOrEmpty($env:ATTRIBUTION_LOCALE_FORCE_ARGUMENTS)) {
        foreach ($argumentValue in $ArgumentValues) {
            [void] $startInfo.ArgumentList.Add($argumentValue)
        }
    }
    else {
        $startInfo.Arguments = Join-NativeArguments -Values $ArgumentValues
    }

    $process = New-Object System.Diagnostics.Process
    try {
        $process.StartInfo = $startInfo
        if (-not $process.Start()) {
            throw "could not start $FileName"
        }

        # Rien n'est écrit sur l'entrée de l'enfant : le code Python passe par
        # -c, jamais par stdin (sous .NET Framework, StandardInput peut émettre
        # un BOM quand la console est en page 65001).
        $process.StandardInput.Close()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $capturedExitCode = $process.ExitCode
        $capturedStdout = $stdoutTask.GetAwaiter().GetResult()
        $capturedStderr = $stderrTask.GetAwaiter().GetResult()

        return [PSCustomObject]@{
            ExitCode = $capturedExitCode
            Stdout   = $capturedStdout
            Stderr   = $capturedStderr
        }
    }
    finally {
        $process.Dispose()
    }
}

function Resolve-ApplicationPath {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name
    )

    $applications = @(Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue)
    if ($applications.Count -eq 0) {
        return $null
    }
    return $applications[0].Source
}

function Resolve-Python3 {
    param(
        [Parameter(Mandatory = $true)]
        [string] $WorkingDirectory,

        [Parameter(Mandatory = $true)]
        [bool] $RunningOnWindows
    )

    $candidates = @(
        [PSCustomObject]@{ Name = 'python3'; Prefix = [string[]] @() },
        [PSCustomObject]@{ Name = 'python'; Prefix = [string[]] @() }
    )
    if ($RunningOnWindows) {
        $candidates += [PSCustomObject]@{ Name = 'py'; Prefix = [string[]] @('-3') }
    }

    # Octets UTF-8, jamais du texte : voir l'en-tête, étape 3 (pyrun.ps1 écrit
    # en texte ; ici on LIT la sortie, donc l'encodage du pipe compte).
    $probeCode = 'import sys; sys.exit(1) if sys.version_info[0] != 3 else None; sys.stdout.buffer.write(sys.executable.encode())'
    foreach ($candidate in $candidates) {
        $candidatePath = Resolve-ApplicationPath -Name $candidate.Name
        if ([string]::IsNullOrEmpty($candidatePath)) {
            continue
        }

        [string[]] $probeArguments = @()
        foreach ($prefixArgument in $candidate.Prefix) {
            $probeArguments += $prefixArgument
        }
        $probeArguments += '-c'
        $probeArguments += $probeCode

        try {
            $probeResult = Invoke-CapturedProcess `
                -FileName $candidatePath `
                -ArgumentValues $probeArguments `
                -WorkingDirectory $WorkingDirectory
        }
        catch {
            continue
        }

        if ($probeResult.ExitCode -ne 0) {
            continue
        }
        $resolvedPython = $probeResult.Stdout.TrimEnd("`r", "`n")
        if ([string]::IsNullOrEmpty($resolvedPython)) {
            continue
        }
        if (-not [System.IO.File]::Exists($resolvedPython)) {
            continue
        }
        return [System.IO.Path]::GetFullPath($resolvedPython)
    }

    return $null
}

# La racine git du dossier, comme `paths.py` _git_toplevel du paquet `cadre`
# (`.agents/vendor/cadre/` ou `src/cadre/`) la lit pour
# project_init.py : `git -C <dossier> rev-parse --show-toplevel`. $null si git
# est absent, échoue, ou si le dossier n'est dans aucun dépôt : l'appelant
# retombe alors sur le dossier lui-même, le même repli que project_init.py.
function Resolve-RacineGit {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Depart
    )

    $gitPath = Resolve-ApplicationPath -Name 'git'
    if ([string]::IsNullOrEmpty($gitPath)) {
        return $null
    }
    try {
        $resultat = Invoke-CapturedProcess `
            -FileName $gitPath `
            -ArgumentValues @('-C', $Depart, 'rev-parse', '--show-toplevel') `
            -WorkingDirectory $Depart
    }
    catch {
        return $null
    }
    if ($resultat.ExitCode -ne 0) {
        return $null
    }
    $haut = $resultat.Stdout.Trim()
    if ($haut.Length -eq 0) {
        return $null
    }
    return [System.IO.Path]::GetFullPath($haut)
}

# --- La fusion, en Python ----------------------------------------------------
# Lancée `-I -X utf8 -c <code> <chemin> <valeur>` : -I écarte le répertoire
# courant de sys.path (un json.py posé à la racine ne s'importe pas), -X utf8
# fixe l'encodage des sorties. Contrat des codes : 0 (stdout `ecrit` ou
# `inchange`), 4 (refus du contenu), 6 (lecture ou écriture impossible) — le
# message part sur stderr. Code en ASCII, sans commentaire : il vit dans une
# chaîne PowerShell.
$codeFusion = @'
import json, os, shutil, sys, tempfile, time
chemin, valeur = sys.argv[1], sys.argv[2]
cle = 'OTEL_RESOURCE_ATTRIBUTES'
def refus(code, motif):
    sys.stderr.write(motif + '\n')
    sys.exit(code)
def paires(liste):
    vues = {}
    for k, v in liste:
        if k in vues:
            raise ValueError('cle en double : ' + json.dumps(k))
        vues[k] = v
    return vues
def constante(nom):
    raise ValueError('constante non JSON : ' + nom)
if os.path.islink(chemin):
    refus(4, 'lien symbolique : ecrivez la cible ' + os.path.realpath(chemin))
existe = os.path.lexists(chemin)
brut = b''
if existe:
    try:
        with open(chemin, 'rb') as f:
            brut = f.read()
    except OSError as e:
        refus(6, 'lecture impossible : ' + str(e))
bom = brut.startswith(b'\xef\xbb\xbf')
try:
    texte = brut.decode('utf-8-sig')
except UnicodeDecodeError as e:
    refus(4, 'encodage non UTF-8 : ' + str(e))
vide = texte.strip(' \t\r\n') == ''
if vide:
    donnees = {}
else:
    try:
        donnees = json.loads(texte, object_pairs_hook=paires, parse_constant=constante)
    except (ValueError, RecursionError) as e:
        refus(4, 'JSON invalide : ' + str(e))
if not isinstance(donnees, dict):
    refus(4, 'la racine du JSON n est pas un objet')
if 'env' not in donnees:
    donnees['env'] = {}
env = donnees['env']
if not isinstance(env, dict):
    refus(4, 'la cle env n est pas un objet')
if existe and not vide and not bom and env.get(cle) == valeur:
    sys.stdout.write('inchange\n')
    sys.exit(0)
env[cle] = valeur
try:
    sortie = (json.dumps(donnees, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
except (UnicodeEncodeError, ValueError) as e:
    refus(4, 'hors JSON strict (nombre hors double, ou chaine non encodable en UTF-8) : ' + str(e))
dossier = os.path.dirname(os.path.abspath(chemin))
try:
    os.makedirs(dossier, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dossier, prefix='.settings.local.json.', suffix='.tmp')
except OSError as e:
    refus(6, 'fichier temporaire impossible : ' + str(e))
try:
    with os.fdopen(fd, 'wb') as f:
        f.write(sortie)
        f.flush()
        os.fsync(f.fileno())
    if existe:
        shutil.copymode(chemin, tmp)
    for essai in range(10):
        try:
            os.replace(tmp, chemin)
            break
        except PermissionError:
            if essai == 9:
                raise
            time.sleep(0.1)
except OSError as e:
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    try:
        os.unlink(tmp)
    except OSError:
        pass
    refus(6, 'ecriture impossible : ' + str(e))
sys.stdout.write('ecrit\n')
'@

# --- Déroulé ------------------------------------------------------------------
try {
    # (0) Jamais sous un agent : settings.local.json est réservé au pilote.
    if (-not [string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable('CLAUDECODE'))) {
        Write-Refus 'a lancer par vous-meme dans un terminal, pas par un agent :'
        Write-Refus '.claude/settings.local.json est reserve au pilote (CLAUDECODE est pose ici). Rien n a ete lu ni ecrit.'
        exit 7
    }

    $runningOnWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT

    # (1) La racine : -Root, sinon le parent du dossier du script.
    if ([string]::IsNullOrEmpty($Root)) {
        if ([string]::IsNullOrEmpty($PSScriptRoot)) {
            Write-Refus 'dossier du script inconnu -- passez -Root <racine du depot>'
            exit 2
        }
        $racine = [System.IO.Path]::Combine($PSScriptRoot, '..')
    }
    else {
        $racine = $Root
        if (-not [System.IO.Path]::IsPathRooted($racine)) {
            $racine = [System.IO.Path]::Combine((Get-Location).ProviderPath, $racine)
        }
    }
    try {
        $racine = [System.IO.Path]::GetFullPath($racine)
    }
    catch {
        Write-Refus ('racine illisible : ' + $racine)
        exit 2
    }
    if (-not [System.IO.Directory]::Exists($racine)) {
        Write-Refus ('racine introuvable : ' + $racine)
        exit 2
    }

    # Ramenée à la racine git, celle que project_init.py lira (en-tête, (1)).
    $racineDemandee = $racine
    $racineGit = Resolve-RacineGit -Depart $racine
    if (-not [string]::IsNullOrEmpty($racineGit)) {
        $comparaison = [System.StringComparison]::Ordinal
        if ($runningOnWindows) {
            $comparaison = [System.StringComparison]::OrdinalIgnoreCase
        }
        $separateurs = [char[]] @(
            [System.IO.Path]::DirectorySeparatorChar,
            [System.IO.Path]::AltDirectorySeparatorChar
        )
        if (-not [string]::Equals($racineGit.TrimEnd($separateurs), $racine.TrimEnd($separateurs), $comparaison)) {
            Write-Refus ('note : racine git ' + $racineGit + ' (et non ' + $racine + ') : c est elle que project_init.py lit.')
        }
        $racine = $racineGit
    }

    $projectInit = [System.IO.Path]::Combine($racine, '.agents', 'bin', 'project_init.py')
    if (-not [System.IO.File]::Exists($projectInit)) {
        $kitDemande = [System.IO.Path]::Combine($racineDemandee, '.agents', 'bin', 'project_init.py')
        if ($racineDemandee -ne $racine -and [System.IO.File]::Exists($kitDemande)) {
            # Monodépôt : le kit est sous la racine git, pas à elle.
            Write-Refus ('racine git ' + $racine + ' : .agents/bin/project_init.py n y est pas, mais le kit est sous ' + $racineDemandee + '.')
            Write-Refus 'project_init.py lit la racine git de son dossier : placez le kit a la racine du depot git, ou faites de son dossier un depot git.'
        }
        else {
            Write-Refus ('.agents/bin/project_init.py absent sous ' + $racine + ' : cette racine ne porte pas le kit.')
        }
        exit 2
    }

    # (2) L'identité : lue par project_init.py, jamais créée ni copiée ici.
    $identite = [System.IO.Path]::Combine($racine, '.agents', 'state', 'project.json')
    if (-not [System.IO.File]::Exists($identite)) {
        Write-Refus 'identite du projet absente (.agents/state/project.json).'
        Write-Refus 'Lancez d abord l init du projet : python .agents/bin/project_init.py (py -3 sous Windows).'
        exit 3
    }

    # (3) Python 3, sans supposer un nom unique sur le PATH.
    $python = Resolve-Python3 -WorkingDirectory $racine -RunningOnWindows $runningOnWindows
    if ([string]::IsNullOrEmpty($python)) {
        Write-Refus 'PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3.'
        exit 127
    }

    # (4) La valeur, et elle seule.
    $publication = Invoke-CapturedProcess `
        -FileName $python `
        -ArgumentValues @('-X', 'utf8', $projectInit, '--print-otel-env', '--format', 'json') `
        -WorkingDirectory $racine
    if ($publication.ExitCode -ne 0) {
        $motif = $publication.Stderr.Trim()
        if ($motif.Length -gt 0) {
            [Console]::Error.WriteLine($motif)
        }
        Write-Refus ('project_init.py --print-otel-env a echoue (code ' + $publication.ExitCode + ')')
        exit 5
    }

    # Par expression reguliere, jamais ConvertFrom-Json (en-tete, (4)) : la
    # sortie peut porter http_proxy ET HTTP_PROXY. Une seule occurrence exigee ;
    # c est la classe (ni guillemet, ni antislash, ni blanc) qui refuse un saut
    # de ligne, meme echappe ; \z n est qu une redondance.
    $motifOtel = '"OTEL_RESOURCE_ATTRIBUTES"\s*:\s*"(agentkit\.project_id=[^"\\\s]+)"'
    $occurrences = [System.Text.RegularExpressions.Regex]::Matches($publication.Stdout, $motifOtel)
    $valeur = $null
    if ($occurrences.Count -eq 1) {
        $valeur = $occurrences[0].Groups[1].Value
    }
    if ($null -eq $valeur -or $valeur -cnotmatch '\Aagentkit\.project_id=[^"\\\s]+\z') {
        Write-Refus 'sortie de project_init.py sans UNE valeur env.OTEL_RESOURCE_ATTRIBUTES = agentkit.project_id=<id> bien formee'
        exit 5
    }

    # (5) (6) (7) Fusion, écriture atomique, idempotence : l'étape Python.
    $settings = [System.IO.Path]::Combine($racine, '.claude', 'settings.local.json')
    $fusion = Invoke-CapturedProcess `
        -FileName $python `
        -ArgumentValues @('-I', '-X', 'utf8', '-c', $codeFusion, $settings, $valeur) `
        -WorkingDirectory $racine
    $etat = $fusion.Stdout.Trim()
    $motifFusion = $fusion.Stderr.Trim()
    if ($fusion.ExitCode -eq 4) {
        Write-Refus ($settings + ' refuse : ' + $motifFusion + ' -- fichier intact, corrigez-le puis relancez')
        exit 4
    }
    if ($fusion.ExitCode -ne 0) {
        if ($motifFusion.Length -gt 0) {
            [Console]::Error.WriteLine($motifFusion)
        }
        Write-Refus ($settings + ' non ecrit (code ' + $fusion.ExitCode + ') -- fichier intact')
        exit 6
    }

    # (8) Le témoin : la valeur posée, puis ce qui a été fait.
    [Console]::Out.WriteLine($script:Prefixe + ' OTEL_RESOURCE_ATTRIBUTES=' + $valeur)
    if ($etat -eq 'inchange') {
        [Console]::Out.WriteLine($script:Prefixe + ' deja posee, fichier inchange : ' + $settings)
    }
    else {
        [Console]::Out.WriteLine($script:Prefixe + ' posee dans ' + $settings)
    }
    exit 0
}
catch {
    Write-Refus ('erreur inattendue : ' + $_.Exception.Message)
    exit 1
}
