# core-scripts/setup.ps1 — T-01M4WHQQHHGFS6NPSFQ9TSM36V
#
# INSTALLE LES PRÉREQUIS DU KIT SOUS WINDOWS, PAR winget. L'étape 2 « Équipe
# ton poste » de docs/usage.html, système Windows ; macOS et Ubuntu : core-scripts/setup.sh.
#
# USAGE
#   powershell -NoProfile -ExecutionPolicy Bypass -File core-scripts\setup.ps1 [-DryRun]
#   pwsh -NoProfile -File core-scripts/setup.ps1 [-DryRun] [-Inventory <tsv>]
#     -DryRun     dit ce qu'il ferait ; n'installe RIEN, n'écrit rien
#     -Inventory  autre inventaire (défaut : core-scripts/tool-inventory.tsv) — bancs
#   SETUP_PS1_OS=windows   force la branche Windows hors de Windows — RÉSERVÉ AU
#                          BANC (core-scripts/setup.test.sh joue le script sous
#                          pwsh macOS avec un winget factice) ; winget est cherché
#                          dans PATH, c'est le PATH que le banc remplace.
#
# CE QU'IL INSTALLE — DÉRIVÉ DE L'INVENTAIRE, JAMAIS D'UNE LISTE ÉCRITE ICI.
#   Les lignes `nature=outil`, `class=B` de core-scripts/tool-inventory.tsv dont
#   la colonne `os` vaut `any` ou contient `windows` : ce sans quoi la
#   vérification du kit (core-scripts/verify.sh, sous Git Bash) ne tourne pas.
#   À l'inventaire relevé le 2026-10-06 : git >= 2.34, bash >= 4, python3 >= 3.11,
#   pytest, tee. Rien d'autre : les outils de classe A ne sont PAS installés —
#   core-scripts/doctor.sh (l'étape 2, sous Git Bash) dit ce que chacun coûte.
#
# PAR QUEL CANAL — winget, ET UN SEUL pip.
#   LE NOM DU PAQUET est la table `Get-CanalWinget` ci-dessous — DÉCLARÉE, pas
#   dérivée : la colonne `windows` de l'inventaire dit le canal que la CI du kit
#   exécute (une archive zip épinglée pour ctags), jamais un identifiant winget.
#   Les identifiants (Git.Git, Python.Python.3.12) sont ceux du dépôt winget
#   public et NE SONT PAS MESURÉS sur ce poste.
#     git, bash, tee  → Git.Git (Git for Windows livre Git Bash : bash.exe et
#                        tee.exe sous <Git>\bin et <Git>\usr\bin)
#     python3         → Python.Python.3.12
#     pytest          → `<python> -m pip install --user pytest==<pin>` : winget
#                        n'a pas pytest ; pip est le gestionnaire de paquets de
#                        Python lui-même, annoncé avant d'être lancé. La version
#                        est ÉPINGLÉE ($script:PytestPin) à celle que la CI du
#                        kit installe (.github/workflows/ci.yml, `pytest==`),
#                        jamais « la dernière » ; le banc (W0) relit les deux
#                        et rougit quand la CI bouge. Si Python vient
#                        d'être posé par ce passage, il est RE-SONDÉ après
#                        winget ; s'il n'est pas encore visible de cette session
#                        (winget écrit le PATH système), pytest est rapporté
#                        « manque encore », avec la commande à taper dans un
#                        NOUVEAU terminal.
#   Jamais `iex` d'un contenu distant, jamais un installateur téléchargé, jamais
#   une élévation : winget demande lui-même le consentement UAC quand un paquet
#   l'exige, et le script ne le contourne pas. winget absent : le script
#   s'arrête (2) et renvoie à « App Installer » du Microsoft Store.
#
# CE QU'IL FAIT, DANS CET ORDRE
#   0. agent : un marqueur d'agent posé (valeur non blanche) et pas -DryRun ⇒
#      REFUS (7), qui nomme le marqueur trouvé. Les marqueurs, lus dans cet
#      ordre : CLAUDECODE et CLAUDE_CODE_ENTRYPOINT (Claude Code, shell de
#      l'agent), AGENTS_HOOK_HOST (posé par les configs de hooks du kit, dans
#      les SOUS-PROCESSUS DE HOOK seulement, jamais dans le shell de l'agent),
#      COPILOT_AGENT_SESSION_ID et COPILOT_CLI (shell de l'agent Copilot CLI,
#      mesurés en 1.0.96) — la liste de core-scripts/setup.sh. Ce script
#      modifie le poste : il se lance à la main, dans un terminal. C'est une
#      GARDE, pas une frontière : elle freine, elle ne ferme pas ; elle empêche
#      d'oublier, pas de tricher. FAUX NÉGATIF NOMMÉ : Codex, Gemini et Kimi
#      n'exposent aucun marqueur mesuré dans le shell de l'agent
#      (AGENTS_HOOK_HOST n'y est pas) : lancé depuis LEUR shell d'agent, ce
#      script n'est pas refusé.
#      Borne : COPILOT_CLI est hérité par un shell lancé depuis Copilot CLI —
#      faux positif assumé : lancez depuis un terminal ouvert hors de Copilot CLI ;
#   1. plateforme (Win32NT, ou SETUP_PS1_OS=windows) ; winget sur le PATH ;
#   2. AVANT : chaque outil B est cherché par NOM sur le PATH (Get-Command,
#      applications seulement), alternative par alternative (`python3|python|py`).
#      Quand la colonne `version` porte une contrainte, le candidat exécute
#      `--version` : un code ≠ 0 ou une sortie sans numéro l'ÉCARTE — c'est
#      ainsi que l'alias `python.exe` du Microsoft Store, qui ouvre le Store au
#      lieu de répondre, n'est pas compté présent. `>=X.Y` compare le premier
#      numéro pointé ; une contrainte textuelle est cherchée dans la sortie.
#      bash et tee : les dossiers de Git for Windows (<Git>\bin, <Git>\usr\bin,
#      résolus depuis git.exe) sont sondés AVANT le PATH — sur le PATH,
#      `bash.exe` est souvent le lanceur WSL de System32, qui n'est pas le bash
#      que Git Bash lance. pytest : le binaire, sinon `<python> -m pytest`.
#      Ce n'est PAS la sonde de core-scripts/doctor.sh (bash, injoignable d'ici
#      quand bash manque) : le doctor, à l'étape 2, reste l'arbitre ;
#   3. plan : un canal par outil absent ou en mauvaise version — un outil
#      présent à la bonne version n'entre PAS dans le plan : relancer ne
#      réinstalle rien ;
#   4. -DryRun : le plan, puis la sortie ; sinon une commande winget par
#      identifiant (dédoublonné : Git.Git une fois pour git, bash, tee), chacune
#      affichée avant d'être lancée, puis pip pour pytest ;
#   5. APRÈS : re-sonde ; trois listes — installes, deja la, manque encore
#      (avec la commande à taper) ; puis UNE ligne de résumé :
#        setup: installes=... deja la=... manque encore=... -- exit N
#      (en ASCII : voir COMPATIBILITÉ ; la forme de setup.sh porte des accents).
#   6. juste avant la ligne de résumé : pilote de fusion — python ≥ 3.11 (1er
#      de python3|python|py), --verifier ; non installé et stdin terminal :
#      question [o/N], seuls o/oui lancent --installer (--depuis origin/develop
#      dans le kit sur develop) puis --verifier ; -DryRun, marqueur d'agent,
#      non-terminal : rien armé, dit ; le code de sortie n'en dépend jamais ;
#      une sortie 2 ne l'atteint pas.
#
# CE QU'IL NE PROMET PAS — dit plutôt que découvert.
#   - le PATH de cette session : winget ajoute Git et Python au PATH SYSTÈME ;
#     la session courante ne le voit pas toujours — « manque encore » après une
#     installation réussie signifie souvent « ouvrez un nouveau terminal » ;
#   - un pytest visible de Git Bash : `pip --user` pose pytest.exe sous
#     %APPDATA%\Python\Python3xx\Scripts, pas toujours sur le PATH ; la sonde
#     par module (`python -m pytest`) le voit, le doctor (par nom) peut ne pas
#     le voir : c'est la borne nommée en tête de doctor.sh ;
#   - Windows PowerShell 5.1 n'est jamais EXÉCUTÉ par le banc (W0 le borne par
#     une lecture statique ; W9 joue sous pwsh le CODE du repli `Arguments` de
#     5.1, forcé sur une copie, mais ni l'aiguillage sous .NET Framework ni le
#     découpage de la ligne par Windows) ; les identifiants winget ne sont pas
#     mesurés.
#
# CODES DE SORTIE
#   0    tous les outils B sont présents (déjà là, ou installés par ce passage) ;
#        en -DryRun : rien à installer
#   1    il manque encore quelque chose après l'installation (winget ou pip en
#        échec, PATH non rafraîchi, version restée basse) ; en -DryRun : il y a
#        quelque chose à installer
#   2    usage : hors Windows (→ core-scripts/setup.sh), winget absent,
#        inventaire introuvable ou illisible
#   7    lancé par un agent (marqueur d'agent posé, étape 0) sans -DryRun :
#        rien n'est fait
#   1    erreur PowerShell inattendue (message sur stderr)
#
# COMPATIBILITÉ : PowerShell 7 (pwsh) ET Windows PowerShell 5.1. Donc ni `??`,
# ni `?.`, ni ternaire, ni `&&` / `||` de pipeline, ni `-AsHashtable`, ni
# `$IsWindows`. Toute ligne de CODE reste en ASCII : 5.1 lit un .ps1 sans BOM
# comme de l'ANSI, et certains octets UTF-8 y deviennent des guillemets
# typographiques. Les accents ne vivent que dans les commentaires `#` ; les
# messages sont en français sans accents. Le banc core-scripts/setup.test.sh
# tient ces règles par une LECTURE statique (W0).
[CmdletBinding()]
param(
    [switch] $DryRun,
    [string] $Inventory = ''
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$script:Prefixe = 'setup:'
# La version de pytest que pip pose : celle que la CI du kit epingle par hash
# (.github/workflows/ci.yml, ligne `pytest==`). A changer ICI quand la CI change ;
# le banc (W0) compare les deux.
$script:PytestPin = 'pytest==9.1.1'

function Write-Refus {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Message
    )
    [Console]::Error.WriteLine($script:Prefixe + ' ' + $Message)
}

function Write-Ligne {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Message
    )
    [Console]::Out.WriteLine($Message)
}

function Write-Dire {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Message
    )
    [Console]::Out.WriteLine($script:Prefixe + ' ' + [regex]::Replace($Message, '[\x00-\x1F\x7F]', '?'))
}

# --- Lancement d'un enfant natif, sorties capturées : repris de attribution-locale.ps1
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
# parametre obligatoire (« chaine vide ») et le repli de 5.1 jette, alors que
# ArgumentList (pwsh 7) l'accepte et que ConvertTo-NativeArgument le cite en "".
# Mesure par le cas (W9) de setup.test.sh, 2026-10-14.
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
        [string[]] $ArgumentValues
    )

    $utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = $utf8
    $startInfo.StandardErrorEncoding = $utf8

    $argumentListProperty = $startInfo.PSObject.Properties['ArgumentList']
    if ($null -ne $argumentListProperty) {
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

# --- L'inventaire, par NOM de colonne ---------------------------------------
# Lignes `#` ignorées ; la première ligne restante nomme les colonnes ;
# séparateur TABULATION, champ `-` = sans objet. Chaque ligne rendue porte
# Tool, Nature, Os, Class, Version. Une colonne requise absente, ou une ligne
# au mauvais nombre de champs : exception, l'appelant sort 2.
function Read-Inventaire {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Chemin
    )

    $utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
    $lignes = [System.IO.File]::ReadAllLines($Chemin, $utf8)
    $colonnes = $null
    $nombre = 0
    $entrees = New-Object 'System.Collections.Generic.List[object]'
    $numero = 0
    foreach ($brute in $lignes) {
        $numero += 1
        $ligne = $brute.TrimEnd("`r")
        if ($ligne.StartsWith('#')) {
            continue
        }
        if ($ligne.Trim().Length -eq 0) {
            continue
        }
        $champs = $ligne.Split("`t")
        if ($null -eq $colonnes) {
            $colonnes = @{}
            for ($i = 0; $i -lt $champs.Count; $i++) {
                $colonnes[$champs[$i]] = $i
            }
            $nombre = $champs.Count
            foreach ($requise in @('tool', 'nature', 'os', 'class', 'version')) {
                if (-not $colonnes.ContainsKey($requise)) {
                    throw ('colonne requise absente de la ligne de colonnes : ' + $requise)
                }
            }
            continue
        }
        if ($champs.Count -ne $nombre) {
            throw ('ligne ' + $numero + ' : ' + $champs.Count + ' champs, ' + $nombre + ' attendus')
        }
        $entrees.Add([PSCustomObject]@{
            Tool    = $champs[$colonnes['tool']]
            Nature  = $champs[$colonnes['nature']]
            Os      = $champs[$colonnes['os']]
            Class   = $champs[$colonnes['class']]
            Version = $champs[$colonnes['version']]
        })
    }
    if ($null -eq $colonnes) {
        throw 'aucune ligne de colonnes'
    }
    return $entrees
}

function Test-OsApplique {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Cellule
    )
    if ($Cellule -eq 'any') {
        return $true
    }
    return (',' + $Cellule + ',').Contains(',windows,')
}

# --- La version : premier numéro pointé, comparé champ par champ -------------
function Get-NumeroVersion {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string] $Sortie
    )
    $m = [System.Text.RegularExpressions.Regex]::Match($Sortie, '[0-9]+(\.[0-9]+)+')
    if (-not $m.Success) {
        return $null
    }
    return $m.Value
}

function Test-VersionSuffisante {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Vue,

        [Parameter(Mandatory = $true)]
        [string] $Seuil
    )
    $a = $Vue.Split('.')
    $b = $Seuil.Split('.')
    $n = [Math]::Max($a.Count, $b.Count)
    for ($i = 0; $i -lt $n; $i++) {
        $x = 0
        $y = 0
        if ($i -lt $a.Count) { $x = [int] $a[$i] }
        if ($i -lt $b.Count) { $y = [int] $b[$i] }
        if ($x -gt $y) { return $true }
        if ($x -lt $y) { return $false }
    }
    return $true
}

# --- Git for Windows : les dossiers de Git Bash, depuis git.exe ---------------
# git.exe vit sous <Git>\cmd, <Git>\bin ou <Git>\mingw64\bin ; bash.exe sous
# <Git>\bin, tee.exe sous <Git>\usr\bin. Rend les candidats EXISTANTS.
function Get-CandidatsGitBash {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Nom
    )
    $resultat = New-Object 'System.Collections.Generic.List[string]'
    $git = Resolve-ApplicationPath -Name 'git'
    if ([string]::IsNullOrEmpty($git)) {
        return $resultat
    }
    $dossier = [System.IO.Path]::GetDirectoryName($git)
    $racines = New-Object 'System.Collections.Generic.List[string]'
    $parent = [System.IO.Path]::GetDirectoryName($dossier)
    if (-not [string]::IsNullOrEmpty($parent)) {
        $racines.Add($parent)
        $grandParent = [System.IO.Path]::GetDirectoryName($parent)
        if (-not [string]::IsNullOrEmpty($grandParent)) {
            $racines.Add($grandParent)
        }
    }
    foreach ($racine in $racines) {
        foreach ($sous in @('bin', 'usr/bin')) {
            $chemin = $racine
            foreach ($segment in $sous.Split('/')) {
                $chemin = [System.IO.Path]::Combine($chemin, $segment)
            }
            foreach ($nomFichier in @(($Nom + '.exe'), $Nom)) {
                $candidat = [System.IO.Path]::Combine($chemin, $nomFichier)
                if ([System.IO.File]::Exists($candidat)) {
                    $resultat.Add($candidat)
                }
            }
        }
    }
    return $resultat
}

# --- La sonde d'un candidat : present / version / ecarte ----------------------
function Test-Candidat {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Chemin,

        [Parameter(Mandatory = $true)]
        [string] $Contrainte
    )
    if ($Contrainte -eq '-') {
        return [PSCustomObject]@{ Etat = 'present'; Chemin = $Chemin; Vue = '' }
    }
    try {
        $r = Invoke-CapturedProcess -FileName $Chemin -ArgumentValues @('--version')
    }
    catch {
        return $null
    }
    if ($r.ExitCode -ne 0) {
        return $null
    }
    $sortie = $r.Stdout + $r.Stderr
    if ($Contrainte.StartsWith('>=')) {
        $num = Get-NumeroVersion -Sortie $sortie
        if ($null -eq $num) {
            return $null
        }
        if (Test-VersionSuffisante -Vue $num -Seuil $Contrainte.Substring(2)) {
            return [PSCustomObject]@{ Etat = 'present'; Chemin = $Chemin; Vue = $num }
        }
        return [PSCustomObject]@{ Etat = 'version'; Chemin = $Chemin; Vue = $num }
    }
    $premiere = ($sortie.Split("`n")[0]).Trim()
    if ($sortie.Contains($Contrainte)) {
        return [PSCustomObject]@{ Etat = 'present'; Chemin = $Chemin; Vue = $premiere }
    }
    return [PSCustomObject]@{ Etat = 'version'; Chemin = $Chemin; Vue = $premiere }
}

# Find-Outil <jeton> <contrainte> : Etat = present | version | absent, avec le
# chemin et la version vue. Les alternatives sont essayées dans l'ordre ; la
# premiere PRESENTE gagne ; sinon la derniere en mauvaise version ; sinon absent.
function Find-Outil {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Jeton,

        [Parameter(Mandatory = $true)]
        [string] $Contrainte
    )
    $versionBasse = $null
    foreach ($alternative in $Jeton.Split('|')) {
        $candidats = New-Object 'System.Collections.Generic.List[string]'
        if ($alternative -eq 'bash' -or $alternative -eq 'tee') {
            foreach ($c in (Get-CandidatsGitBash -Nom $alternative)) {
                $candidats.Add($c)
            }
        }
        $surPath = Resolve-ApplicationPath -Name $alternative
        if (-not [string]::IsNullOrEmpty($surPath)) {
            $candidats.Add($surPath)
        }
        foreach ($candidat in $candidats) {
            $verdict = Test-Candidat -Chemin $candidat -Contrainte $Contrainte
            if ($null -eq $verdict) {
                continue
            }
            if ($verdict.Etat -eq 'present') {
                return $verdict
            }
            $versionBasse = $verdict
        }
    }
    if ($null -ne $versionBasse) {
        return $versionBasse
    }
    return [PSCustomObject]@{ Etat = 'absent'; Chemin = ''; Vue = '' }
}

# --- LA TABLE DES CANAUX — déclarée (en-tête) --------------------------------
function Get-CanalWinget {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Premier
    )
    switch ($Premier) {
        'git' { return [PSCustomObject]@{ Type = 'winget'; Id = 'Git.Git' } }
        'bash' { return [PSCustomObject]@{ Type = 'winget'; Id = 'Git.Git' } }
        'tee' { return [PSCustomObject]@{ Type = 'winget'; Id = 'Git.Git' } }
        'python3' { return [PSCustomObject]@{ Type = 'winget'; Id = 'Python.Python.3.12' } }
        'pytest' { return [PSCustomObject]@{ Type = 'pip'; Id = $script:PytestPin } }
    }
    return $null
}

function Get-CommandeWinget {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Id
    )
    return @('install', '--id', $Id, '--exact', '--silent', '--accept-package-agreements', '--accept-source-agreements')
}

function Format-Liste {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]] $Jetons
    )
    if ($Jetons.Count -eq 0) {
        return 'aucun'
    }
    return [string]::Join(' ', $Jetons)
}

# --- Le marqueur d'agent (en-tête, étape 0) -----------------------------------
# Rend le NOM du premier marqueur posé, '' sinon ; un marqueur fait de blancs
# vaut ABSENT (IsNullOrWhiteSpace : setup.sh ôte les mêmes blancs ASCII, espace,
# \t \r \n \v \f ; les blancs Unicode ne valent absents qu'ici). Borne :
# COPILOT_CLI est hérité d'un shell lancé depuis Copilot CLI — faux positif
# assumé, le remède est un terminal hors de Copilot CLI.
function Get-MarqueurAgent {
    foreach ($nom in @('CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'AGENTS_HOOK_HOST', 'COPILOT_AGENT_SESSION_ID', 'COPILOT_CLI')) {
        if (-not [string]::IsNullOrWhiteSpace([System.Environment]::GetEnvironmentVariable($nom))) {
            return $nom
        }
    }
    return ''
}

$script:HooksConseilDirect = $false
function Invoke-HooksPath {
    param([string] $Racine)

    $git = Resolve-ApplicationPath -Name 'git'
    if ([string]::IsNullOrEmpty($git)) {
        Write-Dire 'depot Git illisible : hooks non proposes ; configuration inchangee.'
        return
    }
    try {
        $top = Invoke-CapturedProcess -FileName $git -ArgumentValues @('-C', $Racine, 'rev-parse', '--show-toplevel')
        if ($top.ExitCode -ne 0) {
            Write-Dire 'depot Git illisible : hooks non proposes ; configuration inchangee.'
            return
        }
        $racineGit = [System.IO.Path]::GetFullPath($top.Stdout.Trim())
        $comparaison = [System.StringComparison]::Ordinal
        if ([System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT) {
            $comparaison = [System.StringComparison]::OrdinalIgnoreCase
        }
        if (-not [string]::Equals($racineGit, $Racine, $comparaison)) {
            $ecart = Invoke-CapturedProcess -FileName $git -ArgumentValues @('-C', $Racine, 'rev-parse', '--show-cdup')
            if ($ecart.ExitCode -ne 0 -or -not [string]::IsNullOrWhiteSpace($ecart.Stdout)) {
                Write-Dire ('racine Git differente de ' + $Racine + ' (' + $racineGit + ') : hooks non proposes ; configuration inchangee.')
                return
            }
        }
        $hooksKit = [System.IO.Path]::Combine($Racine, '.githooks')
        if (-not [System.IO.Directory]::Exists($hooksKit)) {
            Write-Dire ('.githooks/ absent : hooks non propos' + [char]0xE9 + 's ; configuration inchang' + [char]0xE9 + 'e.')
            return
        }
        $cheminLien = $hooksKit
        $cibleLien = 'in-root'
        for ($n = 0; $n -lt 40; $n++) {
            $itemLien = Get-Item -LiteralPath $cheminLien -Force
            $typeLien = $itemLien.PSObject.Properties['LinkType']
            if ($null -eq $typeLien -or [string]::IsNullOrEmpty([string]$typeLien.Value)) { break }
            $proprieteCible = $itemLien.PSObject.Properties['Target']
            if ($null -eq $proprieteCible) { $cibleLien = ''; break }
            $cibleLien = [string]$proprieteCible.Value
            if ([string]::IsNullOrWhiteSpace($cibleLien)) { break }
            if (-not [System.IO.Path]::IsPathRooted($cibleLien)) {
                $cibleLien = [System.IO.Path]::Combine([System.IO.Path]::GetDirectoryName($cheminLien), $cibleLien)
            }
            $cheminLien = [System.IO.Path]::GetFullPath($cibleLien)
        }
        $racineNorm = $Racine.TrimEnd([char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar))
        if ($n -ge 40 -or [string]::IsNullOrWhiteSpace($cibleLien) -or
            (-not $cheminLien.StartsWith($racineNorm + [System.IO.Path]::DirectorySeparatorChar, $comparaison))) {
            Write-Dire '.githooks/ hors de cette racine : hooks non proposes ; configuration inchangee.'
            return
        }
        $separateurs = [char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
        $relatif = $cheminLien.Substring($racineNorm.Length).TrimStart($separateurs)
        $etape = $racineNorm
        foreach ($segment in $relatif.Split($separateurs, [System.StringSplitOptions]::RemoveEmptyEntries)) {
            $etape = [System.IO.Path]::Combine($etape, $segment)
            $itemSegment = Get-Item -LiteralPath $etape -Force
            if (($itemSegment.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                Write-Dire ('.githooks/ cible avec lien imbriqu' + [char]0xE9 + ' : hooks non propos' + [char]0xE9 + 's ; configuration inchang' + [char]0xE9 + 'e.')
                return
            }
        }
        $config = Invoke-CapturedProcess -FileName $git -ArgumentValues @('-C', $Racine, 'config', '--get', 'core.hooksPath')
        if ($config.ExitCode -ne 0 -and $config.ExitCode -ne 1) {
            Write-Dire 'lecture de core.hooksPath en echec : hooks non proposes ; configuration inchangee.'
            return
        }
        if ($config.ExitCode -eq 0) {
            $valeur = $config.Stdout.Trim()
            $chemin = ''
            try {
                $chemin = $valeur
                if (-not [System.IO.Path]::IsPathRooted($chemin)) {
                    $chemin = [System.IO.Path]::Combine($Racine, $chemin)
                }
                $chemin = [System.IO.Path]::GetFullPath($chemin)
                $chemin = $chemin.TrimEnd([char[]]@([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar))
            }
            catch { $chemin = '' }
            if ([string]::Equals($chemin, $hooksKit, $comparaison)) {
                Write-Dire ('Hooks d' + [char]0xE9 + 'j' + [char]0xE0 + ' activ' + [char]0xE9 + 's dans ce clone ; configuration inchang' + [char]0xE9 + 'e.')
            }
            else {
                Write-Dire ('core.hooksPath deja defini a ' + $valeur + ' : hooks non proposes ; configuration inchangee.')
            }
            return
        }
        $gitPath = Invoke-CapturedProcess -FileName $git -ArgumentValues @('-C', $Racine, 'rev-parse', '--git-path', 'hooks')
        if ($gitPath.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($gitPath.Stdout)) {
            Write-Dire 'chemin des hooks Git illisible : hooks non proposes ; configuration inchangee.'
            return
        }
        $hooks = $gitPath.Stdout.Trim()
        if (-not [System.IO.Path]::IsPathRooted($hooks)) {
            $hooks = [System.IO.Path]::Combine($Racine, $hooks)
        }
        if (-not [System.IO.Directory]::Exists($hooks)) {
            Write-Dire ('inventaire des hooks impossible (' + $hooks + ') : hooks non proposes ; configuration inchangee.')
            return
        }
        $actifs = @(Get-ChildItem -LiteralPath $hooks -Force -ErrorAction Stop | Where-Object { $_.Name -notlike '*.sample' } | ForEach-Object { $_.Name })
        if ($actifs.Count -gt 0) {
            Write-Dire ('hooks actifs dans ' + $hooks + ' : ' + [string]::Join(' ', $actifs) + ' ; hooks non proposes ; configuration inchangee.')
            Write-Dire 'Integrez les hooks existants dans .githooks/ en chainant les noms communs, ou integrez les hooks du kit dans le repertoire actif sans changer core.hooksPath ; si pre-push existe deja, chainez les deux pre-push sans copier par-dessus.'
            return
        }
        $script:HooksConseilDirect = $true
        if ($DryRun) {
            Write-Dire 'hooks non proposes en -DryRun ; configuration inchangee.'
            return
        }
        $marqueurHooks = Get-MarqueurAgent
        if ($marqueurHooks) {
            # Défense en profondeur, injoignable : sortie 7 en amont.
            Write-Dire ('hooks non proposes sous ' + $marqueurHooks + ' ; configuration inchangee.')
            return
        }
        if ([Console]::IsInputRedirected) {
            Write-Dire 'hooks non proposes : entree non interactive ; configuration inchangee.'
            return
        }
        Write-Ligne ('Activer les hooks de ce d' + [char]0xE9 + 'p' + [char]0xF4 + 't (tous ses worktrees li' + [char]0xE9 + 's partagent ce r' + [char]0xE9 + 'glage) dans .githooks ? core.hooksPath remplace les hooks de .git/hooks ; pre-push refuse un push sans tampon de porte vert ; commit-msg refuse certains sujets ; Git ex' + [char]0xE9 + 'cute les hooks de l' + [char]0x2019 + 'arbre courant. [o/N]')
        $reponse = [Console]::ReadLine()
        if ($reponse -cne 'o' -and $reponse -cne 'oui') {
            Write-Dire ('Hooks non activ' + [char]0xE9 + 's dans ce clone ; configuration inchang' + [char]0xE9 + 'e.')
            return
        }
        $ecriture = Invoke-CapturedProcess -FileName $git -ArgumentValues @('-C', $Racine, 'config', '--local', 'core.hooksPath', '.githooks')
        if ($ecriture.ExitCode -eq 0) {
            $script:HooksConseilDirect = $false
            Write-Dire ('Hooks activ' + [char]0xE9 + 's dans ce d' + [char]0xE9 + 'p' + [char]0xF4 + 't (worktrees li' + [char]0xE9 + 's compris) : core.hooksPath=.githooks.')
        }
        else {
            Write-Dire 'ecriture de core.hooksPath en echec ; configuration inchangee.'
        }
    }
    catch {
        Write-Dire ('verification des hooks impossible : ' + $_.Exception.Message + ' ; configuration inchangee.')
    }
}

function Invoke-PiloteFusion {
    param([string] $Racine)

    if ($DryRun) {
        Write-Dire 'pilote de fusion non propose en -DryRun ; rien arme.'
        return
    }
    $marqueurPilote = Get-MarqueurAgent
    if ($marqueurPilote) {
        Write-Dire ('pilote de fusion non propose sous ' + $marqueurPilote + ' ; rien arme.')
        return
    }
    $python = ''
    foreach ($nom in @('python3', 'python', 'py')) {
        $candidat = Resolve-ApplicationPath -Name $nom
        if ([string]::IsNullOrEmpty($candidat)) { continue }
        try {
            $version = Invoke-CapturedProcess -FileName $candidat -ArgumentValues @('-c', 'import sys; sys.exit(sys.version_info < (3, 11))')
            if ($version.ExitCode -eq 0) {
                $python = $candidat
                break
            }
        }
        catch { continue }
    }
    if ([string]::IsNullOrEmpty($python)) {
        Write-Dire 'pilote non propose : python >= 3.11 absent ; rien arme.'
        return
    }
    $pilote = [System.IO.Path]::Combine($Racine, '.agents', 'bin', 'fusion_enregistrement.py')
    try {
        & $python -I -B $pilote --verifier
        if ($LASTEXITCODE -eq 0) {
            Write-Dire 'pilote de fusion deja installe.'
            return
        }
    }
    catch {
        Write-Dire ('verification du pilote impossible : ' + $_.Exception.Message)
    }
    if ([Console]::IsInputRedirected) {
        Write-Dire 'pilote de fusion non propose : entree non interactive ; rien arme.'
        if ($script:HooksConseilDirect) {
            Write-Dire 'sans core.hooksPath -> .githooks, aucune alerte de fusion (git config core.hooksPath .githooks).'
        }
        return
    }
    Write-Ligne 'Installer le pilote de fusion dans ce clone ? [o/N]'
    $reponse = [Console]::ReadLine()
    if ($reponse -cne 'o' -and $reponse -cne 'oui') {
        Write-Dire 'pilote de fusion refuse ; rien arme.'
        if ($script:HooksConseilDirect) {
            Write-Dire 'sans core.hooksPath -> .githooks, aucune alerte de fusion (git config core.hooksPath .githooks).'
        }
        return
    }
    $argumentsPilote = @('-I', '-B', $pilote, '--installer')
    $marqueurKit = [System.IO.Path]::Combine($Racine, '.agents', 'IS_THE_KIT')
    if ([System.IO.File]::Exists($marqueurKit)) {
        $git = Resolve-ApplicationPath -Name 'git'
        if (-not [string]::IsNullOrEmpty($git)) {
            try {
                $branche = (& $git -C $Racine symbolic-ref --quiet --short HEAD 2>$null)
                $codeBranche = $LASTEXITCODE
                & $git -C $Racine show-ref --verify --quiet refs/remotes/origin/develop 2>$null
                if ($codeBranche -eq 0 -and $branche -eq 'develop' -and $LASTEXITCODE -eq 0) {
                    $argumentsPilote += @('--depuis', 'origin/develop')
                }
            }
            catch { }
        }
    }
    try {
        & $python @argumentsPilote
        $codeInstallation = $LASTEXITCODE
        if ($codeInstallation -ne 0) {
            Write-Dire ('installation du pilote de fusion en echec (code ' + $codeInstallation + ').')
        }
        & $python -I -B $pilote --verifier
        if ($LASTEXITCODE -eq 0) {
            Write-Dire 'pilote de fusion verifie.'
        }
        else {
            Write-Dire 'pilote de fusion non verifie ; rien ne garantit son armement.'
        }
    }
    catch {
        Write-Dire ('installation ou verification du pilote impossible : ' + $_.Exception.Message)
    }
}

# --- Déroulé ------------------------------------------------------------------
try {
    # (0) Jamais sous un agent quand le poste va être modifié.
    $marqueurAgent = Get-MarqueurAgent
    if ($marqueurAgent -and (-not $DryRun)) {
        Write-Refus ('a lancer par vous-meme dans un terminal, pas par un agent : ce script installe des paquets sur le poste (' + $marqueurAgent + ' est pose ici).')
        Write-Refus 'Rien n a ete fait. -DryRun reste permis.'
        Write-Refus ('pilote de fusion non propose sous ' + $marqueurAgent + ' ; rien arme.')
        exit 7
    }

    # (1) La plateforme, puis winget.
    $surWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
    $noteOs = 'OSVersion.Platform : ' + [System.Environment]::OSVersion.Platform.ToString()
    $forceOs = [System.Environment]::GetEnvironmentVariable('SETUP_PS1_OS')
    if ((-not $surWindows) -and ($forceOs -eq 'windows')) {
        $surWindows = $true
        $noteOs = 'imposee par SETUP_PS1_OS (banc)'
    }
    if (-not $surWindows) {
        Write-Refus ('ce script est pour Windows (' + $noteOs + '). Sur macOS et Ubuntu : bash core-scripts/setup.sh')
        exit 2
    }
    $winget = Resolve-ApplicationPath -Name 'winget'
    if ([string]::IsNullOrEmpty($winget)) {
        Write-Refus 'winget introuvable dans le PATH. Installez "App Installer" depuis le Microsoft Store (ce script ne telecharge aucun installateur), puis relancez.'
        exit 2
    }

    # L'inventaire.
    $inventaire = $Inventory
    if ([string]::IsNullOrEmpty($inventaire)) {
        if ([string]::IsNullOrEmpty($PSScriptRoot)) {
            Write-Refus 'dossier du script inconnu -- passez -Inventory <tsv>'
            exit 2
        }
        $inventaire = [System.IO.Path]::Combine($PSScriptRoot, 'tool-inventory.tsv')
    }
    if (-not [System.IO.File]::Exists($inventaire)) {
        Write-Refus ('inventaire illisible : ' + $inventaire)
        exit 2
    }
    try {
        $entrees = Read-Inventaire -Chemin $inventaire
    }
    catch {
        Write-Refus ('inventaire illisible : ' + $inventaire + ' : ' + $_.Exception.Message)
        exit 2
    }

    Write-Ligne ('setup -- prerequis du kit (inventaire : ' + $inventaire + ')')
    Write-Ligne ('Plateforme : windows (' + $noteOs + ') -- gestionnaire : winget (' + $winget + ')')
    if ($DryRun) {
        Write-Dire '-DryRun : rien ne sera installe'
    }

    # (2) AVANT : les outils B de la plateforme, sondés.
    $requis = New-Object 'System.Collections.Generic.List[object]'
    foreach ($entree in $entrees) {
        if ($entree.Nature -ne 'outil') { continue }
        if ($entree.Class -ne 'B') { continue }
        if (-not (Test-OsApplique -Cellule $entree.Os)) { continue }
        $requis.Add($entree)
    }
    if ($requis.Count -eq 0) {
        Write-Refus ('aucun outil de classe B pour windows dans ' + $inventaire + ' : rien a installer, rien a verifier')
        exit 2
    }
    $tous = New-Object 'System.Collections.Generic.List[string]'
    foreach ($entree in $requis) {
        $tous.Add($entree.Tool)
    }
    Write-Ligne ('Requis (classe B de l inventaire, windows) : ' + [string]::Join(' ', $tous.ToArray()))

    # La sonde de pytest par module passe par le python retenu.
    function Get-Etats {
        param(
            [Parameter(Mandatory = $true)]
            [object] $Lignes
        )
        $etats = @{}
        $python = ''
        foreach ($entree in $Lignes) {
            $verdict = Find-Outil -Jeton $entree.Tool -Contrainte $entree.Version
            if ($verdict.Etat -eq 'present' -and ($entree.Tool.Split('|')[0] -eq 'python3')) {
                $python = $verdict.Chemin
            }
            $etats[$entree.Tool] = $verdict
        }
        foreach ($entree in $Lignes) {
            if ($entree.Tool.Split('|')[0] -ne 'pytest') { continue }
            if ($etats[$entree.Tool].Etat -ne 'absent') { continue }
            if ([string]::IsNullOrEmpty($python)) { continue }
            try {
                $r = Invoke-CapturedProcess -FileName $python -ArgumentValues @('-m', 'pytest', '--version')
            }
            catch {
                continue
            }
            if ($r.ExitCode -eq 0) {
                $etats[$entree.Tool] = [PSCustomObject]@{ Etat = 'present'; Chemin = ($python + ' -m pytest'); Vue = '' }
            }
        }
        return [PSCustomObject]@{ Etats = $etats; Python = $python }
    }

    $avant = Get-Etats -Lignes $requis
    $dejaLa = New-Object 'System.Collections.Generic.List[string]'
    $aFaire = New-Object 'System.Collections.Generic.List[string]'
    $sansCanal = New-Object 'System.Collections.Generic.List[string]'
    $idsWinget = New-Object 'System.Collections.Generic.List[string]'
    $pipPaquets = New-Object 'System.Collections.Generic.List[string]'
    foreach ($entree in $requis) {
        $verdict = $avant.Etats[$entree.Tool]
        if ($verdict.Etat -eq 'present') {
            $dejaLa.Add($entree.Tool)
            continue
        }
        $aFaire.Add($entree.Tool)
        $libelle = 'absent'
        if ($verdict.Etat -eq 'version') {
            $libelle = 'mauvaise version'
        }
        $canal = Get-CanalWinget -Premier ($entree.Tool.Split('|')[0])
        if ($null -eq $canal) {
            $sansCanal.Add($entree.Tool)
            Write-Ligne ('  ' + $libelle.PadRight(18) + ' ' + $entree.Tool + ' -- aucun canal winget connu de ce script')
            continue
        }
        if ($canal.Type -eq 'winget') {
            Write-Ligne ('  ' + $libelle.PadRight(18) + ' ' + $entree.Tool + ' -- winget : ' + $canal.Id)
            if (-not $idsWinget.Contains($canal.Id)) {
                $idsWinget.Add($canal.Id)
            }
        }
        else {
            Write-Ligne ('  ' + $libelle.PadRight(18) + ' ' + $entree.Tool + ' -- pip : ' + $canal.Id)
            if (-not $pipPaquets.Contains($canal.Id)) {
                $pipPaquets.Add($canal.Id)
            }
        }
    }
    Write-Ligne ('  deja la : ' + (Format-Liste -Jetons $dejaLa.ToArray()))

    function Exit-Bilan {
        param(
            [AllowEmptyCollection()] [string[]] $Installes,
            [AllowEmptyCollection()] [string[]] $DejaLa,
            [AllowEmptyCollection()] [string[]] $Manque,
            [int] $Code
        )
        $racine = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..'))
        Invoke-HooksPath -Racine $racine
        try {
            Invoke-PiloteFusion -Racine $racine
        }
        catch {
            Write-Dire ('pilote de fusion non propose : ' + $_.Exception.Message)
        }
        Write-Ligne ''
        Write-Ligne ($script:Prefixe + ' installes=' + (Format-Liste -Jetons $Installes) + ' deja la=' + (Format-Liste -Jetons $DejaLa) + ' manque encore=' + (Format-Liste -Jetons $Manque) + ' -- exit ' + $Code)
        exit $Code
    }

    # (3) (4) Le plan, et -DryRun.
    if ($aFaire.Count -eq 0) {
        Write-Dire 'tout est la : rien a installer'
        Exit-Bilan -Installes @() -DejaLa $dejaLa.ToArray() -Manque @() -Code 0
    }

    $commandesWinget = New-Object 'System.Collections.Generic.List[string]'
    foreach ($id in $idsWinget) {
        $commandesWinget.Add('winget ' + [string]::Join(' ', (Get-CommandeWinget -Id $id)))
    }
    $commandePip = ''
    if ($pipPaquets.Count -gt 0) {
        $pythonPourPip = $avant.Python
        if ([string]::IsNullOrEmpty($pythonPourPip)) {
            $pythonPourPip = 'python'
        }
        $commandePip = $pythonPourPip + ' -m pip install --user ' + [string]::Join(' ', $pipPaquets.ToArray())
    }

    if ($DryRun) {
        foreach ($commande in $commandesWinget) {
            Write-Dire ('-DryRun : lancerait : ' + $commande)
        }
        if ($commandePip.Length -gt 0) {
            Write-Dire ('-DryRun : lancerait : ' + $commandePip)
        }
        if ($sansCanal.Count -gt 0) {
            Write-Dire ('-DryRun : sans canal connu, a installer vous-meme : ' + [string]::Join(' ', $sansCanal.ToArray()))
        }
        Exit-Bilan -Installes @() -DejaLa $dejaLa.ToArray() -Manque $aFaire.ToArray() -Code 1
    }

    # L'installation : une commande winget par identifiant, affichée avant.
    foreach ($id in $idsWinget) {
        $arguments = Get-CommandeWinget -Id $id
        Write-Dire ('lance : winget ' + [string]::Join(' ', $arguments))
        & $winget @arguments
        $codeWinget = $LASTEXITCODE
        if ($codeWinget -ne 0) {
            Write-Refus ('winget a rendu ' + $codeWinget + ' pour ' + $id + ' -- voir ci-dessus')
        }
    }
    if ($commandePip.Length -gt 0) {
        # Python re-sonde APRES winget : s'il vient d'etre pose et que cette
        # session le voit deja, pip tourne tout de suite ; sinon la commande est
        # rendue pour un nouveau terminal.
        $pythonPip = $avant.Python
        if ([string]::IsNullOrEmpty($pythonPip)) {
            $pythonPip = (Get-Etats -Lignes $requis).Python
        }
        if ([string]::IsNullOrEmpty($pythonPip)) {
            Write-Dire 'pip : Python n est pas visible de cette session -- pytest sera a poser dans un nouveau terminal (commande ci-dessous)'
        }
        else {
            $commandePip = $pythonPip + ' -m pip install --user ' + [string]::Join(' ', $pipPaquets.ToArray())
            Write-Dire ('lance : ' + $commandePip)
            $argumentsPip = @('-m', 'pip', 'install', '--user') + $pipPaquets.ToArray()
            & $pythonPip @argumentsPip
            $codePip = $LASTEXITCODE
            if ($codePip -ne 0) {
                Write-Refus ('pip a rendu ' + $codePip + ' -- voir ci-dessus')
            }
        }
    }

    # (5) APRÈS : re-sonde, trois listes, une ligne de résumé.
    $apres = Get-Etats -Lignes $requis
    $installes = New-Object 'System.Collections.Generic.List[string]'
    $manque = New-Object 'System.Collections.Generic.List[string]'
    Write-Ligne ''
    Write-Ligne 'Apres installation'
    foreach ($jeton in $aFaire) {
        $verdict = $apres.Etats[$jeton]
        if ($verdict.Etat -eq 'present') {
            $installes.Add($jeton)
            Write-Ligne ('  ' + 'installe'.PadRight(18) + ' ' + $jeton + ' -- ' + $verdict.Chemin)
            continue
        }
        $manque.Add($jeton)
        if ($verdict.Etat -eq 'version') {
            Write-Ligne ('  ' + 'manque encore'.PadRight(18) + ' ' + $jeton + ' -- version ' + $verdict.Vue + ' vue (' + $verdict.Chemin + ')')
        }
        else {
            Write-Ligne ('  ' + 'manque encore'.PadRight(18) + ' ' + $jeton + ' -- absent')
        }
        $canal = Get-CanalWinget -Premier ($jeton.Split('|')[0])
        if ($null -eq $canal) {
            Write-Ligne '    a installer vous-meme : aucun canal winget connu de ce script'
        }
        elseif ($canal.Type -eq 'winget') {
            Write-Ligne ('    a taper : winget ' + [string]::Join(' ', (Get-CommandeWinget -Id $canal.Id)))
            Write-Ligne '    note : winget ecrit le PATH systeme ; cette session ne le voit pas toujours -- ouvrez un nouveau terminal et relancez'
        }
        else {
            Write-Ligne ('    a taper, dans un NOUVEAU terminal : python -m pip install --user ' + $canal.Id)
        }
    }
    Write-Ligne ('  ' + 'deja la'.PadRight(18) + ' ' + (Format-Liste -Jetons $dejaLa.ToArray()))

    $code = 0
    if ($manque.Count -gt 0) {
        $code = 1
    }
    Exit-Bilan -Installes $installes.ToArray() -DejaLa $dejaLa.ToArray() -Manque $manque.ToArray() -Code $code
}
catch {
    Write-Refus ('erreur inattendue : ' + $_.Exception.Message)
    exit 1
}
