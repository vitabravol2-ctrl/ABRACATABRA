Set-Location (Join-Path $PSScriptRoot "..")
python -m unittest discover -s tests
