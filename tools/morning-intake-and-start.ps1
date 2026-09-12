# Retired in the protected-access release; parameter compatibility only.
[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [string]$DatabasePath = '',
    [string]$LvfaceDir = '',
    [string]$CaptionDir = '',
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8002,
    [ValidateRange(1, 65535)]
    [int]$CaptionPort = 8102,
    [switch]$PreflightOnly
)

throw 'Legacy combined launcher retired. Use scripts/staging_app.py with explicit private configuration after following docs/security/PROTECTED_UPGRADE.md. No runtime action was performed.'
