# SSI-263 SAPI -- Check for updates, by hand only (Tomi: never on its own; the button is the consent to look).
#
# The NVDA add-on's rules (nvda/ssi263/globalPlugins/ssi263Speech/updates.py), in PowerShell for the settings
# dialog: GitHub's releases, drafts and prereleases skipped, the version read from the installer's own name
# (ssi263-sapi-0.8.5-setup.exe says 0.8.5 on whichever release carries it), the newest across the releases; and the
# download checked against that release's SHA256SUMS.txt before it runs.  It fails closed: no checksum file, no
# entry, two entries or a wrong hash, and nothing runs.  (SHA256SUMS proves the file is the one that release
# published, not who made it: it is not a signature.)  The installer's own pages and its UAC prompt still ask.
#
# PowerShell 2.0's dialect, like settings.ps1: JSON through .NET 3.5's JavaScriptSerializer (ConvertFrom-Json is
# 3.0), WebClient (Invoke-WebRequest is 3.0), SHA-256 through .NET (Get-FileHash is 4.0).
# SSI263_UPDATES_BREAK, the tests' controls (test_updates.ps1; never set otherwise): "drafts" offers drafts and
# prereleases, "hash" takes any download.

$UpdateRepo = 'tgeczy/ssi263-speech'
$UpdateApi = "https://api.github.com/repos/$UpdateRepo/releases?per_page=20"
$UpdateAsset = '^ssi263-sapi-(\d+(?:\.\d+)*)-setup\.exe$'
$UpdateSums = 'SHA256SUMS.txt'
$UpdateAgent = 'ssi263-sapi-settings'
# the installer's own AppId (installer.iss): Inno Setup keeps the installed version under it
$UpdateUninstallKeys = @(
    'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{7C3E91A2-5B64-4D0F-9E28-A61D3F84C7B5}_is1',
    'HKLM:\SOFTWARE\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{7C3E91A2-5B64-4D0F-9E28-A61D3F84C7B5}_is1')

function Compare-UpdateVersions([string]$a, [string]$b) {
    # 1 when $a is newer, -1 when older, 0 when the same; digits only, so a tag's prefix or suffix never counts
    $pa = @([regex]::Matches($a, '\d+') | ForEach-Object { [int]$_.Value })
    $pb = @([regex]::Matches($b, '\d+') | ForEach-Object { [int]$_.Value })
    $width = [Math]::Max($pa.Length, $pb.Length)
    for ($i = 0; $i -lt $width; $i++) {
        $x = 0; $y = 0
        if ($i -lt $pa.Length) { $x = $pa[$i] }
        if ($i -lt $pb.Length) { $y = $pb[$i] }
        if ($x -gt $y) { return 1 }
        if ($x -lt $y) { return -1 }
    }
    0
}

# GitHub's list of releases, as dictionaries (draft, prerelease, assets: name, browser_download_url)
function ConvertFrom-UpdateJson([string]$text) {
    Add-Type -AssemblyName System.Web.Extensions
    $serializer = New-Object Web.Script.Serialization.JavaScriptSerializer
    $serializer.MaxJsonLength = 64MB
    $list = $serializer.DeserializeObject($text)
    if (-not ($list -is [Array])) { throw "GitHub's answer was not a list of releases." }
    ,$list
}

# The newest installer newer than $current among the releases: @{version; name; url; sums}, or $null.
function Find-UpdateRelease($releases, [string]$current) {
    $best = $null
    foreach ($release in $releases) {
        if (($release['draft'] -or $release['prerelease']) -and $env:SSI263_UPDATES_BREAK -ne 'drafts') { continue }
        $assets = @{}
        foreach ($a in @($release['assets'])) { if ($a) { $assets[[string]$a['name']] = [string]$a['browser_download_url'] } }
        foreach ($name in $assets.Keys) {
            if ($name -notmatch $UpdateAsset -or -not $assets[$name]) { continue }
            $v = $matches[1]
            if (-not $best -or (Compare-UpdateVersions $v $best.version) -gt 0) {
                $best = @{ version = $v; name = $name; url = $assets[$name]; sums = $assets[$UpdateSums] }
            }
        }
    }
    if (-not $best -or (Compare-UpdateVersions $best.version $current) -le 0) { return $null }
    $best
}

# The one SHA-256 SHA256SUMS.txt gives for $name (sha256sum's "<hash>  <name>" or "<hash> *<name>")
function Get-UpdateExpectedHash([string]$sumsText, [string]$name) {
    $found = @()
    foreach ($line in ($sumsText -split "`r?`n")) {
        if ($line -match '^([0-9a-fA-F]{64}) [ *](.+?)\s*$' -and $matches[2] -ceq $name) { $found += $matches[1].ToLower() }
    }
    if ($found.Length -eq 0) { throw "The release's checksum file has no entry for $name." }
    if ($found.Length -gt 1) { throw "The release's checksum file lists $name more than once." }
    $found[0]
}

function Test-UpdateHash([string]$path, [string]$sha256) {
    if ($env:SSI263_UPDATES_BREAK -eq 'hash') { return }
    $sha = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($path)
    try { $got = -join ($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) } finally { $stream.Close() }
    if ($got -ne $sha256) {
        throw ("The download does not match the release's checksum (got {0}, expected {1})." -f $got.Substring(0, 12), $sha256.Substring(0, 12))
    }
}

function Get-InstalledSapiVersion {
    foreach ($path in $UpdateUninstallKeys) {
        try {
            $v = (Get-ItemProperty -Path $path -Name DisplayVersion -ErrorAction Stop).DisplayVersion
            if ($v) { return [string]$v }
        } catch {}
    }
    $null
}

function New-UpdateClient {
    # GitHub is TLS 1.2 or nothing; an older .NET defaults to less (additive, forgiven where the value is unknown)
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072 } catch {}
    $wc = New-Object Net.WebClient
    $wc.Headers.Add('User-Agent', $UpdateAgent)
    $wc
}

# The newest release's installer newer than $current, from GitHub: @{...} or $null; throws with words
function Get-UpdateOffer([string]$current) {
    try { $json = (New-UpdateClient).DownloadString($UpdateApi) }
    catch { throw ("Could not reach GitHub: {0}" -f $_.Exception.Message) }
    Find-UpdateRelease (ConvertFrom-UpdateJson $json) $current
}

# The offer's installer saved in $folder and checked against its release's SHA256SUMS.txt: its path; throws with
# words, the file removed, when it cannot be checked or does not match
function Save-UpdateInstaller($offer, [string]$folder) {
    if (-not $offer.sums) { throw "The release has no $UpdateSums, so the download cannot be checked." }
    $file = Join-Path $folder $offer.name
    # the old file first, so a half-written download from a failed attempt is never the thing that runs
    if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
    try {
        $wc = New-UpdateClient
        $sums = $wc.DownloadString($offer.sums)
        $wc.DownloadFile($offer.url, $file)
    } catch {
        if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file -Force }
        throw ("The download failed: {0}" -f $_.Exception.Message)
    }
    try { Test-UpdateHash $file (Get-UpdateExpectedHash $sums $offer.name) }
    catch { Remove-Item -LiteralPath $file -Force; throw }
    $file
}
