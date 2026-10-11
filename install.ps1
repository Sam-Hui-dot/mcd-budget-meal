param()
$ErrorActionPreference = 'Stop'
$sourceSkill = Join-Path $PSScriptRoot 'skills\mcd-budget-meal'
$userProfilePath = [Environment]::GetFolderPath('UserProfile')
$skillHomePath = [IO.Path]::GetFullPath((Join-Path $userProfilePath '.workbuddy\skills'))
$targetSkillPath = [IO.Path]::GetFullPath((Join-Path $skillHomePath 'mcd-budget-meal'))
if (-not $targetSkillPath.StartsWith($skillHomePath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw '安装目录超出 WorkBuddy 用户技能目录。'
}
if (-not (Test-Path -LiteralPath (Join-Path $sourceSkill 'SKILL.md'))) {
    throw '请保留完整仓库目录，从仓库根目录运行 install.ps1。'
}
if ([IO.Path]::GetFullPath($sourceSkill) -eq $targetSkillPath) {
    throw '源目录与目标目录相同；请从下载的仓库副本运行。'
}
# Never follow an existing directory junction into another location.
foreach ($installPath in @((Join-Path $userProfilePath '.workbuddy'), $skillHomePath, $targetSkillPath)) {
    if (Test-Path -LiteralPath $installPath) {
        $existingPathItem = Get-Item -LiteralPath $installPath -Force
        if ($existingPathItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw '安装路径包含链接目录，请使用普通 WorkBuddy 用户目录。'
        }
    }
}
if (Test-Path -LiteralPath $targetSkillPath) {
    $backupRootPath = Join-Path $userProfilePath '.workbuddy\skill-backups'
    New-Item -ItemType Directory -Path $backupRootPath -Force | Out-Null
    $backupSkillPath = Join-Path $backupRootPath ('mcd-budget-meal-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    Copy-Item -LiteralPath $targetSkillPath -Destination $backupSkillPath -Recurse
    Write-Host ('原技能已备份到：' + $backupSkillPath)
}
New-Item -ItemType Directory -Path $targetSkillPath -Force | Out-Null
foreach ($sourcePart in (Get-ChildItem -LiteralPath $sourceSkill -Force)) {
    Copy-Item -LiteralPath $sourcePart.FullName -Destination $targetSkillPath -Recurse -Force
}
Write-Host ('技能已安装到：' + $targetSkillPath)
Write-Host '请新开 WorkBuddy 会话，输入“预算30元，想吃汉堡和饮料”。'
Write-Host '安装仅复制技能文件，不安装 Python、不配置连接器、不读取 Token。'
