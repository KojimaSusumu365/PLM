$ErrorActionPreference = 'Stop'
$releasePath = Join-Path $PSScriptRoot '..\outputs\PLM-L1-SS-active-v0.3'
if (Test-Path -LiteralPath $releasePath) { throw 'Release already exists' }
New-Item -ItemType Directory -Path $releasePath | Out-Null
foreach ($folder in @('ss_trace','ss_multicode','evaluation','tests','verification','data','examples')) {
    New-Item -ItemType Directory -Path (Join-Path $releasePath $folder) | Out-Null
}
$sourcePath = Join-Path $PSScriptRoot '..\outputs\PLM-L1-SS-active-v0.2'
Copy-Item -LiteralPath (Join-Path $sourcePath 'ss_multicode\algebra.py'),(Join-Path $sourcePath 'ss_multicode\model.py'),(Join-Path $sourcePath 'ss_multicode\learning.py'),(Join-Path $sourcePath 'ss_multicode\__init__.py') -Destination (Join-Path $releasePath 'ss_multicode')
Copy-Item -LiteralPath (Join-Path $sourcePath 'requirements.txt') -Destination $releasePath
