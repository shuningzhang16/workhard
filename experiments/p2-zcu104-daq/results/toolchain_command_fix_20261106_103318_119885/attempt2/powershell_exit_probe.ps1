# README structure; only the native Vivado call is replaced by harmless exit(7).
$p2Root = (Get-Location).Path
$runDir = Join-Path $p2Root ("build\toolchain_" + (Get-Date -Format "yyyyMMdd_HHmmss_fff"))
if (Test-Path -LiteralPath $runDir) { throw "请选择全新输出目录：$runDir" }
New-Item -ItemType Directory -Path $runDir -ErrorAction Stop | Out-Null
Push-Location $runDir
try {
    & 'E:\python.exe' -B -c 'raise SystemExit(7)'
    $vivadoExitCode = $LASTEXITCODE
    if ($vivadoExitCode -ne 0) { throw "Vivado failed with exit code $vivadoExitCode; output retained: $runDir" }
} finally {
    Pop-Location
}
