# Isolated installer acceptance: only synthetic private records and temporary profile.
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$testRoot = [IO.Path]::GetFullPath((Join-Path $systemTemp ('mcd-budget-meal-test-' + [guid]::NewGuid().ToString('N'))))
if (-not $testRoot.StartsWith($systemTemp+'\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe test directory' }
function Check($Condition, [string]$Description) { if (-not $Condition) { throw $Description }; Write-Host ('PASS: '+$Description) }
try {
    $package = Join-Path $testRoot 'package'
    New-Item -ItemType Directory -Path (Join-Path $package 'skills') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repository 'install.ps1') -Destination $package
    Copy-Item -LiteralPath (Join-Path $repository 'skills\mcd-budget-meal') -Destination (Join-Path $package 'skills\mcd-budget-meal') -Recurse
    $source = Join-Path $package 'skills\mcd-budget-meal'
    New-Item -ItemType Directory -Path (Join-Path $source 'private'),(Join-Path $source 'scripts\__pycache__') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $source 'private\package-secret.txt') -Value 'SYNTHETIC-NOT-TO-COPY'
    Set-Content -LiteralPath (Join-Path $source 'scripts\__pycache__\old.pyc') -Value 'SYNTHETIC-CACHE'
    $profile = Join-Path $testRoot 'profile'
    $install = Join-Path $package 'install.ps1'
    $first = & $install -ProfileDirectory $profile
    $target = $first.TargetPath
    Check (Test-Path -LiteralPath (Join-Path $target 'references\report-template.html')) 'Fresh install includes report template'
    Check (-not (Test-Path -LiteralPath (Join-Path $target 'private\package-secret.txt'))) 'Package private records excluded'
    Check (-not (Test-Path -LiteralPath (Join-Path $target 'scripts\__pycache__'))) 'Python cache excluded'
    $checkPlan = & python -B (Join-Path $target 'scripts\quote_meals.py') (Join-Path $repository 'examples\plan-template.json') --check-plan
    Check ($LASTEXITCODE -eq 0) 'Installed batch entry validates synthetic plan offline'
    $installedPrivate = Join-Path $target 'private'
    New-Item -ItemType Directory -Path $installedPrivate -Force | Out-Null
    $savedComparison = Join-Path $installedPrivate 'comparison.json'
    & python -B (Join-Path $target 'scripts\compare_meals.py') (Join-Path $repository 'examples\demo-quotes.json') --format json | Set-Content -Encoding UTF8 -LiteralPath $savedComparison
    Check ($LASTEXITCODE -eq 0) 'Installed comparison entry produces synthetic JSON'
    $restoredReport = Join-Path $installedPrivate 'restored.html'
    & python -B (Join-Path $target 'scripts\report_meals.py') $savedComparison --from-comparison --output $restoredReport | Out-Null
    Check ($LASTEXITCODE -eq 0 -and (Get-Content -Raw -Encoding UTF8 -LiteralPath $restoredReport).Contains('"historical":true')) 'Installed report entry restores JSON as historical HTML'
    $records = Join-Path $target 'private\old-run'
    New-Item -ItemType Directory -Path $records -Force | Out-Null
    $originalBytes = [byte[]](0,1,2,128,255,10)
    [IO.File]::WriteAllBytes((Join-Path $records 'raw.bin'),$originalBytes)
    Set-Content -LiteralPath (Join-Path $target 'scripts\obsolete.py') -Value 'obsolete'
    $second = & $install -ProfileDirectory $profile
    Check (-not (Test-Path -LiteralPath (Join-Path $target 'scripts\obsolete.py'))) 'Upgrade removes obsolete program file'
    Check (Test-Path -LiteralPath (Join-Path $second.BackupPath 'scripts\obsolete.py')) 'Complete previous version remains in backup'
    $afterBytes=[IO.File]::ReadAllBytes((Join-Path $target 'private\old-run\raw.bin'))
    Check ([Convert]::ToBase64String($afterBytes) -eq [Convert]::ToBase64String($originalBytes)) 'Private record bytes preserved after upgrade'
    Check (Test-Path -LiteralPath (Join-Path $second.BackupPath 'private\old-run\raw.bin')) 'Private records also retained in backup'
    # Inject a cutover failure, allowing rollback Move-Item to execute normally.
    $failureState=[pscustomobject]@{Triggered=$false}
    function Move-Item {
        [CmdletBinding()]param([string]$LiteralPath,[string]$Destination)
        if ((Split-Path $LiteralPath -Leaf).StartsWith('.mcd-budget-meal-stage-') -and -not $failureState.Triggered) {
            $failureState.Triggered=$true
            throw 'Synthetic cutover failure'
        }
        Microsoft.PowerShell.Management\Move-Item -LiteralPath $LiteralPath -Destination $Destination
    }
    $failed=$false
    try { & $install -ProfileDirectory $profile | Out-Null } catch { $failed=$true }
    Check ($failed -and $failureState.Triggered) 'Cutover failure is reported'
    Check (Test-Path -LiteralPath (Join-Path $target 'SKILL.md')) 'Previous installation restored after failure'
    Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $target 'private\old-run\raw.bin'))) -eq [Convert]::ToBase64String($originalBytes)) 'Rollback preserves private bytes'
    Remove-Item -LiteralPath Function:\Move-Item
    $rejected=$false
    try { & $install -ProfileDirectory $source | Out-Null } catch { $rejected=$true }
    Check $rejected 'Nested source/target installation rejected'
    Write-Host '14 temporary-directory installer acceptance checks passed.'
} finally {
    $checkedRoot=[IO.Path]::GetFullPath($testRoot)
    if (-not $checkedRoot.StartsWith($systemTemp+'\mcd-budget-meal-test-', [StringComparison]::OrdinalIgnoreCase)) { throw 'Cleanup refused' }
    if (Test-Path -LiteralPath $checkedRoot) { Remove-Item -LiteralPath $checkedRoot -Recurse -Force }
}
