$ErrorActionPreference='Stop'
$newPath=Join-Path $PSScriptRoot '..\outputs\PLM-L1-SS-doc-v0.1'
$oldPath=Join-Path $PSScriptRoot '..\outputs\PLM-L1-v0.9'
if (Test-Path -LiteralPath $newPath) { throw 'Release already exists' }
New-Item -ItemType Directory -Path $newPath | Out-Null
foreach ($name in @('ss_document','evaluation','data','tests','verification','examples')) {
    New-Item -ItemType Directory -Path (Join-Path $newPath $name) | Out-Null
}
Copy-Item -LiteralPath (Join-Path $oldPath 'plm_l1_v09') -Destination $newPath -Recurse
foreach ($name in @('component_train.json','temporal_train.json','lexicon.json','evaluation.json')) {
    Copy-Item -LiteralPath (Join-Path $oldPath ('data\'+$name)) -Destination (Join-Path $newPath 'data')
}
Copy-Item -LiteralPath (Join-Path $oldPath 'requirements.txt') -Destination $newPath
Copy-Item -LiteralPath (Join-Path $oldPath 'evaluation\oracle.py') -Destination (Join-Path $newPath 'evaluation\event_oracle.py')
