# Retired in the protected-access release; parameter compatibility only.
[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [ValidateRange(30, 600)]
    [int]$CaptionTimeoutSec = 180
)

throw 'Legacy combined launcher retired. Use scripts/staging_app.py with explicit private configuration after following docs/security/PROTECTED_UPGRADE.md. No runtime action was performed.'
