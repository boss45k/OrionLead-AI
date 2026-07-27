-- Migration 002: Add location and product columns to leads table
-- Supports location-based and product-based lead filtering + AI targeting

USE ai_lead_db;

ALTER TABLE leads
    ADD COLUMN IF NOT EXISTS location VARCHAR(255) NULL AFTER position,
    ADD COLUMN IF NOT EXISTS product VARCHAR(255) NULL AFTER interests,
    ADD INDEX IF NOT EXISTS idx_location (location);
