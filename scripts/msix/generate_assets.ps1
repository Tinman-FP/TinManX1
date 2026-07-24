# Generates the MSIX package logo assets from the TinManX1 master bitmap
# (resources\images\TinManX1_1024.png). Each PNG is rendered at its exact target
# size and preserves alpha transparency in the corners.
#
# Run once locally on Windows (re-run only if the logo changes), then commit
# the PNGs in assets/. CI never runs this script.
#
# Prerequisite: Python 3 with Pillow (pip install pillow).
param(
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$source   = Join-Path $repoRoot 'resources\images\TinManX1_1024.png'
$outDir   = Join-Path $PSScriptRoot 'assets'
New-Item -ItemType Directory -Force $outDir | Out-Null

$sizes = [ordered]@{
    'Square150x150Logo.png'                              = 150
    'Square44x44Logo.png'                                = 44
    'Square44x44Logo.targetsize-44_altform-unplated.png' = 44
    'StoreLogo.png'                                      = 50
}

$py = @'
import sys
from pathlib import Path

from PIL import Image

source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
image = Image.open(source).convert('RGBA')
for spec in sys.argv[3:]:
    name, px = spec.rsplit('=', 1)
    px = int(px)
    resized = image.resize((px, px), Image.Resampling.LANCZOS)
    resized.save(out_dir / name)
    print(f'Wrote {name} ({px}x{px})')
'@

$renderScript = Join-Path $env:TEMP 'tinmanx1_msix_render.py'
Set-Content -Path $renderScript -Value $py -Encoding utf8
try {
    $specs = foreach ($name in $sizes.Keys) { "$name=$($sizes[$name])" }
    & $Python $renderScript $source $outDir @specs
    if ($LASTEXITCODE -ne 0) {
        throw 'MSIX asset render failed. Is Pillow installed? (pip install pillow)'
    }
}
finally {
    Remove-Item $renderScript -ErrorAction SilentlyContinue
}
