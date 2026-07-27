# Deployment Guide

## Prerequisites
- Docker and Docker Compose installed
- Production server with Linux OS
- Domain name and SSL certificates
- Database backups configured

## Docker Deployment

### Docker Compose Setup

Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_DATABASE: ai_lead_db
    volumes:
      - ./database/migrations:/docker-entrypoint-initdb.d
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      FLASK_ENV: production
      DATABASE_URL: mysql+pymysql://${MYSQL_USER}:${MYSQL_PASSWORD}@mysql:3306/ai_lead_db
      SECRET_KEY: ${SECRET_KEY}
    ports:
      - "5000:5000"
    depends_on:
      - mysql

  web:
    build:
      context: ./web
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    depends_on:
      - backend

volumes:
  mysql_data:
```

### Build and Deploy

```bash
# Build images
docker-compose -f docker-compose.prod.yml build

# Start services
docker-compose -f docker-compose.prod.yml up -d

# View logs
docker-compose -f docker-compose.prod.yml logs -f
```

## Manual Deployment

### Backend (Gunicorn + Nginx)

1. **Setup Gunicorn**
   ```bash
   cd backend
   gunicorn --workers 4 --threads 2 --worker-class gthread \
     --bind 0.0.0.0:5000 --timeout 60 \
     --access-logfile - --error-logfile - \
     wsgi:app
   ```

2. **Setup Nginx**
   ```nginx
   upstream backend {
       server 127.0.0.1:5000;
   }

   server {
       listen 80;
       server_name api.yourdomain.com;

       location / {
           proxy_pass http://backend;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Frontend (Static Hosting)

1. **Build React app**
   ```bash
   cd web
   npm run build
   ```

2. **Deploy to CDN or web server**
   ```bash
   aws s3 sync build/ s3://your-bucket/
   ```

## Environment Configuration

### Production .env
```
FLASK_ENV=production
DEBUG=False

DATABASE_URL=mysql+pymysql://user:password@db-host:3306/ai_lead_db
SECRET_KEY=your-strong-secret-key

JWT_SECRET_KEY=your-strong-jwt-secret
JWT_ALGORITHM=HS256

API_URL=https://api.yourdomain.com
REACT_APP_API_URL=https://api.yourdomain.com

ALLOWED_HOSTS=yourdomain.com,api.yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

## SSL/TLS Setup

### Using Let's Encrypt with Certbot

```bash
# Install Certbot
apt-get install certbot python3-certbot-nginx

# Generate certificate
certbot certonly --nginx -d yourdomain.com

# Auto-renewal
certbot renew --dry-run
```

## Database Backup Strategy

### Automated Backups

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR="/backups"
DB_NAME="ai_lead_db"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mysqldump -u root -p${MYSQL_PASSWORD} ${DB_NAME} | gzip > ${BACKUP_DIR}/backup_${TIMESTAMP}.sql.gz

# Keep only last 7 days of backups
find ${BACKUP_DIR} -name "backup_*.sql.gz" -mtime +7 -delete
```

Add to crontab:
```
0 2 * * * /path/to/backup.sh
```

## Monitoring

### Health Checks

```bash
# Check API health
curl -f https://api.yourdomain.com/api/health

# Check database
mysql -u user -p${PASSWORD} -h db-host -e "SELECT 1"
```

### Logging

- Backend logs to `/var/log/ai-lead/app.log`
- Database logs to `/var/log/mysql/error.log`
- Nginx logs to `/var/log/nginx/`

## Performance Optimization

1. **Enable caching**
   - Redis for session storage
   - Browser caching headers

2. **Database optimization**
   - Query optimization
   - Index maintenance
   - Connection pooling

3. **Frontend optimization**
   - Minify and bundle assets
   - Enable gzip compression
   - Use CDN for static files

## Security Checklist

- [ ] SSL/TLS certificates configured
- [ ] Firewall rules configured
- [ ] SSH keys configured
- [ ] Regular security updates
- [ ] Database encryption
- [ ] Environment variables protected
- [ ] API rate limiting enabled
- [ ] CORS properly configured
- [ ] SQL injection prevention verified
- [ ] Regular security audits scheduled

## Rollback Procedure

1. Stop current services
2. Restore database backup
3. Revert to previous version
4. Verify functionality

```bash
# Stop services
docker-compose down

# Restore database
mysql -u root -p < backup_20260328_020000.sql

# Start services
docker-compose up -d
```

## Troubleshooting

### High Memory Usage
- Check for memory leaks
- Optimize database queries
- Scale horizontally

### Database Connection Issues
- Check connection pooling limits
- Verify credentials
- Check network connectivity

### API Timeouts
- Increase timeout values
- Optimize slow queries
- Add caching
- Scale horizontally
