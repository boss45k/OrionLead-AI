-- Seed data for development and testing

USE ai_lead_db;

-- Insert sample leads for testing
INSERT INTO leads (name, email, phone, company, position, interests, qualification_score, status, source, notes) VALUES
('John Doe', 'john.doe@example.com', '+1-555-0101', 'Tech Corp', 'CTO', '["electronics", "smart devices"]', 95, 'qualified', 'website', 'High-value lead, very interested'),
('Jane Smith', 'jane.smith@example.com', '+1-555-0102', 'Design Studio', 'Creative Director', '["electronics", "laptop"]', 82, 'active', 'linkedin', 'Good fit for product'),
('Mike Johnson', 'mike.j@example.com', '+1-555-0103', 'Retail Solutions', 'Procurement Manager', '["clothing", "smart devices"]', 75, 'active', 'facebook', 'Medium priority'),
('Sarah Wilson', 'sarah.w@example.com', '+1-555-0104', 'Home Services Inc', 'Manager', '["smart devices", "real estate"]', 88, 'qualified', 'website', 'Enterprise potential'),
('Robert Lee', 'robert.lee@business.com', '+1-555-0105', 'Business Consulting', 'Director', '["electronics"]', 70, 'pending', 'directory', 'Needs follow-up'),
('Emily Davis', 'e.davis@company.com', '+1-555-0106', 'Fashion Forward', 'Operations Head', '["clothing"]', 65, 'pending', 'social_media', 'Early stage interest'),
('David Martinez', 'david.m@example.com', '+1-555-0107', 'International Trade', 'VP Sales', '["electronics", "clothing"]', 92, 'qualified', 'website', 'Bulk buyer potential'),
('Lisa Anderson', 'lisa.a@example.com', '+1-555-0108', 'Real Estate Corp', 'Property Manager', '["real estate", "smart devices"]', 78, 'active', 'linkedin', 'Corporate account');

-- Insert sample classification categories (if not already exist)
INSERT IGNORE INTO classification_categories (name, keywords) VALUES
('Premium Buyer', '["bulk", "enterprise", "director", "manager"]'),
('Individual Consumer', '["personal", "individual", "consumer"]'),
('Tech Enthusiast', '["tech", "electronics", "gadget", "innovation"]'),
('Business Owner', '["owner", "ceo", "founder", "entrepreneur"]');

-- Insert sample data sources
INSERT INTO data_sources (name, url, type, status, config) VALUES
('Tech News Website', 'https://technews.example.com', 'web', 'active', '{"crawl_frequency": "daily"}'),
('LinkedIn Search', 'https://linkedin.com', 'social_media', 'active', '{"search_keywords": ["electronics", "tech"]}'),
('Business Directory', 'https://business-directory.example.com', 'directory', 'active', '{"filters": ["b2b"]}'),
('Facebook Groups', 'https://facebook.com/groups', 'social_media', 'active', '{"groups": ["tech_buyers", "business_group"]}');
