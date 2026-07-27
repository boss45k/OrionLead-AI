# Database Setup Guide

## MySQL Database Configuration

### Prerequisites
- MySQL Server 8.0 or higher installed
- MySQL command-line client or MySQL Workbench

### Quick Setup

1. **Login to MySQL:**
   ```bash
   mysql -u root -p
   ```

2. **Run initialization script:**
   ```bash
   mysql -u root -p < migrations/001_initial_schema.sql
   ```

3. **Load sample data (optional):**
   ```bash
   mysql -u root -p ai_lead_db < seeds/sample_data.sql
   ```

### Database Structure

#### Users Table
- Stores user account information
- Fields: id, email, password_hash, full_name, company, role, is_active, created_at, updated_at

#### Leads Table
- Central storage for all collected leads
- Fields: id, name, email, phone, company, position, interests, qualification_score, status, source, data_points, notes, created_at, updated_at
- Status: pending, active, qualified, contacted, converted
- Includes full-text search index on name and email

#### Lead Activities Table
- Tracks all interactions with leads
- Fields: id, lead_id, user_id, activity_type, notes, created_at
- Foreign keys to leads and users tables

#### Data Sources Table
- Manages web scraping data sources
- Fields: id, name, url, type, last_crawled, status, config

#### Classification Categories Table
- Stores interest categories and keywords
- Fields: id, name, description, keywords, created_at

### Backup and Restore

**Backup database:**
```bash
mysqldump -u root -p ai_lead_db > backup_$(date +%Y%m%d_%H%M%S).sql
```

**Restore database:**
```bash
mysql -u root -p ai_lead_db < backup_20260328_120000.sql
```

### Performance Optimization

The schema includes:
- Proper indexing on frequently queried columns
- Full-text search indexes for lead searching
- Foreign key constraints for data integrity
- Normalized table structure
- Partitioning support for large datasets

### Access Control

Create a dedicated user for the application:
```bash
CREATE USER 'lead_app'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON ai_lead_db.* TO 'lead_app'@'localhost';
FLUSH PRIVILEGES;
```

### Monitoring Queries

Check database size:
```sql
SELECT SUM(round(((data_length + index_length) / 1024 / 1024), 2)) as size_mb 
FROM information_schema.TABLES 
WHERE table_schema = 'ai_lead_db';
```

Check active connections:
```sql
SHOW PROCESSLIST;
```
