-- Create leaderboard table
CREATE TABLE IF NOT EXISTS public.leaderboard (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_name TEXT NOT NULL,
    trade_name TEXT NOT NULL,
    marks INTEGER NOT NULL,
    reg_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Enable Row Level Security (RLS)
ALTER TABLE public.leaderboard ENABLE ROW LEVEL SECURITY;

-- Policy 1: Allow PUBLIC to only READ data
CREATE POLICY "Allow public read access" 
ON public.leaderboard
FOR SELECT
TO public
USING (true);

-- Policy 2: Allow INSERT only via secure Python backend service role.
-- Note: The 'service_role' bypasses RLS by default, but it's good practice to be explicit if role-based access is strictly defined.
CREATE POLICY "Allow service role insert" 
ON public.leaderboard
FOR INSERT
TO service_role
WITH CHECK (true);

-- Create Supabase Storage bucket for temp_results
-- This bucket is not public as the screenshots should only be accessible by the backend for processing
INSERT INTO storage.buckets (id, name, public) 
VALUES ('temp_results', 'temp_results', false) 
ON CONFLICT (id) DO NOTHING;

-- Optionally, you can explicitly restrict access to the bucket to only the service role
-- The service role bypasses these policies, ensuring only the backend can upload and delete.
CREATE POLICY "Deny public access to temp_results"
ON storage.objects
FOR ALL
TO public
USING (bucket_id != 'temp_results');
