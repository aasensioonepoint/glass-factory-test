[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('module', 'bash')]
    [string] $Mode,

    [Parameter(Mandatory = $true, Position = 1)]
    [string] $RepoRoot,

    [Parameter(Mandatory = $true, Position = 2)]
    [string] $Target,

    [Parameter(Position = 3, ValueFromRemainingArguments = $true)]
    [AllowEmptyCollection()]
    [AllowEmptyString()]
    [string[]] $HookArguments = @()
)

# Resolve Python independently of hook stdin, then launch exactly one child.
# ProcessStartInfo avoids PowerShell's version-dependent native argument parser.
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

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

function New-NativeStartInfo {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FileName,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [AllowEmptyString()]
        [string[]] $ArgumentValues,

        [Parameter(Mandatory = $true)]
        [string] $WorkingDirectory,

        [switch] $Capture
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FileName
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true

    $argumentListProperty = $startInfo.PSObject.Properties['ArgumentList']
    if ($null -ne $argumentListProperty) {
        foreach ($argumentValue in $ArgumentValues) {
            [void] $startInfo.ArgumentList.Add($argumentValue)
        }
    }
    else {
        $startInfo.Arguments = Join-NativeArguments -Values $ArgumentValues
    }

    if ($Capture) {
        $startInfo.RedirectStandardInput = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
    }

    return $startInfo
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

    $process = New-Object System.Diagnostics.Process
    try {
        $process.StartInfo = New-NativeStartInfo `
            -FileName $FileName `
            -ArgumentValues $ArgumentValues `
            -WorkingDirectory $WorkingDirectory `
            -Capture
        if (-not $process.Start()) {
            throw "could not start $FileName"
        }

        # The resolver probe must never consume the hook payload.
        $process.StandardInput.Close()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $capturedExitCode = $process.ExitCode
        $capturedStdout = $stdoutTask.GetAwaiter().GetResult()
        [void] $stderrTask.GetAwaiter().GetResult()

        return [PSCustomObject]@{
            ExitCode = $capturedExitCode
            Stdout   = $capturedStdout
        }
    }
    finally {
        $process.Dispose()
    }
}

function Invoke-InheritedProcess {
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

    $process = New-Object System.Diagnostics.Process
    try {
        $process.StartInfo = New-NativeStartInfo `
            -FileName $FileName `
            -ArgumentValues $ArgumentValues `
            -WorkingDirectory $WorkingDirectory
        if (-not $process.Start()) {
            throw "could not start $FileName"
        }
        $process.WaitForExit()
        return $process.ExitCode
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

    $probeCode = 'import sys; sys.exit(1) if sys.version_info[0] != 3 else None; sys.stdout.write(sys.executable)'
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

$runningOnWindows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
$callerDirectory = (Get-Location).ProviderPath
$resolvedRoot = [System.IO.Path]::GetFullPath($RepoRoot)
if (-not [System.IO.Directory]::Exists($resolvedRoot)) {
    [Console]::Error.WriteLine('pyrun: repository root not found')
    exit 2
}
if ([System.IO.Path]::IsPathRooted($Target)) {
    [Console]::Error.WriteLine('pyrun: target must be repository-relative')
    exit 2
}

$resolvedTarget = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($resolvedRoot, $Target))
$pathComparison = [System.StringComparison]::Ordinal
if ($runningOnWindows) {
    $pathComparison = [System.StringComparison]::OrdinalIgnoreCase
}
$separatorChars = [char[]] @(
    [System.IO.Path]::DirectorySeparatorChar,
    [System.IO.Path]::AltDirectorySeparatorChar
)
$rootPrefix = $resolvedRoot.TrimEnd($separatorChars) + [System.IO.Path]::DirectorySeparatorChar
if (-not $resolvedTarget.StartsWith($rootPrefix, $pathComparison)) {
    [Console]::Error.WriteLine('pyrun: target escapes repository root')
    exit 2
}
if (-not [System.IO.File]::Exists($resolvedTarget)) {
    [Console]::Error.WriteLine('pyrun: target not found')
    exit 2
}

if ($Mode -eq 'module') {
    if ([System.IO.Path]::GetExtension($resolvedTarget) -ne '.py') {
        [Console]::Error.WriteLine('pyrun: module target must be a .py file')
        exit 2
    }

    $moduleCode = 'import os,runpy,sys; p=sys.argv[1]; sys.path.insert(0,os.path.dirname(p)); sys.argv=[p]+sys.argv[2:]; runpy.run_module(os.path.splitext(os.path.basename(p))[0],run_name="__main__")'
    [string[]] $childArguments = @('-c', $moduleCode, $resolvedTarget)
}
else {
    if ([System.IO.Path]::GetExtension($resolvedTarget) -ne '.sh') {
        [Console]::Error.WriteLine('pyrun: bash target must be a .sh file')
        exit 2
    }

    # Keep the Python subprocess bridge; only the Bash child changes cwd.
    $bashCode = 'import subprocess,sys; sys.exit(subprocess.run(["bash",sys.argv[2]]+sys.argv[3:],cwd=sys.argv[1]).returncode)'
    [string[]] $childArguments = @('-c', $bashCode, $resolvedRoot, $resolvedTarget)
}

# Preserve the caller cwd during discovery and Python execution in both modes.
# sys.executable retains the venv launcher path; never dereference its symlink.
$pythonPath = Resolve-Python3 -WorkingDirectory $callerDirectory -RunningOnWindows $runningOnWindows
if ([string]::IsNullOrEmpty($pythonPath)) {
    [Console]::Error.WriteLine('PYTHON 3 NOT FOUND: tried python3, python, and Windows py -3.')
    exit 127
}
foreach ($hookArgument in $HookArguments) {
    $childArguments += $hookArgument
}
$env:PYTHONDONTWRITEBYTECODE = '1'
$childExitCode = Invoke-InheritedProcess `
    -FileName $pythonPath `
    -ArgumentValues $childArguments `
    -WorkingDirectory $callerDirectory
exit $childExitCode
