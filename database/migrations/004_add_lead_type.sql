-- Add lead_type column to distinguish between company and person leads
ALTER TABLE leads ADD COLUMN lead_type VARCHAR(50) NULL AFTER source;

-- Create index for filtering by lead type
CREATE INDEX idx_leads_lead_type ON leads(lead_type);
