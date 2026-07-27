-- Database creation and initialization script
-- AI-Based Public Data & Lead Collection System

-- Create database
CREATE DATABASE IF NOT EXISTS ai_lead_db;
USE ai_lead_db;

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    company VARCHAR(255),
    role VARCHAR(50) DEFAULT 'user',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create leads table
CREATE TABLE IF NOT EXISTS leads (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(120),
    phone VARCHAR(20),
    company VARCHAR(255),
    position VARCHAR(255),
    interests JSON,
    qualification_score FLOAT DEFAULT 0.0,
    status VARCHAR(50) DEFAULT 'pending',
    source VARCHAR(100),
    data_points JSON,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_email (email),
    INDEX idx_status (status),
    INDEX idx_score (qualification_score),
    INDEX idx_created_at (created_at),
    FULLTEXT INDEX ft_name_email (name, email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create lead_activities table
CREATE TABLE IF NOT EXISTS lead_activities (
    id INT PRIMARY KEY AUTO_INCREMENT,
    lead_id INT NOT NULL,
    user_id INT NOT NULL,
    activity_type VARCHAR(100) NOT NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_lead_id (lead_id),
    INDEX idx_user_id (user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create data_sources table
CREATE TABLE IF NOT EXISTS data_sources (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    url VARCHAR(500),
    type VARCHAR(50) NOT NULL,
    last_crawled TIMESTAMP NULL,
    status VARCHAR(50) DEFAULT 'active',
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Create classification_categories table
CREATE TABLE IF NOT EXISTS classification_categories (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    keywords JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert default classification categories
INSERT IGNORE INTO classification_categories (name, description, keywords) VALUES
('Electronics', 'Electronic devices and gadgets', '["phone", "laptop", "tablet", "gadget", "device", "electronics"]'),
('Clothing', 'Apparel and fashion', '["dress", "shirt", "shoe", "clothes", "fashion", "apparel"]'),
('Smart Devices', 'IoT and smart home devices', '["smart", "iot", "home automation", "connected", "smart device"]'),
('Real Estate', 'Property and real estate', '["property", "house", "apartment", "real estate", "land"]'),
('Services', 'Professional services', '["service", "consulting", "agency", "professional"]');

-- Create indexes for performance optimization
CREATE INDEX idx_lead_qualification ON leads(qualification_score DESC);
CREATE INDEX idx_activity_timestamp ON lead_activities(created_at DESC);
