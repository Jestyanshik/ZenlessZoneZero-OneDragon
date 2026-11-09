[CmdletBinding()]
param(
    [string] $Tag,
    [string] $Destination,
    [string] $Python,
    [switch] $OpenDraft
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$official = 'https://github.com/OneDragon-Anything/ZenlessZoneZero-OneDragon.git'
$base = (Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'upstream-base.txt')).Trim()
$baseCommit = (Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'upstream-commit.txt')).Trim()

function Invoke-RepoGit([string] $Repo, [string[]] $Command) {
    $trusted = "safe.directory=$($Repo.Replace('\','/'))"
    & git -c $trusted -C $Repo @Command
    if ($LASTEXITCODE) { throw "Git $($Command[0]) failed (exit $LASTEXITCODE)" }
}

$upstream = Invoke-RepoGit $root @('remote', 'get-url', 'upstream')
if ($upstream -ne $official) { throw "The upstream remote must be $official" }
if ($Tag -and $Tag -notmatch '^v\d+\.\d+\.\d+$') { throw 'Expected a stable tag such as v2.6.1.' }

$api = 'https://api.github.com/repos/OneDragon-Anything/ZenlessZoneZero-OneDragon/releases/'
$release = Invoke-RestMethod -Uri ($api + $(if ($Tag) { "tags/$Tag" } else { 'latest' })) -Headers @{
    'User-Agent' = 'OneDragon-Fork-Update'
    'Accept' = 'application/vnd.github+json'
} -TimeoutSec 30
if ($release.draft -or $release.prerelease -or $release.tag_name -notmatch '^v\d+\.\d+\.\d+$') {
    throw 'GitHub did not return a stable official release.'
}
$Tag = $release.tag_name
Write-Host "Current upstream base $base. Selected official release $Tag."
if ([version]$Tag.Substring(1) -le [version]$base.Substring(1)) { return }

$baseBranch = Invoke-RepoGit $root @('branch', '--show-current')
if ($baseBranch -notin @('main', 'codex/ru-ui')) {
    throw 'Run this command from the maintained fork branch (main or codex/ru-ui).'
}
$dirty = Invoke-RepoGit $root @('--no-optional-locks', 'status', '--porcelain', '--untracked-files=no')
if ($dirty) { throw 'Commit or otherwise review tracked local changes before preparing an update.' }

$fork = $null
if ($OpenDraft) {
    $origin = Invoke-RepoGit $root @('remote', 'get-url', 'origin')
    if ($origin -notmatch '^https://github\.com/([A-Za-z0-9-]+/[A-Za-z0-9_.-]+?)\.git$') {
        throw 'The origin remote must be an HTTPS GitHub fork.'
    }
    $fork = $Matches[1]
    $pushUrl = Invoke-RepoGit $root @('remote', 'get-url', '--push', 'origin')
    if ($pushUrl -ne $origin) { throw 'The origin fetch and push URLs must match.' }
    $parent = & gh api "repos/$fork" --jq '.parent.full_name'
    if ($LASTEXITCODE -or $parent -ne 'OneDragon-Anything/ZenlessZoneZero-OneDragon') {
        throw 'Origin is not an accessible fork of the official repository.'
    }
    $remoteHead = Invoke-RepoGit $root @('ls-remote', '--heads', 'origin', "refs/heads/$baseBranch")
    $localHead = Invoke-RepoGit $root @('rev-parse', 'HEAD')
    if (-not $remoteHead -or ($remoteHead -split '\s+')[0] -ne $localHead) {
        throw 'The local base must match the published fork branch before opening a draft PR.'
    }
}

Invoke-RepoGit $root @('fetch', '--no-tags', 'upstream', "refs/tags/${Tag}:refs/tags/$Tag")
$targetCommit = Invoke-RepoGit $root @('rev-parse', "${Tag}^{commit}")
Invoke-RepoGit $root @('merge-base', '--is-ancestor', $baseCommit, $targetCommit)
$changes = Invoke-RepoGit $root @('log', '--oneline', "$baseCommit..$targetCommit")
$changes | Write-Output
Write-Host $release.html_url

$branch = "codex/upstream-$Tag"
if (-not $Destination) { $Destination = Join-Path (Split-Path $root -Parent) "OneDragon-review-$Tag" }
$Destination = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Destination)
if (Test-Path -LiteralPath $Destination) { throw "Review destination already exists: $Destination" }
Invoke-RepoGit $root @('worktree', 'add', '-b', $branch, $Destination, 'HEAD')

try {
    Invoke-RepoGit $Destination @('merge', '--no-ff', '--no-commit', $targetCommit)
} catch {
    $conflicts = Invoke-RepoGit $Destination @('diff', '--name-only', '--diff-filter=U')
    $conflicts | Write-Output
    throw "Merge stopped. Review the retained worktree at $Destination. No draft PR was opened."
}

Set-Content -LiteralPath (Join-Path $Destination 'tools/fork/upstream-base.txt') -Value $Tag -Encoding ascii
Set-Content -LiteralPath (Join-Path $Destination 'tools/fork/upstream-commit.txt') -Value $targetCommit -Encoding ascii
Push-Location -LiteralPath $Destination
$previousPythonPath = $env:PYTHONPATH
$previousQtPlatform = $env:QT_QPA_PLATFORM
$previousSkipDriver = $env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL
try {
    $env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL = 'true'
    $env:QT_QPA_PLATFORM = 'offscreen'
    $env:PYTHONPATH = Join-Path $Destination 'src'
    if ($Python) {
        & $Python -m pytest -q tools/fork/checks.py
    } else {
        & uv sync --locked --group dev
        if ($LASTEXITCODE) { throw 'Dependency setup failed in the review worktree.' }
        & uv run --no-sync python -m pytest -q tools/fork/checks.py
    }
    if ($LASTEXITCODE) { throw "Verification failed. The review worktree is retained at $Destination." }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    $env:QT_QPA_PLATFORM = $previousQtPlatform
    $env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL = $previousSkipDriver
    Pop-Location
}

Invoke-RepoGit $Destination @('add', '--', 'tools/fork/upstream-base.txt', 'tools/fork/upstream-commit.txt')
Invoke-RepoGit $Destination @('diff', '--cached', '--check')
Invoke-RepoGit $Destination @('commit', '-m', "chore(upstream): integrate $Tag")
Write-Host "Verified update branch $branch at $Destination."

if ($OpenDraft) {
    $draft = @(
        "Integrates official $Tag into the fork."
        ''
        "Previous upstream base: $base."
        "Official release: $($release.html_url)"
        'Fork verification: passed.'
        ''
        'Manual in-game verification is pending.'
        ''
        'Upstream commits:'
    ) + @($changes | Select-Object -First 100 | ForEach-Object { "- $_" })
    $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) "onedragon-$([guid]::NewGuid()).md"
    try {
        Set-Content -LiteralPath $bodyFile -Value $draft -Encoding utf8
        Invoke-RepoGit $Destination @('push', '-u', 'origin', "HEAD:refs/heads/$branch")
        & gh pr create --repo $fork --base $baseBranch --head $branch --draft --title "Integrate upstream $Tag" --body-file $bodyFile
        if ($LASTEXITCODE) { throw 'The update branch was pushed, but draft PR creation failed.' }
    } finally {
        if (Test-Path -LiteralPath $bodyFile) { Remove-Item -LiteralPath $bodyFile }
    }
}
