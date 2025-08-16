# Operations & Maintenance

This section contains operational guides for running and maintaining the VLM Photo Engine.

## 📋 Operations Guides

### Daily Operations
- **[Operations Runbook](./operations.md)** - Start/stop, monitoring, troubleshooting

## 🚀 Quick Operations

### Start/Stop Services

**Docker Deployment**
```bash
cd deploy

# Start all services
docker compose up -d

# Stop all services
docker compose down

# Restart specific service
docker compose restart api

# View logs
docker compose logs -f api
```

**Development Mode**
```bash
cd vlmPhotoHouse
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

cd backend
python -m app.main
```

### Health Monitoring

**System Health**
```bash
# Overall system status
curl http://localhost:8001/health

# Detailed component status
curl http://localhost:8001/health/caption
curl http://localhost:8001/health/lvface
curl http://localhost:8001/health/database
```

**Response Examples**
```json
{
  "status": "healthy",
  "timestamp": "2025-08-16T10:30:00Z",
  "components": {
    "database": "healthy",
    "caption_models": "healthy", 
    "face_recognition": "healthy",
    "vector_index": "healthy"
  },
  "metrics": {
    "photos_indexed": 1234,
    "captions_generated": 890,
    "faces_detected": 567
  }
}
```

## 📊 Monitoring

### Key Metrics

**Performance Metrics**
- Search response time (<500ms target)
- Caption generation time
- Face detection accuracy
- Indexing throughput

**System Metrics**
- GPU utilization
- Memory usage
- Disk usage (models + derived data)
- Database size and performance

**Business Metrics**
- Photos processed per day
- Search queries per day
- Person recognition accuracy
- User engagement

### Logging

**Log Locations**
```bash
# Docker deployment
docker logs vlm-api
docker logs vlm-worker
docker logs vlm-nginx

# Development mode
tail -f backend/logs/app.log
tail -f backend/logs/worker.log
```

**Log Levels**
- `ERROR`: System errors requiring attention
- `WARN`: Potential issues to monitor
- `INFO`: Normal operations, key events
- `DEBUG`: Detailed debugging information

### Alerting

**Critical Alerts**
- System health check failures
- Database connection errors
- Model loading failures
- Disk space low (<10% free)

**Warning Alerts**
- Slow search performance (>1s)
- High GPU memory usage (>90%)
- Task queue backlog (>100 items)
- Failed photo processing

## 🔧 Maintenance Tasks

### Daily Tasks

**Health Checks**
```bash
# Run health verification
curl http://localhost:8001/health

# Check disk usage
df -h /opt/vlm-photo-engine
df -h /mnt/photos

# Monitor task queue
curl http://localhost:8001/tasks/status
```

**Log Review**
```bash
# Check for errors
docker logs vlm-api | grep ERROR

# Monitor performance
docker logs vlm-api | grep "slow_query"
```

### Weekly Tasks

**Database Maintenance**
```bash
# SQLite optimization
sqlite3 app.db "VACUUM;"
sqlite3 app.db "ANALYZE;"

# Check database size
du -h app.db
```

**Model Cache Cleanup**
```bash
# Clear temporary model files
cd vlmCaptionModels
rm -rf temp/
rm -rf __pycache__/
```

**Backup Verification**
```bash
# Test backup restore
cp backup/app-latest.sqlite test_restore.sqlite
sqlite3 test_restore.sqlite ".tables"
```

### Monthly Tasks

**Performance Review**
```bash
# Generate performance report
curl http://localhost:8001/admin/performance_report

# Review slow queries
sqlite3 app.db "SELECT * FROM slow_queries ORDER BY duration DESC LIMIT 10;"
```

**Security Updates**
```bash
# Update container images
docker compose pull
docker compose up -d

# Update Python dependencies
pip install --upgrade -r requirements.txt
```

**Capacity Planning**
```bash
# Check growth trends
sqlite3 app.db "SELECT COUNT(*) FROM assets;"
du -h derived/

# Plan storage expansion if needed
```

## 🚨 Troubleshooting

### Common Issues

**Service Won't Start**
```bash
# Check port conflicts
netstat -tulpn | grep 8001

# Check Docker status
docker ps -a
docker logs vlm-api

# Check file permissions
ls -la /opt/vlm-photo-engine
```

**Slow Performance**
```bash
# Check GPU usage
nvidia-smi

# Check memory usage
free -h
docker stats

# Check database performance
sqlite3 app.db "EXPLAIN QUERY PLAN SELECT * FROM assets WHERE caption LIKE '%sunset%';"
```

**Model Loading Failures**
```bash
# Check model files
ls -la vlmCaptionModels/models/

# Test model loading
cd vlmCaptionModels
.venv/bin/activate
python scripts/test_model_loading.py

# Clear model cache
rm -rf models/ && python scripts/download_models.py
```

**Search Not Working**
```bash
# Check vector index
curl http://localhost:8001/health/vector_index

# Rebuild index if needed
curl -X POST http://localhost:8001/admin/rebuild_index

# Check embedding generation
curl http://localhost:8001/health/embeddings
```

### Emergency Procedures

**System Recovery**
```bash
# Stop all services
docker compose down

# Check system resources
df -h
free -h
nvidia-smi

# Start with minimal services
docker compose up -d api
```

**Database Recovery**
```bash
# Restore from backup
cp backup/app-latest.sqlite app.db

# Verify database integrity
sqlite3 app.db "PRAGMA integrity_check;"

# Rebuild indexes
sqlite3 app.db "REINDEX;"
```

**Complete Reset**
```bash
# WARNING: This will delete all processed data
docker compose down
rm -rf derived/
rm app.db
docker compose up -d

# Re-scan photos
curl -X POST http://localhost:8001/ingest/scan
```

## 📈 Performance Optimization

### GPU Optimization
```bash
# Monitor GPU memory
nvidia-smi --query-gpu=memory.used,memory.total --format=csv

# Optimize batch sizes
export CAPTION_BATCH_SIZE=4
export FACE_BATCH_SIZE=8
```

### Database Optimization
```sql
-- SQLite performance tuning
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=20000;
PRAGMA temp_store=memory;

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_assets_caption ON assets(caption);
CREATE INDEX IF NOT EXISTS idx_assets_date ON assets(taken_at);
```

### Storage Optimization
```bash
# Use fast storage for temporary files
export TEMP_DIR=/tmp/vlm_temp

# Optimize photo access
mount -o ro,noatime /mnt/photos /opt/photos

# Clean up old thumbnails
find derived/thumbnails -type f -mtime +30 -delete
```

## 🔄 Backup & Recovery

### Backup Strategy
```bash
#!/bin/bash
# backup.sh - Daily backup script

DATE=$(date +%Y%m%d)
BACKUP_DIR="/backup/$DATE"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
cp app.db "$BACKUP_DIR/app.db"

# Backup configuration
cp .env "$BACKUP_DIR/.env"

# Backup derived data (if needed)
# rsync -av derived/ "$BACKUP_DIR/derived/"

# Clean old backups (keep 30 days)
find /backup -type d -mtime +30 -exec rm -rf {} \;
```

### Recovery Procedures
```bash
# Restore from backup
RESTORE_DATE="20250815"
cp "/backup/$RESTORE_DATE/app.db" ./app.db
cp "/backup/$RESTORE_DATE/.env" ./.env

# Restart services
docker compose down
docker compose up -d

# Verify recovery
curl http://localhost:8001/health
```

---

*For detailed troubleshooting procedures, see the operations runbook.*
