# Deployment Documentation

This section contains deployment guides for production environments.

## 🚀 Deployment Options

### 1. Development/Single User
- **[Local Development Setup](../setup/README.md)** - Development environment
- Single machine, local storage
- Ideal for: Personal use, development, testing

### 2. Hybrid Workstation + NAS
- **[Hybrid Deployment](./deployment.md)** - WSL2 + Docker + NVIDIA
- Local compute with network storage
- Ideal for: Power users, small teams

### 3. Production Server
- **[Production Deployment](./deployment-profiles.md)** - Dedicated server deployment
- Dedicated hardware, redundant storage
- Ideal for: Families, small organizations

## 📋 Deployment Guides

### Docker Deployment
- **[Docker Deployment](./deployment.md)** - Complete Docker Compose setup
- **[Deployment Profiles](./deployment-profiles.md)** - Different deployment scenarios

## 🏗️ Infrastructure Requirements

### Minimum Requirements
- **CPU**: 8+ cores (Intel/AMD x64)
- **RAM**: 16+ GB
- **Storage**: 50+ GB fast storage (SSD)
- **GPU**: NVIDIA GPU with 8+ GB VRAM (recommended)
- **Network**: Gigabit for photo access

### Recommended Production
- **CPU**: 16+ cores, 3.0+ GHz
- **RAM**: 32+ GB
- **Storage**: 
  - 100+ GB NVMe SSD (application/database)
  - Network storage for photos (TB+ capacity)
- **GPU**: RTX 3090/4090 or equivalent
- **Network**: 10Gb for high-throughput photo access

## 🐳 Docker Deployment

### Quick Start
```bash
# Clone repository
git clone https://github.com/phoenixjyb/vlmPhotoHouse.git
cd vlmPhotoHouse/deploy

# Configure environment
cp env.sample .env
# Edit .env with your paths and settings

# Deploy
docker compose up -d
```

### Environment Configuration
```bash
# Core paths
PHOTOS_PATH=/mnt/nas/photos
DERIVED_PATH=/opt/vlm/derived
DATABASE_URL=sqlite:////data/app.sqlite

# GPU configuration
API_GPU=0                    # Primary GPU for inference
NVIDIA_VISIBLE_DEVICES=all   # Make all GPUs available

# Worker configuration  
WORKER_CONCURRENCY=2
ENABLE_INLINE_WORKER=true

# External models
EXTERNAL_CAPTION_ENABLED=true
CAPTION_PROVIDER=blip2
FACE_PROVIDER=lvface
```

### Docker Compose Services
```yaml
services:
  api:
    # FastAPI backend + task queue
    ports: ["8001:8001"]
    
  nginx:
    # Reverse proxy + static files
    ports: ["80:80"]
    
  # Future: separate worker containers
  # worker:
  #   # Background task processing
```

## 🔧 Production Configuration

### Database
```bash
# SQLite (default, single-user)
DATABASE_URL=sqlite:////data/app.sqlite

# PostgreSQL (recommended for production)
DATABASE_URL=postgresql://user:pass@localhost/vlm_photos
```

### Storage Layout
```bash
# Application data
/opt/vlm-photo-engine/
├── vlmPhotoHouse/      # Backend application
├── vlmCaptionModels/   # AI models (20.96 GB)
└── data/               # Database, logs

# Photo storage (network mounted)
/mnt/photos/
├── originals/          # Original photos (read-only)
└── imports/            # New photo uploads

# Derived data (fast local storage)
/opt/vlm/derived/
├── thumbnails/         # Generated thumbnails
├── embeddings/         # Vector embeddings
└── metadata/           # Extracted metadata
```

### Security Configuration
```bash
# Network access
ALLOWED_HOSTS=localhost,192.168.1.100
CORS_ORIGINS=http://localhost:3000

# File permissions
chown -R vlm:vlm /opt/vlm-photo-engine
chmod 750 /opt/vlm-photo-engine

# Database permissions
chmod 640 /opt/vlm/data/app.sqlite
```

## 📊 Monitoring & Health

### Health Endpoints
```bash
# System health
curl http://localhost:8001/health

# Component health
curl http://localhost:8001/health/caption
curl http://localhost:8001/health/lvface
curl http://localhost:8001/health/database
```

### Logging
```bash
# Application logs
docker logs vlm-api

# Worker logs  
docker logs vlm-worker

# System logs
journalctl -u docker
```

### Metrics
```bash
# Basic metrics endpoint
curl http://localhost:8001/metrics

# Database size
du -h /opt/vlm/data/

# Model storage
du -h /opt/vlm-photo-engine/vlmCaptionModels/models/
```

## 🔄 Maintenance

### Backup Strategy
```bash
# Database backup
cp /opt/vlm/data/app.sqlite /backup/app-$(date +%Y%m%d).sqlite

# Configuration backup
tar -czf /backup/config-$(date +%Y%m%d).tar.gz /opt/vlm-photo-engine/.env

# Derived data backup (optional)
rsync -av /opt/vlm/derived/ /backup/derived/
```

### Updates
```bash
# Update application
cd /opt/vlm-photo-engine/vlmPhotoHouse
git pull
docker compose pull
docker compose up -d

# Update models (if needed)
cd /opt/vlm-photo-engine/vlmCaptionModels  
.venv/bin/activate
python scripts/update_models.py
```

### Scaling
```bash
# Add worker containers
docker compose up -d --scale worker=3

# Database migration to PostgreSQL
python scripts/migrate_to_postgres.py

# Storage expansion
# Add new photo sources to PHOTOS_PATH
# Expand derived storage volume
```

## 🔒 Security

### Network Security
- Run on internal network only by default
- Use reverse proxy (nginx) for external access
- Implement authentication for remote access
- Enable HTTPS/TLS for production

### File System Security
- Read-only access to photo storage
- Restricted write access to derived data
- Regular backup verification
- File integrity monitoring

### Application Security
- Regular dependency updates
- Security scanning of Docker images
- Audit logs for administrative actions
- Rate limiting for API endpoints

## 📈 Performance Tuning

### GPU Optimization
```bash
# Monitor GPU usage
nvidia-smi -l 1

# Optimize model loading
export CUDA_VISIBLE_DEVICES=0
export OMP_NUM_THREADS=4
```

### Storage Optimization
```bash
# Use fast storage for derived data
mount -t tmpfs -o size=4G tmpfs /opt/vlm/derived/temp

# Optimize photo storage access
mount -o ro,noatime /mnt/nas/photos /opt/photos
```

### Database Optimization
```sql
-- SQLite optimization
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=10000;
PRAGMA temp_store=memory;
```

---

*For specific deployment scenarios, see the individual deployment guides listed above.*
