-- Migration 003: Add country, city, industry, website, linkedin_url to leads
-- Supports country-based public web data collection and lead enrichment
-- Supports 45+ countries across all major regions

USE ai_lead_db;

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS country VARCHAR(100) NULL AFTER location,
    ADD COLUMN IF NOT EXISTS city VARCHAR(255) NULL AFTER country,
    ADD COLUMN IF NOT EXISTS industry VARCHAR(255) NULL AFTER city,
    ADD COLUMN IF NOT EXISTS website VARCHAR(500) NULL AFTER industry,
    ADD COLUMN IF NOT EXISTS linkedin_url VARCHAR(500) NULL AFTER website,
    ADD INDEX IF NOT EXISTS idx_country (country),
    ADD INDEX IF NOT EXISTS idx_industry (industry),
    ADD INDEX IF NOT EXISTS idx_city (city);
