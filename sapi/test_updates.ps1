# test_updates.ps1 -- the SAPI settings' Check for updates (updates.ps1) on GitHub's shapes, with no network:
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File sapi\test_updates.ps1
#
# The releases as this repository has them (the Android updater's UpdatesTest.kt, with the SAPI installer's names):
# a draft and a prerelease never offered, a release with no installer passed over, the version read from the
# installer's own name (0.8.0's release carrying a rebuilt 0.8.2 installer), the newest across the releases; and the
# checksum: an entry found in either of sha256sum's forms, none or two refused, a wrong file refused and removed.
# The controls (run_tests): SSI263_UPDATES_BREAK=drafts (the draft offered) and =hash (any download taken) must
# fail their own checks.
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'updates.ps1')

$failures = 0
function Check([string]$name, [bool]$ok, [string]$detail) {
    Write-Output ('{0,-4} {1,-60} {2}' -f $(if ($ok) { 'ok' } else { 'FAIL' }), $name, $detail)
    if (-not $ok) { $script:failures++ }
}

$releases = ConvertFrom-UpdateJson @'
[
  {"tag_name": "v0.9.0", "draft": true, "prerelease": false,
   "assets": [{"name": "ssi263-sapi-0.9.0-setup.exe", "browser_download_url": "https://example/draft.exe"},
              {"name": "SHA256SUMS.txt", "browser_download_url": "https://example/draft-sums"}]},
  {"tag_name": "v0.8.5-beta", "draft": false, "prerelease": true,
   "assets": [{"name": "ssi263-sapi-0.8.5-setup.exe", "browser_download_url": "https://example/beta.exe"}]},
  {"tag_name": "v0.8.1", "draft": false, "prerelease": false,
   "assets": [{"name": "ssi263-speech-0.8.1.nvda-addon", "browser_download_url": "https://example/0.8.1.addon"}]},
  {"tag_name": "v0.8.0", "draft": false, "prerelease": false,
   "assets": [{"name": "ssi263-speech-0.8.0.nvda-addon", "browser_download_url": "https://example/0.8.0.addon"},
              {"name": "ssi263-sapi-0.8.2-setup.exe", "browser_download_url": "https://example/0.8.2.exe"},
              {"name": "SHA256SUMS.txt", "browser_download_url": "https://example/0.8.0-sums"}]},
  {"tag_name": "v0.7.7", "draft": false, "prerelease": false,
   "assets": [{"name": "ssi263-sapi-0.7.7-setup.exe", "browser_download_url": "https://example/0.7.7.exe"},
              {"name": "ssi263-sapi-setup.exe", "browser_download_url": "https://example/unversioned.exe"}]}
]
'@

$o = Find-UpdateRelease $releases '0.8.0'
Check 'the newest installer, read from its own name' ($o -and $o.version -eq '0.8.2' -and $o.url -eq 'https://example/0.8.2.exe') ('offered: {0}' -f $(if ($o) { $o.name } else { 'nothing' }))
Check 'its release''s checksum file goes with it' ($o -and $o.sums -eq 'https://example/0.8.0-sums') ('sums: {0}' -f $(if ($o) { $o.sums } else { '-' }))
$o = Find-UpdateRelease $releases '0.7.5'
Check 'drafts and prereleases are never offered' ($o -and $o.version -eq '0.8.2') ('from 0.7.5, offered: {0}' -f $(if ($o) { $o.name } else { 'nothing' }))
$o = Find-UpdateRelease $releases '0.8.2'
Check 'the newest installed: nothing offered' ($null -eq $o) ('from 0.8.2, offered: {0}' -f $(if ($o) { $o.name } else { 'nothing' }))
$o = Find-UpdateRelease $releases '0.10.0'
Check 'versions compared as numbers, not text' ($null -eq $o) ('from 0.10.0, offered: {0}' -f $(if ($o) { $o.name } else { 'nothing' }))
Check 'a version with a tag''s prefix compares by its numbers' ((Compare-UpdateVersions 'v0.8.2' '0.8.2') -eq 0 -and (Compare-UpdateVersions '0.8' '0.8.0') -eq 0 -and (Compare-UpdateVersions '0.8.10' '0.8.9') -eq 1) 'v0.8.2 = 0.8.2, 0.8 = 0.8.0, 0.8.10 > 0.8.9'

$name = 'ssi263-sapi-0.8.2-setup.exe'
$hash = 'ab' * 32
$sums = "{0}  ssi263-speech-0.8.0.nvda-addon`n{1}  {2}`n" -f ('cd' * 32), $hash, $name
$got = $null; try { $got = Get-UpdateExpectedHash $sums $name } catch {}
Check 'the checksum file''s entry for the installer' ($got -eq $hash) ('got {0}' -f $got)
$got = $null; try { $got = Get-UpdateExpectedHash ("{0} *{1}`r`n" -f $hash.ToUpper(), $name) $name } catch {}
Check 'sha256sum''s binary form, upper case' ($got -eq $hash) ('got {0}' -f $got)
$cases = @(
    @('no entry', ("{0}  other.exe`n" -f $hash), 'no entry'),
    @('two entries', ("{0}  {1}`n{0}  {1}`n" -f $hash, $name), 'more than once'),
    @('a name that only ends the same', ("{0}  old-{1}`n" -f $hash, $name), 'no entry'))
foreach ($case in $cases) {
    $why = ''; try { Get-UpdateExpectedHash $case[1] $name | Out-Null } catch { $why = $_.Exception.Message }
    Check ('refused: ' + $case[0]) ($why -like ('*' + $case[2] + '*')) $(if ($why) { $why } else { 'taken' })
}

$folder = Join-Path $env:TEMP ('ssi263-updates-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $folder | Out-Null
try {
    $file = Join-Path $folder $name
    [IO.File]::WriteAllBytes($file, [Text.Encoding]::ASCII.GetBytes('an installer'))
    $sha = [Security.Cryptography.SHA256]::Create()
    $right = -join ($sha.ComputeHash([Text.Encoding]::ASCII.GetBytes('an installer')) | ForEach-Object { $_.ToString('x2') })
    $why = $null; try { Test-UpdateHash $file $right } catch { $why = $_.Exception.Message }
    Check 'the right download is taken' ($null -eq $why) $(if ($why) { $why } else { 'matches' })
    $why = $null; try { Test-UpdateHash $file ('0' * 64) } catch { $why = $_.Exception.Message }
    Check 'a download that does not match is refused' ($null -ne $why) $(if ($why) { $why } else { 'taken' })
    $offer = @{ version = '0.8.2'; name = $name; url = 'https://example/0.8.2.exe'; sums = $null }
    $why = $null; try { Save-UpdateInstaller $offer $folder | Out-Null } catch { $why = $_.Exception.Message }
    Check 'a release with no checksum file is refused before downloading' ($null -ne $why -and (Test-Path -LiteralPath $file)) $(if ($why) { $why } else { 'taken' })
} finally {
    Remove-Item -LiteralPath $folder -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures) { Write-Output ('sapi updates: {0} FAILED' -f $failures); exit 1 }
Write-Output 'sapi updates: all passed'
exit 0
