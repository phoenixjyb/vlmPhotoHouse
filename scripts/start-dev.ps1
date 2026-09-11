# Retired in the protected-access release; parameter compatibility only.
param(
  [int]$Port = 8002,
  [Alias('Host')][string]$ApiHost = '127.0.0.1',
  [switch]$Reload
)

throw 'Legacy combined launcher retired. Use scripts/staging_app.py with explicit private configuration after following docs/security/PROTECTED_UPGRADE.md. No runtime action was performed.'
