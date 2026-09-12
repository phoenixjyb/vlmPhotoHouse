# Retired in the protected-access release; parameter compatibility only.
[CmdletBinding()]
param(
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [string]$DatabasePath = '',
    [string]$LvfaceDir = '',
    [string]$CaptionDir = '',
    [string]$CaptionProvider = 'http',
    [string]$CaptionServiceUrl = 'http://127.0.0.1:8102',
    [string]$LvfaceModelName = 'LVFace-B_Glint360K.onnx',
    [string]$EmbedDevice = 'cuda:0',
    [string]$CaptionDevice = 'cuda:0',
    [ValidateRange(1, 65535)]
    [int]$ApiPort = 8002,
    [ValidateRange(5, 600)]
    [int]$ReadyTimeoutSec = 120,
    [ValidateRange(1, 30)]
    [int]$HealthTimeoutSec = 5,
    [ValidateRange(1, 365)]
    [int]$LogRetention = 14,
    [switch]$DisableInlineWorker,
    [switch]$NoAutoMigrate,
    [switch]$Detached,
    [switch]$PreflightOnly
)

throw 'Legacy combined launcher retired. Use scripts/staging_app.py with explicit private configuration after following docs/security/PROTECTED_UPGRADE.md. No runtime action was performed.'
