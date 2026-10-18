param(
    [string]$ProfileDirectory = [Environment]::GetFolderPath('UserProfile')
)
$ErrorActionPreference = 'Stop'
$sourceSkill = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'skills\mcd-budget-meal'))
$profilePath = [IO.Path]::GetFullPath($ProfileDirectory)
$workbuddyPath = Join-Path $profilePath '.workbuddy'
$skillHomePath = [IO.Path]::GetFullPath((Join-Path $workbuddyPath 'skills'))
$targetSkillPath = [IO.Path]::GetFullPath((Join-Path $skillHomePath 'mcd-budget-meal'))
$backupRootPath = [IO.Path]::GetFullPath((Join-Path $workbuddyPath 'skill-backups'))

function Assert-Contained([string]$Candidate, [string]$Parent) {
    $absolute = [IO.Path]::GetFullPath($Candidate)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if (-not $absolute.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw '安装或备份路径超出指定目录。'
    }
}
function Assert-RegularTree([string]$TreePath) {
    if (-not (Test-Path -LiteralPath $TreePath)) { return }
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($TreePath)
    while ($pending.Count) {
        $item = Get-Item -LiteralPath $pending.Pop() -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw '安装路径或文件包含链接；请先使用普通目录，未替换原技能。'
        }
        if ($item.PSIsContainer) {
            foreach ($child in (Get-ChildItem -LiteralPath $item.FullName -Force)) { $pending.Push($child.FullName) }
        }
    }
}
function Copy-Package([string]$From, [string]$To) {
    New-Item -ItemType Directory -Path $To -Force | Out-Null
    foreach ($part in (Get-ChildItem -LiteralPath $From -Force)) {
        if ($part.Name -in @('private', '__pycache__') -or $part.Extension -eq '.pyc') { continue }
        if ($part.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw '源技能包含链接，停止安装。' }
        $destination = Join-Path $To $part.Name
        if ($part.PSIsContainer) { Copy-Package $part.FullName $destination }
        else { Copy-Item -LiteralPath $part.FullName -Destination $destination }
    }
}
Assert-Contained $targetSkillPath $skillHomePath
Assert-Contained $backupRootPath $workbuddyPath
foreach ($path in @($profilePath, $workbuddyPath, $skillHomePath, $targetSkillPath, $backupRootPath)) {
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw '安装路径不是普通目录，停止安装。'
        }
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill 'SKILL.md') -PathType Leaf)) {
    throw '请保留完整仓库目录，从仓库根目录运行install.ps1。'
}
if ($sourceSkill -eq $targetSkillPath -or $sourceSkill.StartsWith($targetSkillPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '源目录不能是已安装技能，请从独立的下载副本运行。'
}
if ($targetSkillPath.StartsWith($sourceSkill + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw '安装目标不能位于源技能内部。'
}
Assert-RegularTree $targetSkillPath
$stagePath = Join-Path $skillHomePath ('.mcd-budget-meal-stage-' + [guid]::NewGuid().ToString('N'))
Assert-Contained $stagePath $skillHomePath
Copy-Package $sourceSkill $stagePath
# Keep user records separate from versioned package files, in both backup and new installation.
$oldPrivate = Join-Path $targetSkillPath 'private'
if (Test-Path -LiteralPath $oldPrivate) {
    if (-not (Test-Path -LiteralPath $oldPrivate -PathType Container)) { throw 'private不是目录，未替换原技能。' }
    Copy-Item -LiteralPath $oldPrivate -Destination (Join-Path $stagePath 'private') -Recurse
}
$backupSkillPath = $null
if (Test-Path -LiteralPath $targetSkillPath) {
    New-Item -ItemType Directory -Path $backupRootPath -Force | Out-Null
    $backupSkillPath = Join-Path $backupRootPath ('mcd-budget-meal-' + [guid]::NewGuid().ToString('N'))
    Assert-Contained $backupSkillPath $backupRootPath
    # Move the complete old installation to a recoverable backup; never recursively delete it.
    Move-Item -LiteralPath $targetSkillPath -Destination $backupSkillPath
}
try {
    Move-Item -LiteralPath $stagePath -Destination $targetSkillPath
} catch {
    if ($backupSkillPath -and -not (Test-Path -LiteralPath $targetSkillPath)) {
        Move-Item -LiteralPath $backupSkillPath -Destination $targetSkillPath
    }
    throw '新技能替换未完成；原技能已保留或恢复，暂存目录保留供检查。'
}
Write-Host ('技能已安装到：' + $targetSkillPath)
if ($backupSkillPath) { Write-Host ('原技能完整备份：' + $backupSkillPath) }
Write-Host '请新开WorkBuddy会话。安装不读取Token、不改连接器；旧private记录已保留。'
[pscustomobject]@{ TargetPath = $targetSkillPath; BackupPath = $backupSkillPath }
