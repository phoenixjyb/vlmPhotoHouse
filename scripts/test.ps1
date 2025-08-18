param(
    [ValidateSet('unit','integration','all')]
    [string]$scope = 'unit'
)

$ErrorActionPreference = 'Stop'

# Activate local venv if present
$venvPython = Join-Path $PSScriptRoot '..' | Join-Path -ChildPath '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
  Write-Host "Using venv: $venvPython"
} else {
  Write-Host "No local venv found; falling back to python on PATH" -ForegroundColor Yellow
  $venvPython = 'python'
}

$pytestArgs = @()

switch ($scope) {
  'unit' { $pytestArgs = @('backend/tests','-m','not integration') }
  'integration' { $pytestArgs = @('integration_tests','-m','integration') }
  'all' {
    $pytestArgs = @('backend/tests','integration_tests')
    if ($env:RUN_INTEGRATION_TESTS -ne '1') {
      # When running all but env isn't set, still include both paths but filter out integration
      $pytestArgs += @('-m','not integration')
    }
  }
}

& $venvPython -m pytest @pytestArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
