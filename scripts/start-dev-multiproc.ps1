# Retired in the protected-access release; parameter compatibility only.
param(
    [string]$LvfaceDir = '',
    [string]$CaptionDir = '',
    [string]$RamppDir = '',
    [string]$VoiceDir = '',
    [string]$LvfaceModelName = '',
    [int]$ApiPort = 8002,
    [string]$ApiHost = '127.0.0.1',
    [int]$RamppPort = 8112,
    [int]$VoicePort = 8001,
    [bool]$EnableRampp = $true,
    [string]$CaptionProvider = 'qwen3-vl',
    [string]$FaceProvider = 'lvface',
    [string]$DbPath = 'E:\VLM_DATA\databases\metadata.sqlite',
    [string]$DataRoot = 'E:\VLM_DATA',
    [string]$OriginalsPath = 'E:\01_INCOMING',
    [string]$Preset, # Optional: LowVRAM | RTX3090
    [switch]$Gpu,
    [switch]$UseWindowsTerminal,
    [switch]$KillExisting,  # Retained only for a clear retirement error
    [switch]$NoCleanup,     # Retained only for a clear retirement error
    [switch]$TailscaleAccess,
    [switch]$PreflightOnly
)

throw 'Legacy combined launcher retired. Use scripts/staging_app.py with explicit private configuration after following docs/security/PROTECTED_UPGRADE.md. No runtime action was performed.'
