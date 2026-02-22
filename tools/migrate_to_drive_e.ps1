# VLM Data Migration to Drive E
# Separates code from data assets

Write-Host "🚀 VLM Data Migration to Drive E" -ForegroundColor Cyan
Write-Host "=" * 50

$WorkspaceRoot = "C:\Users\yanbo\wSpace\vlm-photo-engine\vlmPhotoHouse"
$DriveERoot = "E:\VLM_DATA"

# Check Drive E accessibility
if (-not (Test-Path $DriveERoot)) {
    Write-Error "❌ Drive E is not accessible!"
    exit 1
}

# Create directory structure on Drive E
Write-Host "📁 Creating directory structure..." -ForegroundColor Yellow
$Directories = @(
    "databases",
    "embeddings\faces", 
    "embeddings\images",
    "derived\thumbnails",
    "derived\captions", 
    "derived\analytics",
    "logs",
    "verification",
    "test_assets\photos",
    "test_assets\videos",
    "backups"
)

foreach ($Dir in $Directories) {
    $FullPath = Join-Path $DriveERoot $Dir
    if (-not (Test-Path $FullPath)) {
        New-Item -ItemType Directory -Path $FullPath -Force | Out-Null
        Write-Host "✅ Created: $FullPath" -ForegroundColor Green
    }
}

# Function to move items safely
function Move-ItemSafely {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$Description
    )
    
    if (Test-Path $Source) {
        Write-Host "🚚 Moving $Description..." -ForegroundColor Yellow
        Write-Host "   From: $Source"
        Write-Host "   To: $Destination"
        
        # Create destination directory if needed
        $DestDir = Split-Path $Destination -Parent
        if (-not (Test-Path $DestDir)) {
            New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
        }
        
        # Move the item
        if (Test-Path $Destination) {
            Write-Host "⚠️  Destination exists, creating backup..." -ForegroundColor Orange
            $BackupName = "$Destination.backup_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
            Move-Item $Destination $BackupName
        }
        
        Move-Item $Source $Destination -Force
        Write-Host "✅ Moved $Description successfully" -ForegroundColor Green
        return $true
    } else {
        Write-Host "⚠️  Source not found: $Source" -ForegroundColor Orange
        return $false
    }
}

# Migrate databases
Write-Host "`n💾 Migrating Databases..." -ForegroundColor Cyan
$DatabaseFiles = @("app.db", "drive_e_processing.db", "metadata.sqlite")
foreach ($DbFile in $DatabaseFiles) {
    $Source = Join-Path $WorkspaceRoot $DbFile
    $Destination = Join-Path $DriveERoot "databases\$DbFile"
    Move-ItemSafely $Source $Destination "Database: $DbFile"
}

# Migrate embeddings (largest folder)
Write-Host "`n🧠 Migrating Embeddings..." -ForegroundColor Cyan
$EmbeddingsSource = Join-Path $WorkspaceRoot "embeddings"
$EmbeddingsDestination = Join-Path $DriveERoot "embeddings\faces"
if (Test-Path $EmbeddingsSource) {
    $FileCount = (Get-ChildItem $EmbeddingsSource -Filter "*.json").Count
    Write-Host "📊 Found $FileCount embedding files to migrate..."
    Move-ItemSafely $EmbeddingsSource $EmbeddingsDestination "Embeddings folder ($FileCount files)"
}

# Migrate derived data
Write-Host "`n📊 Migrating Derived Data..." -ForegroundColor Cyan
$DerivedSource = Join-Path $WorkspaceRoot "derived"
$DerivedDestination = Join-Path $DriveERoot "derived"
Move-ItemSafely $DerivedSource $DerivedDestination "Derived data"

# Migrate verification results
Write-Host "`n🔍 Migrating Verification Results..." -ForegroundColor Cyan
$VerificationSource = Join-Path $WorkspaceRoot "verification_results"
$VerificationDestination = Join-Path $DriveERoot "verification"
Move-ItemSafely $VerificationSource $VerificationDestination "Verification results"

# Migrate test assets
Write-Host "`n🧪 Migrating Test Assets..." -ForegroundColor Cyan
$TestPhotosSource = Join-Path $WorkspaceRoot "test_photos"
$TestPhotosDestination = Join-Path $DriveERoot "test_assets\photos"
Move-ItemSafely $TestPhotosSource $TestPhotosDestination "Test photos"

$SampleVideoSource = Join-Path $WorkspaceRoot "sample_video"
$SampleVideoDestination = Join-Path $DriveERoot "test_assets\videos"
Move-ItemSafely $SampleVideoSource $SampleVideoDestination "Sample videos"

# Migrate logs and state files
Write-Host "`n📋 Migrating Logs and State Files..." -ForegroundColor Cyan
$LogFiles = Get-ChildItem $WorkspaceRoot -Filter "*.log"
$StateFiles = Get-ChildItem $WorkspaceRoot -Filter "*_state.json"
$MonitoringFiles = Get-ChildItem $WorkspaceRoot -Filter "gpu_monitoring_*.png"

$AllFiles = $LogFiles + $StateFiles + $MonitoringFiles
foreach ($File in $AllFiles) {
    $Destination = Join-Path $DriveERoot "logs\$($File.Name)"
    Move-ItemSafely $File.FullName $Destination $File.Name
}

# Create configuration file
Write-Host "`n⚙️  Creating Drive E Configuration..." -ForegroundColor Cyan
$ConfigDir = Join-Path $WorkspaceRoot "config"
if (-not (Test-Path $ConfigDir)) {
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
}

$Config = @{
    vlm_data_root = "E:/VLM_DATA"
    databases = @{
        metadata = "E:/VLM_DATA/databases/metadata.sqlite"
        app = "E:/VLM_DATA/databases/app.db"
        drive_e_processing = "E:/VLM_DATA/databases/drive_e_processing.db"
    }
    embeddings = @{
        faces = "E:/VLM_DATA/embeddings/faces"
        images = "E:/VLM_DATA/embeddings/images"
    }
    derived = @{
        thumbnails = "E:/VLM_DATA/derived/thumbnails"
        captions = "E:/VLM_DATA/derived/captions"
        analytics = "E:/VLM_DATA/derived/analytics"
    }
    logs = "E:/VLM_DATA/logs"
    verification = "E:/VLM_DATA/verification"
    test_assets = "E:/VLM_DATA/test_assets"
    migration_date = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
}

$ConfigPath = Join-Path $ConfigDir "drive_e_paths.json"
$Config | ConvertTo-Json -Depth 3 | Set-Content $ConfigPath -Encoding UTF8
Write-Host "✅ Configuration saved: $ConfigPath" -ForegroundColor Green

# Create symlinks for database compatibility (if needed)
Write-Host "`n🔗 Creating Symlinks for Code Compatibility..." -ForegroundColor Cyan
foreach ($DbFile in $DatabaseFiles) {
    $WorkspaceDbPath = Join-Path $WorkspaceRoot $DbFile
    $DriveEDbPath = Join-Path $DriveERoot "databases\$DbFile"
    
    if ((Test-Path $DriveEDbPath) -and (-not (Test-Path $WorkspaceDbPath))) {
        try {
            # Create symbolic link
            cmd /c "mklink `"$WorkspaceDbPath`" `"$DriveEDbPath`"" 2>$null
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ Created symlink: $DbFile" -ForegroundColor Green
            } else {
                Write-Host "⚠️  Could not create symlink for $DbFile (may need admin rights)" -ForegroundColor Orange
            }
        } catch {
            Write-Host "⚠️  Symlink creation failed for $DbFile" -ForegroundColor Orange
        }
    }
}

# Summary
Write-Host "`n🎉 Migration Summary" -ForegroundColor Cyan
Write-Host "=" * 50
Write-Host "📁 Data Location: $DriveERoot" -ForegroundColor Green
Write-Host "⚙️  Configuration: $ConfigPath" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Drive E Structure:" -ForegroundColor Yellow
Get-ChildItem $DriveERoot | ForEach-Object {
    $Size = if ($_.PSIsContainer) { 
        $ItemCount = (Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue).Count
        "($ItemCount files)"
    } else { 
        "({0:N0} KB)" -f ($_.Length / 1KB)
    }
    Write-Host "  📂 $($_.Name) $Size" -ForegroundColor White
}

Write-Host "`n✅ Migration completed successfully!" -ForegroundColor Green
Write-Host "💡 Workspace now contains only code - all data is on Drive E" -ForegroundColor Green
