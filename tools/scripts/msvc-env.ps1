# ==============================================================================
# MSVC + Windows SDK environment for the Tauri (Rust) build
# ==============================================================================
#
# Dot-source it, do not call it:
#
#     . "$PSScriptRoot\tools\scripts\msvc-env.ps1"
#
# ## Why this is a file and not two copies
#
# It was two copies -- `build_prototype.ps1` and `start_desktop.ps1` carried the same ~35 lines,
# identical but for their comments. One is the installer path and one is the dev path, so a
# toolchain fix applied to whichever the author happened to be running would leave the other
# broken, and nothing would say so until someone used it.
#
# ## What was wrong with those copies
#
# They resolved the toolchain like this:
#
#     $msvcRoot = if (Test-Path "$PSScriptRoot\msvc\...") { ... } else { "$env:USERPROFILE\msvc" }
#
# -- so on any machine without a portable MSVC unpacked under the repo or the home directory,
# `$msvcRoot` became a path that does not exist. `$msvcVer` then fell back to a hardcoded
# "14.51.36231", INCLUDE and LIB were **overwritten** with directories that were not there, and
# the script printed *"MSVC Environment injected."* and carried on.
#
# Three separate faults, all silent:
#
#   1. **A real Visual Studio install was never consulted.** `vswhere.exe` is the supported
#      discovery mechanism and shipped on the machine this was first run on.
#   2. **The version fallbacks were guesses that reported success.** A hardcoded MSVC and SDK
#      version that happen to be absent produce the same "injected" message as ones that are
#      present.
#   3. **`Select-Object -First 1` over `Get-ChildItem` picks the OLDEST version**, because the
#      listing is ascending. Where several toolchains were installed it silently chose the
#      earliest one.
#
# It usually built anyway, which is why it survived: modern `rustc` locates the MSVC linker by
# itself for the `*-pc-windows-msvc` target. So the block was mostly decorative on a healthy
# machine and actively misleading on an unhealthy one -- it could only ever fail at the link step,
# minutes into a release build, with an error about `link.exe` rather than about this script.
#
# ## What it does now
#
# Search order deliberately preserves what already worked, and only adds the case that did not:
#
#   1. `<repo>\msvc`            -- a portable toolchain committed beside the project
#   2. `%USERPROFILE%\msvc`     -- a portable toolchain unpacked once per machine
#   3. `vswhere` -> Visual Studio / Build Tools  (NEW -- this is the case that used to fail)
#
# A machine that builds today takes the same branch it takes today. Nothing is exported until
# `cl.exe` and `link.exe` have actually been found, and if no toolchain resolves this **throws**
# rather than exporting paths that do not exist.

$ErrorActionPreference = "Stop"

function Get-HighestVersionDir {
    <#
        .SYNOPSIS
        Newest versioned subdirectory, or $null.

        .DESCRIPTION
        Sorts DESCENDING on purpose. The code this replaces used `Select-Object -First 1` on an
        ascending listing, so with 14.38 and 14.51 installed it chose 14.38 -- an old toolchain,
        picked silently, on the machines most likely to have several.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [string]$Filter = "*"
    )
    if (-not (Test-Path $Path)) { return $null }
    $dirs = Get-ChildItem -Path $Path -Filter $Filter -Directory -ErrorAction SilentlyContinue
    if (-not $dirs) { return $null }
    return ($dirs | Sort-Object -Property Name -Descending | Select-Object -First 1)
}

function Find-VisualStudioRoot {
    <#
        .SYNOPSIS
        Installation path of the newest VS/Build Tools carrying the x64 C++ toolset, or $null.
    #>
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { return $null }

    # -products * so Build Tools counts, not just Community/Professional/Enterprise. A CI or
    # build box typically has only Build Tools, which the -products default excludes.
    $found = & $vswhere -latest -products * `
        -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
        -property installationPath
    if ($LASTEXITCODE -ne 0) { return $null }

    $path = ($found | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($path)) { return $null }
    if (-not (Test-Path $path)) { return $null }
    return $path
}

function Resolve-MsvcToolchain {
    <#
        .SYNOPSIS
        Locate an MSVC toolset whose compiler and linker are really on disk.

        .OUTPUTS
        Hashtable with Bin, Include, Lib, Label -- or $null when nothing usable was found.
    #>
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $candidates = @(
        @{ Root = (Join-Path $RepoRoot "msvc");          Label = "portable (repo)" },
        @{ Root = (Join-Path $env:USERPROFILE "msvc");   Label = "portable (user profile)" }
    )

    $vsRoot = Find-VisualStudioRoot
    if ($vsRoot) {
        $candidates += @{ Root = $vsRoot; Label = "Visual Studio ($vsRoot)" }
    }

    foreach ($candidate in $candidates) {
        $root = $candidate.Root
        $toolsDir = Join-Path $root "VC\Tools\MSVC"
        $verDir = Get-HighestVersionDir -Path $toolsDir
        if (-not $verDir) { continue }

        $bin = Join-Path $verDir.FullName "bin\Hostx64\x64"
        # The whole point of the rewrite: prove the tools exist before exporting anything.
        if (-not (Test-Path (Join-Path $bin "cl.exe")))   { continue }
        if (-not (Test-Path (Join-Path $bin "link.exe"))) { continue }

        # The SDK may sit beside a portable toolchain, otherwise it is the system one.
        $sdkRoot = Join-Path $root "Windows Kits\10"
        if (-not (Test-Path $sdkRoot)) {
            $sdkRoot = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10"
        }
        # Versioned from Include, not bin: bin can carry a version whose headers were never
        # installed, and headers are what INCLUDE is for.
        $sdkVerDir = Get-HighestVersionDir -Path (Join-Path $sdkRoot "Include") -Filter "10.*"
        if (-not $sdkVerDir) { continue }
        $sdkVer = $sdkVerDir.Name
        if (-not (Test-Path (Join-Path $sdkRoot "Include\$sdkVer\ucrt"))) { continue }

        return @{
            Label = $candidate.Label
            Bin   = @(
                $bin,
                (Join-Path $sdkRoot "bin\$sdkVer\x64")
            )
            Include = @(
                (Join-Path $verDir.FullName "include"),
                (Join-Path $sdkRoot "Include\$sdkVer\ucrt"),
                (Join-Path $sdkRoot "Include\$sdkVer\shared"),
                (Join-Path $sdkRoot "Include\$sdkVer\um"),
                (Join-Path $sdkRoot "Include\$sdkVer\winrt"),
                (Join-Path $sdkRoot "Include\$sdkVer\cppwinrt")
            )
            Lib = @(
                (Join-Path $verDir.FullName "lib\x64"),
                (Join-Path $sdkRoot "Lib\$sdkVer\ucrt\x64"),
                (Join-Path $sdkRoot "Lib\$sdkVer\um\x64")
            )
        }
    }

    return $null
}

# ── apply ─────────────────────────────────────────────────────────────────────────────────
# $PSScriptRoot here is tools/scripts, so the repo root is two levels up. Resolved rather than
# assumed from the caller's location, because both callers sit at the repo root and a third one
# elsewhere would otherwise silently search the wrong tree.
$__repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$__toolchain = Resolve-MsvcToolchain -RepoRoot $__repoRoot

if (-not $__toolchain) {
    $__vsHint = Find-VisualStudioRoot
    $__detail = if ($__vsHint) {
        "vswhere found '$__vsHint' but it has no usable VC\Tools\MSVC\<ver>\bin\Hostx64\x64\link.exe, or no Windows SDK headers."
    } else {
        "vswhere reported no install with the x64 C++ toolset (Microsoft.VisualStudio.Component.VC.Tools.x86.x64)."
    }
    throw @"
No usable MSVC toolchain found. The Rust build needs cl.exe, link.exe and the Windows SDK headers.

Searched, in order:
  1. $__repoRoot\msvc
  2. $env:USERPROFILE\msvc
  3. Visual Studio / Build Tools via vswhere

$__detail

Install the "Desktop development with C++" workload (or Build Tools with the x64 C++ toolset and
a Windows 10/11 SDK), or unpack a portable toolchain to one of the first two paths.

This now fails here instead of exporting paths that do not exist -- which is what it used to do,
reporting "MSVC Environment injected." and then failing minutes later at the link step with an
error about link.exe rather than about this script.
"@
}

$env:Path = (($__toolchain.Bin) -join ";") + ";" + $env:Path
$env:INCLUDE = ($__toolchain.Include) -join ";"
$env:LIB = ($__toolchain.Lib) -join ";"

Write-Host "MSVC toolchain: $($__toolchain.Label)" -ForegroundColor Green
Write-Host "  cl/link: $($__toolchain.Bin[0])" -ForegroundColor DarkGray
