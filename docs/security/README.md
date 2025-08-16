# Security & Privacy

This section contains security considerations and privacy protection measures for the VLM Photo Engine.

## 🔒 Security Overview

The VLM Photo Engine is designed with **privacy-first** and **local-first** principles:

### Core Security Principles
1. **Local Processing**: All AI processing happens on your hardware
2. **No Cloud Dependencies**: No data sent to external services
3. **Privacy by Design**: Personal photos never leave your network
4. **Minimal Attack Surface**: Runs locally with optional network access

## 📋 Security Guides

### Core Security
- **[Security Configuration](./security.md)** - Security setup and hardening

## 🛡️ Privacy Protection

### Data Handling
- **Photo Storage**: Originals remain in their original locations
- **Metadata**: Only extracted metadata stored in local database
- **AI Models**: Run locally without external API calls
- **Search Queries**: Processed locally, no external logging

### Personal Information
- **Face Recognition**: Face embeddings stored locally only
- **Captions**: Generated descriptions kept in local database
- **Search History**: Optional local logging only
- **User Behavior**: No tracking or analytics sent externally

### Data Retention
```bash
# Control data retention
KEEP_ORIGINAL_PHOTOS=true       # Never delete originals
KEEP_DERIVED_DATA=90_days       # Thumbnail/cache retention
KEEP_SEARCH_LOGS=30_days        # Optional search logging
```

## 🔧 Security Configuration

### Network Security

**Default Configuration (Secure)**
```bash
# Bind to localhost only
HOST=127.0.0.1
PORT=8001
CORS_ORIGINS=http://localhost:3000
```

**Remote Access (Advanced)**
```bash
# For remote access, use reverse proxy with authentication
HOST=0.0.0.0
CORS_ORIGINS=https://photos.yourdomain.com
```

### File System Security

**Permissions**
```bash
# Secure file permissions
chown -R vlm:vlm /opt/vlm-photo-engine
chmod 750 /opt/vlm-photo-engine
chmod 640 /opt/vlm-photo-engine/.env

# Read-only photo access
mount -o ro /mnt/photos /opt/photos
```

**Photo Storage**
```bash
# Original photos: read-only access
PHOTOS_READONLY=true

# Derived data: restricted write access  
DERIVED_PATH_OWNER=vlm:vlm
DERIVED_PATH_MODE=750
```

### Database Security

**SQLite (Default)**
```bash
# Database file permissions
chmod 640 app.db
chown vlm:vlm app.db

# Database encryption (optional)
SQLITE_ENCRYPTION_KEY=your_encryption_key
```

**PostgreSQL (Production)**
```bash
# Encrypted connections
DATABASE_URL=postgresql://user:pass@localhost/vlm?sslmode=require

# Role-based access
GRANT SELECT, INSERT, UPDATE ON assets TO vlm_api;
GRANT SELECT ON assets TO vlm_readonly;
```

## 🌐 Network Security

### Firewall Configuration

**Development (Local Only)**
```bash
# Block external access
ufw deny 8001
# Only allow localhost
iptables -A INPUT -p tcp --dport 8001 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8001 -j DROP
```

**Production (With Remote Access)**
```bash
# Allow specific networks only
ufw allow from 192.168.1.0/24 to any port 80
ufw allow from 192.168.1.0/24 to any port 443
```

### Reverse Proxy Security

**Nginx Configuration**
```nginx
server {
    listen 443 ssl http2;
    server_name photos.internal;
    
    # SSL/TLS configuration
    ssl_certificate /etc/ssl/certs/photos.crt;
    ssl_certificate_key /etc/ssl/private/photos.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    
    # Authentication (optional)
    auth_basic "VLM Photo Engine";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Authentication Options

**Basic Authentication**
```bash
# Create user
htpasswd -c /etc/nginx/.htpasswd username

# Nginx configuration
auth_basic "Restricted Area";
auth_basic_user_file /etc/nginx/.htpasswd;
```

**OAuth/OIDC (Advanced)**
```bash
# Using oauth2-proxy
oauth2_proxy \
  --provider=github \
  --client-id=your_client_id \
  --client-secret=your_client_secret \
  --cookie-secret=random_cookie_secret \
  --upstream=http://127.0.0.1:8001
```

## 🔍 Security Monitoring

### Audit Logging

**Enable Audit Logs**
```bash
AUDIT_LOGGING=true
AUDIT_LOG_PATH=/var/log/vlm/audit.log
LOG_LEVEL=INFO
```

**Monitored Events**
- User authentication attempts
- Administrative actions
- Photo access patterns
- System configuration changes
- Failed API requests

### Security Monitoring

**Log Analysis**
```bash
# Monitor failed requests
grep "401\|403\|500" /var/log/vlm/access.log

# Check authentication failures
grep "auth_failed" /var/log/vlm/audit.log

# Monitor unusual activity
grep "unusual_access_pattern" /var/log/vlm/security.log
```

**Alerting**
```bash
# Critical security events
SECURITY_ALERTS_EMAIL=admin@yourdomain.com
ALERT_ON_FAILED_AUTH=true
ALERT_ON_UNUSUAL_ACCESS=true
```

## 🔒 Data Protection

### Encryption

**At Rest Encryption**
```bash
# Database encryption
SQLITE_ENCRYPTION=true
ENCRYPTION_KEY_FILE=/secure/encryption.key

# File system encryption
cryptsetup luksFormat /dev/sdb1
mount /dev/mapper/vlm-encrypted /opt/vlm-secure
```

**In Transit Encryption**
```bash
# HTTPS only
FORCE_HTTPS=true
SSL_REDIRECT=true

# API encryption
TLS_VERSION=1.2
CIPHER_SUITES=ECDHE-RSA-AES256-GCM-SHA384
```

### Backup Security

**Secure Backups**
```bash
# Encrypted backups
gpg --symmetric --cipher-algo AES256 app.db > backup.db.gpg

# Secure backup storage
rsync -av --delete backup/ user@secure-backup:/backups/vlm/
```

### Data Anonymization

**Optional Privacy Features**
```bash
# Face blurring for non-family members
BLUR_UNKNOWN_FACES=true

# Metadata scrubbing
REMOVE_GPS_DATA=true
REMOVE_CAMERA_INFO=false

# Search query anonymization
ANONYMIZE_SEARCH_LOGS=true
```

## 🚨 Security Incident Response

### Incident Detection

**Automated Detection**
```bash
# Monitor for unusual patterns
python scripts/security_monitor.py

# Check for unauthorized access
grep "unauthorized" /var/log/vlm/security.log
```

### Response Procedures

**Security Incident Response**
1. **Detect**: Monitor logs and alerts
2. **Isolate**: Disconnect from network if needed
3. **Investigate**: Analyze logs and system state
4. **Remediate**: Apply fixes and patches
5. **Recover**: Restore from secure backups
6. **Learn**: Update security measures

**Emergency Shutdown**
```bash
# Immediate shutdown
docker compose down
systemctl stop vlm-photo-engine

# Network isolation
iptables -A INPUT -j DROP
iptables -A OUTPUT -j DROP
```

## 📚 Security Best Practices

### Development Security
- Regular dependency updates
- Security code reviews
- Vulnerability scanning
- Secure coding practices

### Operational Security
- Regular backup testing
- Security monitoring
- Access logging
- Incident response planning

### User Security
- Strong authentication
- Principle of least privilege
- Regular access reviews
- Security awareness training

## 🔄 Compliance

### Privacy Regulations

**GDPR Compliance**
- Local processing (no data transfer)
- Right to erasure (delete user data)
- Data minimization (only necessary data)
- Privacy by design (built-in privacy)

**Data Handling**
```bash
# User data deletion
python scripts/delete_user_data.py --user_id=123

# Data export
python scripts/export_user_data.py --user_id=123

# Anonymization
python scripts/anonymize_data.py --before_date=2024-01-01
```

---

*For detailed security configurations, see the security guide referenced above.*
