#Requires -Version 5.1
<#
.SYNOPSIS
    slang-skills installer for Windows (PowerShell).
.DESCRIPTION
    Interactive installer for Slang Claude Code skills. Native Windows port
    of install.sh. Writes a shared manifest (.slang-skills-manifest) that
    is compatible with the bash installer.

    Default install dir is %USERPROFILE%\.claude\skills.

    Symlinks require Developer Mode (Windows 10 1703+) OR an elevated shell.
    If neither is available, the installer auto-falls-back to copy mode.
.EXAMPLE
    .\install.ps1
.EXAMPLE
    .\install.ps1 -Prefix "jv-"
.EXAMPLE
    .\install.ps1 -NonInteractive -Skills "slang-build,slang-run-tests"
.EXAMPLE
    .\install.ps1 -Status
.EXAMPLE
    .\install.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [string]$Prefix = "",
    [switch]$Copy,
    [string]$InstallDir = "",
    [switch]$Uninstall,
    [switch]$Status,
    [switch]$NonInteractive,
    [string]$Skills = "",
    [switch]$DryRun,
    [switch]$Help
)

$ErrorActionPreference = 'Stop'

# --- Constants --------------------------------------------------------------

$script:Version       = "1.0.0"
$script:ManifestFile  = ".slang-skills-manifest"
$script:ScriptDir     = $PSScriptRoot
$script:SkillsSrcDir  = Join-Path $ScriptDir "skills"
$script:ESC           = [char]27

# Default install dir: %USERPROFILE%\.claude\skills
if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:USERPROFILE ".claude\skills"
}
elseif ($InstallDir.StartsWith("~")) {
    $tail = $InstallDir.Substring(1).TrimStart('\', '/')
    $InstallDir = if ($tail) { Join-Path $env:USERPROFILE $tail } else { $env:USERPROFILE }
}

# Dependency map (skill -> list of required skills)
$script:Dependencies = @{
    'slang-fix-bug'          = @('slang-investigate', 'slang-build', 'slang-run-tests', 'slang-write-test')
    'slang-analyze-coverage' = @('slang-write-test')
    'slang-test-feature'     = @('slang-build', 'slang-run-tests', 'slang-write-test', 'slang-create-issue')
    'slang-review-pr'        = @('slang-build')
    'slang-investigate'      = @('slang-build', 'slang-run-tests')
}

# Runtime state
$script:SupportsRawInput = ($Host.Name -ne 'Windows PowerShell ISE Host') -and $Host.UI.RawUI
$script:CopyMode         = [bool]$Copy
$script:SymlinkSupported = $true

# Parallel-array skill state (discovered from disk)
$script:SkillNames    = @()
$script:SkillDescs    = @()
$script:SkillDirs     = @()
$script:SkillSelected = @()

# --- Help / Usage -----------------------------------------------------------

function Show-Usage {
    @"
slang-skills installer v$Version (PowerShell)

Usage: .\install.ps1 [OPTIONS]

Options:
  -Prefix PREFIX       Add a name prefix to skills (e.g., "jv-")
                       Implies copy mode (cannot prefix symlinks)
  -Copy                Force copy mode instead of symlink
  -InstallDir DIR      Install to DIR (default: %USERPROFILE%\.claude\skills)
  -Uninstall           Remove skills installed by this script
  -Status              List skills installed by this script and exit
  -NonInteractive      Skip interactive UI, install all skills
  -Skills LIST         Comma-separated skill names (with -NonInteractive)
  -DryRun              Show what would happen without making changes
  -Help                Show this help message

Examples:
  .\install.ps1                                        # Interactive
  .\install.ps1 -Prefix "jv-"                          # Install all with prefix
  .\install.ps1 -NonInteractive                        # Install all, no UI
  .\install.ps1 -NonInteractive -Skills "slang-build,slang-run-tests"
  .\install.ps1 -Uninstall                             # Remove installed skills
  .\install.ps1 -Status                                # Show what's installed

Notes:
  - Symlinks require Developer Mode or an elevated (Admin) PowerShell.
  - Without symlink support the installer falls back to copy mode.
  - Manifest format is interoperable with the bash installer.
"@ | Write-Host
}

# --- Color helper -----------------------------------------------------------

function Write-Color {
    param(
        [string]$Color,
        [string]$Text,
        [switch]$NoNewline
    )
    $codes = @{
        red    = 31
        green  = 32
        yellow = 33
        cyan   = 36
        bold   = 1
        dim    = 2
    }
    if ($codes.ContainsKey($Color)) {
        $body = "$ESC[$($codes[$Color])m$Text$ESC[0m"
    } else {
        $body = $Text
    }
    if ($NoNewline) {
        Write-Host $body -NoNewline
    } else {
        Write-Host $body
    }
}

# --- Skill discovery --------------------------------------------------------

function Get-Description {
    param([string]$SkillMdPath)
    # Extract 'description:' from YAML frontmatter, strip after first period-space.
    $inFront = $false
    $opened = 0
    foreach ($line in Get-Content -LiteralPath $SkillMdPath -ErrorAction SilentlyContinue) {
        if ($line -match '^---\s*$') {
            $opened++
            $inFront = ($opened -eq 1)
            if ($opened -ge 2) { break }
            continue
        }
        if ($inFront -and $line -match '^description:\s*(.+)$') {
            $d = $matches[1].Trim()
            $d = $d -replace '\.\s.*$', ''
            return $d
        }
    }
    return "(no description)"
}

function Find-Skills {
    if (-not (Test-Path -LiteralPath $SkillsSrcDir -PathType Container)) {
        Write-Color red "Error: Skills source directory not found: $SkillsSrcDir"
        exit 1
    }

    $dirs = Get-ChildItem -LiteralPath $SkillsSrcDir -Directory | Sort-Object Name
    foreach ($d in $dirs) {
        $md = Join-Path $d.FullName "SKILL.md"
        if (-not (Test-Path -LiteralPath $md -PathType Leaf)) { continue }

        $script:SkillNames    += $d.Name
        $script:SkillDescs    += Get-Description $md
        $script:SkillDirs     += $d.FullName
        $script:SkillSelected += 1
    }

    if ($script:SkillNames.Count -eq 0) {
        Write-Color red "Error: No skills found in $SkillsSrcDir"
        exit 1
    }

    if (-not [string]::IsNullOrWhiteSpace($Skills)) {
        $want = $Skills -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
        for ($i = 0; $i -lt $script:SkillNames.Count; $i++) {
            $script:SkillSelected[$i] = if ($want -contains $script:SkillNames[$i]) { 1 } else { 0 }
        }
    }
}

# --- Dependency checking ----------------------------------------------------

function Get-SkillDeps {
    param([string]$Name)
    if ($script:Dependencies.ContainsKey($Name)) { return $script:Dependencies[$Name] }
    return @()
}

function Test-IsSelected {
    param([string]$Name)
    for ($i = 0; $i -lt $script:SkillNames.Count; $i++) {
        if ($script:SkillNames[$i] -eq $Name -and $script:SkillSelected[$i] -eq 1) {
            return $true
        }
    }
    return $false
}

function Test-DeselectImpact {
    param([string]$Deselected)
    $out = @()
    for ($i = 0; $i -lt $script:SkillNames.Count; $i++) {
        if ($script:SkillSelected[$i] -eq 1) {
            $deps = Get-SkillDeps $script:SkillNames[$i]
            if ($deps -contains $Deselected) {
                $out += "$($script:SkillNames[$i]) depends on $Deselected"
            }
        }
    }
    return ,$out
}

function Test-AllDependencies {
    $warnings = @()
    for ($i = 0; $i -lt $script:SkillNames.Count; $i++) {
        if ($script:SkillSelected[$i] -eq 1) {
            foreach ($dep in (Get-SkillDeps $script:SkillNames[$i])) {
                if (-not (Test-IsSelected $dep)) {
                    $warnings += "$($script:SkillNames[$i]) depends on $dep (not selected)"
                }
            }
        }
    }
    if ($warnings.Count -eq 0) { return }

    Write-Color yellow "Warning: unresolved skill dependencies:"
    foreach ($w in $warnings) { Write-Host "  $w" }
    Write-Host ""

    if ($NonInteractive) {
        Write-Host "Continuing anyway (non-interactive mode)."
        return
    }
    $reply = Read-Host "Install anyway? [Y/n]"
    if ($reply -match '^[Nn]') {
        Write-Host "Aborted."
        exit 0
    }
}

# --- Interactive TUI --------------------------------------------------------

$script:CursorPos   = 0
$script:UiLines     = 0
$script:WarningMsg  = ""
$script:WarningTtl  = 0

function Hide-Cursor  { try { [Console]::CursorVisible = $false } catch {} }
function Show-Cursor  { try { [Console]::CursorVisible = $true  } catch {} }

function Read-MenuKey {
    # Returns one of: UP, DOWN, SPACE, ENTER, ESC, QUIT, ALL, NONE, or "" for ignored keys.
    $k = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
    switch ($k.VirtualKeyCode) {
        38 { return 'UP' }
        40 { return 'DOWN' }
        32 { return 'SPACE' }
        13 { return 'ENTER' }
        27 { return 'ESC' }
    }
    switch -Regex ([string]$k.Character) {
        '^[qQ]$' { return 'QUIT' }
        '^[aA]$' { return 'ALL' }
        '^[nN]$' { return 'NONE' }
    }
    return ''
}

function Write-Menu {
    if ($script:UiLines -gt 0) {
        Write-Host "$ESC[$($script:UiLines)A`r" -NoNewline
    }

    $lines    = 0
    $selected = 0
    $total    = $script:SkillNames.Count

    for ($i = 0; $i -lt $total; $i++) {
        $mark = ' '
        if ($script:SkillSelected[$i] -eq 1) { $mark = 'x'; $selected++ }

        $reverse = ''
        $reset   = ''
        if ($i -eq $script:CursorPos) {
            $reverse = "$ESC[7m"
            $reset   = "$ESC[0m"
        }

        $desc = $script:SkillDescs[$i]
        if ($desc.Length -gt 60) { $desc = $desc.Substring(0, 57) + '...' }

        $name = $script:SkillNames[$i].PadRight(28)
        Write-Host ("{0}  [{1}] {2} {3}{4}{5}" -f $reverse, $mark, $name, $desc, "$ESC[K", $reset)
        $lines++
    }

    Write-Host "$ESC[K"
    Write-Host ("  {0}/{1} selected$ESC[K" -f $selected, $total)
    $lines += 2

    if ($script:WarningMsg -and $script:WarningTtl -gt 0) {
        Write-Host "$ESC[33m  $($script:WarningMsg)$ESC[0m$ESC[K"
        $script:WarningTtl--
    } else {
        $script:WarningMsg = ""
        Write-Host "$ESC[K"
    }
    $lines++

    Write-Host "$ESC[K"
    $help =
        "  $ESC[2m[Space]$ESC[0m Toggle  " +
        "$ESC[2m[A]$ESC[0m All  " +
        "$ESC[2m[N]$ESC[0m None  " +
        "$ESC[2m[Enter]$ESC[0m Confirm  " +
        "$ESC[2m[Q]$ESC[0m Quit$ESC[K"
    Write-Host $help
    $lines += 2

    $script:UiLines = $lines
}

function Invoke-InteractiveSelect {
    $total = $script:SkillNames.Count

    Hide-Cursor
    try {
        Write-Host ""
        Write-Color bold "  slang-skills installer"
        Write-Host ""
        Write-Host "  Select skills to install:"
        Write-Host ""

        Write-Menu

        while ($true) {
            $key = Read-MenuKey
            switch ($key) {
                'UP'    { if ($script:CursorPos -gt 0)          { $script:CursorPos-- } }
                'DOWN'  { if ($script:CursorPos -lt ($total-1)) { $script:CursorPos++ } }
                'SPACE' {
                    $i = $script:CursorPos
                    if ($script:SkillSelected[$i] -eq 1) {
                        $impact = Test-DeselectImpact $script:SkillNames[$i]
                        if ($impact.Count -gt 0) {
                            $script:WarningMsg = "Warning: " + $impact[0]
                            $script:WarningTtl = 3
                        }
                        $script:SkillSelected[$i] = 0
                    } else {
                        $script:SkillSelected[$i] = 1
                    }
                }
                'ALL'   { for ($i = 0; $i -lt $total; $i++) { $script:SkillSelected[$i] = 1 } }
                'NONE'  { for ($i = 0; $i -lt $total; $i++) { $script:SkillSelected[$i] = 0 } }
                'ENTER' {
                    $any = $false
                    for ($i = 0; $i -lt $total; $i++) {
                        if ($script:SkillSelected[$i] -eq 1) { $any = $true; break }
                    }
                    if (-not $any) {
                        $script:WarningMsg = "No skills selected. Use [A] to select all or [Q] to quit."
                        $script:WarningTtl = 3
                    } else {
                        Write-Menu
                        return
                    }
                }
                { $_ -in 'QUIT','ESC' } {
                    Show-Cursor
                    Write-Host ""
                    Write-Host "  Aborted."
                    exit 0
                }
            }
            Write-Menu
        }
    } finally {
        Show-Cursor
    }
}

function Show-NonInteractiveList {
    Write-Host ""
    Write-Host "Skills available for installation:"
    Write-Host ""
    for ($i = 0; $i -lt $script:SkillNames.Count; $i++) {
        $status = if ($script:SkillSelected[$i] -eq 1) { '[x]' } else { '[ ]' }
        Write-Host ("  {0} {1} -- {2}" -f $status, $script:SkillNames[$i], $script:SkillDescs[$i])
    }
    Write-Host ""
}

# --- Symlink support detection ---------------------------------------------

function Test-SymlinkSupport {
    if ($script:CopyMode) { return }

    $probeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("slang-skills-probe-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $probeDir -Force | Out-Null
    $src  = Join-Path $probeDir "src.txt"
    $link = Join-Path $probeDir "link.txt"
    Set-Content -LiteralPath $src -Value "probe" -NoNewline

    try {
        New-Item -ItemType SymbolicLink -Path $link -Target $src -ErrorAction Stop | Out-Null
        $script:SymlinkSupported = $true
    } catch {
        $script:SymlinkSupported = $false
        Write-Color yellow "Warning: Symlinks not supported in this shell."
        Write-Host "  Enable Developer Mode (Windows Settings -> Privacy & security -> For developers)"
        Write-Host "  or re-run this script in an elevated (Administrator) PowerShell."
        Write-Host "  Falling back to copy mode."
        $script:CopyMode = $true
    } finally {
        Remove-Item -LiteralPath $probeDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# --- Symlink helpers --------------------------------------------------------

function Test-IsSymlink {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return $false }
    return (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0)
}

function Get-SymlinkTarget {
    param([string]$Path)
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $item) { return $null }
    $t = $item.Target
    if ($null -eq $t) { return $null }
    if ($t -is [System.Array]) { return [string]$t[0] }
    return [string]$t
}

# --- Install ----------------------------------------------------------------

function Install-SkillSymlink {
    param([string]$Name)
    $src  = Join-Path $SkillsSrcDir (Join-Path $Name "SKILL.md")
    $dest = Join-Path $InstallDir (Join-Path $Name "SKILL.md")
    $destDir = Split-Path $dest -Parent

    if ($DryRun) {
        Write-Host "  [dry-run] mkdir $destDir"
        Write-Host "  [dry-run] symlink $dest -> $src"
        return
    }

    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Force }
    New-Item -ItemType SymbolicLink -Path $dest -Target $src -ErrorAction Stop | Out-Null
}

function Install-SkillCopy {
    param([string]$Name)
    $destName = "$Prefix$Name"
    $src  = Join-Path $SkillsSrcDir (Join-Path $Name "SKILL.md")
    $dest = Join-Path $InstallDir (Join-Path $destName "SKILL.md")
    $destDir = Split-Path $dest -Parent

    if ($DryRun) {
        Write-Host "  [dry-run] mkdir $destDir"
        Write-Host "  [dry-run] copy $src -> $dest"
        if ($Prefix) { Write-Host "  [dry-run] rewrite 'name:' field with prefix '$Prefix'" }
        return
    }

    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dest -Force

    if ($Prefix) {
        $content = Get-Content -LiteralPath $dest -Raw
        $content = [regex]::Replace($content, '(?m)^name:\s*', "name: $Prefix")
        Set-Content -LiteralPath $dest -Value $content -NoNewline
    }
}

function Install-Selected {
    $mode = if ($script:CopyMode) { 'copy' } else { 'symlink' }
    Write-Host ""
    if ($DryRun) { Write-Color yellow "=== DRY RUN ===" }

    $installed = 0
    $skipped   = 0
    $manifestLines = New-Object System.Collections.Generic.List[string]
    $manifestPath  = Join-Path $InstallDir $ManifestFile

    # Pre-parse existing manifest into a set of managed names
    $managed = @{}
    if (Test-Path -LiteralPath $manifestPath) {
        foreach ($line in Get-Content -LiteralPath $manifestPath) {
            if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) { continue }
            $parts = $line -split ':', 3
            if ($parts.Count -ge 1 -and $parts[0]) { $managed[$parts[0]] = $true }
        }
    }

    for ($i = 0; $i -lt $script:SkillNames.Count; $i++) {
        if ($script:SkillSelected[$i] -ne 1) { continue }

        $name     = $script:SkillNames[$i]
        $destName = "$Prefix$name"
        $destDir  = Join-Path $InstallDir $destName

        if ((Test-Path -LiteralPath $destDir) -and -not $DryRun) {
            $hasManifest = Test-Path -LiteralPath $manifestPath
            if ($hasManifest -and -not $managed.ContainsKey($destName)) {
                Write-Color yellow "  Skipping $destName (exists, not managed by this installer)"
                $skipped++
                continue
            }
        }

        if ($script:CopyMode) {
            Install-SkillCopy -Name $name
        } else {
            Install-SkillSymlink -Name $name
        }

        $srcPath = Join-Path $SkillsSrcDir $name
        $manifestLines.Add("${destName}:${mode}:${srcPath}") | Out-Null
        $installed++

        if (-not $DryRun) {
            Write-Color green "  [OK] " -NoNewline
            Write-Host $destName
        }
    }

    if (-not $DryRun -and $installed -gt 0) {
        $nowUtc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        $header = @(
            "# slang-skills manifest -- do not edit manually",
            "# installed: $nowUtc",
            "# source: $ScriptDir",
            "# mode: $mode"
        )
        if ($Prefix) { $header += "# prefix: $Prefix" }

        $all = $header + $manifestLines.ToArray()
        # Write UTF-8 without BOM so bash's `#` header parser stays happy.
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllLines($manifestPath, [string[]]$all, $utf8NoBom)
    }

    Write-Host ""
    if ($DryRun) {
        Write-Host "Dry run complete. $installed skill(s) would be installed."
    } else {
        Write-Host "Installed $installed skill(s) to $InstallDir"
        if ($skipped -gt 0) {
            Write-Host "Skipped $skipped skill(s) (already installed by another source)."
        }
        Write-Host ""
        Write-Color dim "Restart Claude Code to load the new skills."
    }
}

# --- Uninstall --------------------------------------------------------------

function Invoke-Uninstall {
    $manifestPath = Join-Path $InstallDir $ManifestFile
    if (-not (Test-Path -LiteralPath $manifestPath)) {
        Write-Host "No manifest found at $manifestPath"
        Write-Host "Cannot determine which skills were installed by this script."
        Write-Host "You can manually remove skill directories from $InstallDir"
        exit 1
    }

    $entries = @()
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split ':', 3
        if ($parts.Count -ge 2) {
            $entries += [PSCustomObject]@{ Name = $parts[0]; Mode = $parts[1] }
        }
    }

    Write-Host ""
    Write-Host "The following skills will be removed:"
    Write-Host ""
    if ($entries.Count -eq 0) {
        Write-Host "  (none)"
        Remove-Item -LiteralPath $manifestPath -Force
        exit 0
    }
    foreach ($e in $entries) { Write-Host "  $($e.Name) ($($e.Mode))" }
    Write-Host ""

    if ($DryRun) {
        Write-Host "[dry-run] Would remove $($entries.Count) skill(s)."
        return
    }

    if (-not $NonInteractive) {
        $reply = Read-Host "Proceed? [y/N]"
        if ($reply -notmatch '^[Yy]') {
            Write-Host "Aborted."
            exit 0
        }
    }

    $removed = 0
    foreach ($e in $entries) {
        $destDir = Join-Path $InstallDir $e.Name
        $skillMd = Join-Path $destDir "SKILL.md"

        if (Test-Path -LiteralPath $destDir) {
            if (Test-Path -LiteralPath $skillMd) {
                # Remove-Item on a symlink deletes the link, not the target.
                Remove-Item -LiteralPath $skillMd -Force -ErrorAction SilentlyContinue
            }
            try {
                Remove-Item -LiteralPath $destDir -Force -ErrorAction Stop
                Write-Color green "  [OK] " -NoNewline
                Write-Host "Removed $($e.Name)"
                $removed++
            } catch {
                # Directory not empty: leave it for the user.
                Write-Color yellow "  [~] $($e.Name) (directory not empty, kept)"
            }
        } else {
            Write-Color dim "  - $($e.Name) (already gone)"
            $removed++
        }
    }

    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Removed $removed skill(s)."
    Write-Color dim "Restart Claude Code to apply changes."
}

# --- Status -----------------------------------------------------------------

function Show-Status {
    $manifestPath = Join-Path $InstallDir $ManifestFile

    Write-Host ""
    Write-Color bold "  slang-skills status"
    Write-Host "  -------------------------------------"
    Write-Host "  Install dir: $InstallDir"

    if (-not (Test-Path -LiteralPath $manifestPath)) {
        Write-Host ""
        Write-Color dim "  No manifest at $manifestPath"
        Write-Host "  No skills are tracked by this installer here."
        Write-Host ""
        return
    }

    # Header metadata
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        switch -Regex ($line) {
            '^# installed:\s*(.+)$' { Write-Host "  Installed:   $($matches[1])" }
            '^# source:\s*(.+)$'    { Write-Host "  Source:      $($matches[1])" }
            '^# mode:\s*(.+)$'      { Write-Host "  Mode:        $($matches[1])" }
            '^# prefix:\s*(.+)$'    { Write-Host "  Prefix:      $($matches[1])" }
        }
    }
    Write-Host "  -------------------------------------"
    Write-Host ""

    $total = 0; $ok = 0; $broken = 0
    foreach ($line in Get-Content -LiteralPath $manifestPath) {
        if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) { continue }
        $parts = $line -split ':', 3
        if ($parts.Count -lt 2) { continue }
        $name       = $parts[0]
        $entryMode  = $parts[1]
        $sourcePath = if ($parts.Count -ge 3) { $parts[2] } else { '' }

        $total++
        $skillMd = Join-Path $InstallDir (Join-Path $name "SKILL.md")

        $color = 'green'; $glyph = '[OK]'; $state = ''

        if ($entryMode -eq 'symlink') {
            if (Test-IsSymlink $skillMd) {
                $target = Get-SymlinkTarget $skillMd
                if (Test-Path -LiteralPath $skillMd) {
                    $state = "ok (-> $target)"
                    $ok++
                } else {
                    $state = "dangling (-> $target)"
                    $color = 'red'; $glyph = '[X]'
                    $broken++
                }
            } elseif (Test-Path -LiteralPath $skillMd) {
                $state = "not a symlink (mode changed?)"
                $color = 'yellow'; $glyph = '[~]'
                $ok++
            } else {
                $state = "missing"
                $color = 'red'; $glyph = '[X]'
                $broken++
            }
        } else {
            # copy mode
            if ((Test-Path -LiteralPath $skillMd -PathType Leaf) -and -not (Test-IsSymlink $skillMd)) {
                $state = "ok (copied from $sourcePath)"
                $ok++
            } elseif (Test-Path -LiteralPath $skillMd) {
                $state = "unexpected file type"
                $color = 'yellow'; $glyph = '[~]'
                $ok++
            } else {
                $state = "missing"
                $color = 'red'; $glyph = '[X]'
                $broken++
            }
        }

        Write-Color $color "  $glyph " -NoNewline
        Write-Host ("{0} " -f $name.PadRight(32)) -NoNewline
        Write-Color dim $state
    }

    Write-Host ""
    if ($total -eq 0) {
        Write-Host "  No skills listed in manifest."
    } elseif ($broken -eq 0) {
        Write-Host "  $total skill(s) installed, all healthy."
    } else {
        Write-Color yellow "  $total skill(s) installed, $broken broken."
        Write-Host "  Re-run .\install.ps1 to repair, or .\install.ps1 -Uninstall to clear."
    }
    Write-Host ""
}

# --- Confirmation prompt ----------------------------------------------------

function Confirm-Install {
    $mode = if ($script:CopyMode) { 'copy' } else { 'symlink' }
    $selected = 0
    for ($i = 0; $i -lt $script:SkillSelected.Count; $i++) {
        if ($script:SkillSelected[$i] -eq 1) { $selected++ }
    }

    Write-Host ""
    Write-Color bold "  Install summary"
    Write-Host "  -------------------------------------"
    Write-Host "  Skills:    $selected"
    Write-Host "  Mode:      $mode"
    Write-Host "  Target:    $InstallDir"
    if ($Prefix) { Write-Host "  Prefix:    $Prefix" }
    Write-Host "  -------------------------------------"
    Write-Host ""

    if ($NonInteractive -or $DryRun) { return }

    $reply = Read-Host "  Proceed? [Y/n]"
    if ($reply -match '^[Nn]') {
        Write-Host "  Aborted."
        exit 0
    }
}

# --- Main -------------------------------------------------------------------

function Invoke-Main {
    if ($Help) {
        Show-Usage
        return
    }

    if ($Status) {
        Show-Status
        return
    }

    if ($Uninstall) {
        Invoke-Uninstall
        return
    }

    Find-Skills

    Test-SymlinkSupport

    # Prefix implies copy mode
    if ($Prefix -and -not $script:CopyMode) {
        Write-Color dim "Note: -Prefix implies copy mode (cannot prefix symlinks)"
        $script:CopyMode = $true
    }

    # Select
    if ($NonInteractive -or -not $script:SupportsRawInput) {
        if (-not $NonInteractive -and -not $script:SupportsRawInput) {
            Write-Host "Non-interactive host detected. Installing all skills."
            Write-Host "Use -Skills 'name1,name2' to select specific skills."
            $NonInteractive = $true
        }
        Show-NonInteractiveList
    } else {
        Invoke-InteractiveSelect
    }

    Test-AllDependencies

    if (-not $DryRun) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    Confirm-Install
    Install-Selected
}

Invoke-Main
