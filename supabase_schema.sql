-- Supabase Schema for Legal RFP Response Tool
-- Run this SQL in your Supabase SQL Editor to set up the required tables

-- ============================================
-- USERS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    bar_number TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    icon TEXT DEFAULT '👤',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- OBJECTIONS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS objections (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    formal_language TEXT NOT NULL,
    argument_template TEXT,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- TEMPLATES TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS templates (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'rfp',  -- 'rfp' or 'opposition'
    description TEXT,
    storage_path TEXT NOT NULL UNIQUE,
    uploaded_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add type column if table already exists
-- ALTER TABLE templates ADD COLUMN type TEXT NOT NULL DEFAULT 'rfp';

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_templates_uploaded_by ON templates(uploaded_by);

-- ============================================
-- ROW LEVEL SECURITY (Optional but recommended)
-- ============================================
-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE objections ENABLE ROW LEVEL SECURITY;
ALTER TABLE templates ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read/write for all tables (suitable for internal tools)
-- Adjust these policies based on your security requirements

CREATE POLICY "Allow anonymous access" ON users
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow anonymous access" ON objections
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow anonymous access" ON templates
    FOR ALL USING (true) WITH CHECK (true);

-- ============================================
-- SUPABASE STORAGE BUCKET
-- ============================================
-- Run this in SQL Editor or create via Supabase Dashboard > Storage

-- Note: Storage bucket creation is typically done via the dashboard, but you can use:
-- INSERT INTO storage.buckets (id, name, public) VALUES ('templates', 'templates', false);

-- Storage RLS policies (run after bucket is created):
-- Allow authenticated users to upload
-- CREATE POLICY "Allow uploads" ON storage.objects
--     FOR INSERT WITH CHECK (bucket_id = 'templates');

-- Allow authenticated users to download
-- CREATE POLICY "Allow downloads" ON storage.objects
--     FOR SELECT USING (bucket_id = 'templates');

-- Allow authenticated users to delete
-- CREATE POLICY "Allow deletes" ON storage.objects
--     FOR DELETE USING (bucket_id = 'templates');
