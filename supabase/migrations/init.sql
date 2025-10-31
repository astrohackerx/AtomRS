/*
  This migration creates all required tables, indexes, triggers, and security policies
  for the ATOMRS fee collector system.

  ## Tables Created

  ### 1. fee_collector_stats
  Tracks cumulative collector statistics:
  - `id` (uuid, primary key) - Unique identifier (singleton design)
  - `total_sol_paid` (numeric) - Cumulative total SOL paid out
  - `successful_executions` (integer) - Count of successful payouts
  - `last_payout_amount` (numeric) - Amount of last successful payout
  - `last_payout_at` (timestamptz) - Timestamp of last successful payout
  - `created_at` (timestamptz) - Record creation time
  - `updated_at` (timestamptz) - Record update time

  ### 2. collector_logs
  Stores real-time activity logs:
  - `id` (bigserial, primary key) - Auto-incrementing ID
  - `timestamp` (timestamptz) - When log was created
  - `level` (text) - Log level: info, success, error, warning
  - `message` (text) - Log message
  - `sol_amount` (numeric) - SOL amount if applicable
  - `tx_signature` (text) - Transaction signature if applicable
  - `metadata` (jsonb) - Additional context data

  ## Security

  ### fee_collector_stats
  - RLS enabled
  - Anyone can SELECT (public stats)
  - Anon can INSERT and UPDATE (backend script)
  - No DELETE policy (stats never deleted)

  ### collector_logs
  - RLS enabled
  - Anyone can SELECT (public monitoring)
  - Anon can INSERT (backend script)
  - No UPDATE or DELETE via policies

  ## Features

  ### Automatic Log Cleanup
  - Trigger maintains last 200 logs only
  - Automatically deletes oldest entries
  - Runs on every insert

  ### Singleton Stats Design
  - Only one stats record exists
  - Uses fixed UUID to prevent duplicates
  - Initial row pre-populated

  ## Indexes
  - collector_logs.timestamp (DESC) - Efficient log queries
  - collector_logs.level - Filter by log level
  - fee_collector_stats singleton constraint
*/

-- =============================================================================
-- TABLE: fee_collector_stats
-- =============================================================================

CREATE TABLE IF NOT EXISTS fee_collector_stats (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  total_sol_paid numeric DEFAULT 0 NOT NULL,
  successful_executions integer DEFAULT 0 NOT NULL,
  last_payout_amount numeric DEFAULT 0,
  last_payout_at timestamptz,
  created_at timestamptz DEFAULT now() NOT NULL,
  updated_at timestamptz DEFAULT now() NOT NULL
);

-- Ensure only one stats row exists (singleton pattern)
CREATE UNIQUE INDEX IF NOT EXISTS fee_collector_stats_singleton
  ON fee_collector_stats ((id IS NOT NULL));

-- Insert initial stats row with fixed UUID
INSERT INTO fee_collector_stats (id, total_sol_paid, successful_executions)
VALUES ('00000000-0000-0000-0000-000000000001', 0, 0)
ON CONFLICT DO NOTHING;

-- Enable Row Level Security
ALTER TABLE fee_collector_stats ENABLE ROW LEVEL SECURITY;

-- Policy: Anyone can read stats (useful for public dashboards)
CREATE POLICY "Anyone can read stats"
  ON fee_collector_stats
  FOR SELECT
  USING (true);

-- Policy: Anon can insert stats (backend script)
CREATE POLICY "Anon can insert stats"
  ON fee_collector_stats
  FOR INSERT
  TO anon
  WITH CHECK (true);

-- Policy: Anon can update stats (backend script)
CREATE POLICY "Anon can update stats"
  ON fee_collector_stats
  FOR UPDATE
  TO anon
  USING (true)
  WITH CHECK (true);

-- =============================================================================
-- TABLE: collector_logs
-- =============================================================================

CREATE TABLE IF NOT EXISTS collector_logs (
  id bigserial PRIMARY KEY,
  timestamp timestamptz DEFAULT now() NOT NULL,
  level text NOT NULL CHECK (level IN ('info', 'success', 'error', 'warning')),
  message text NOT NULL,
  sol_amount numeric,
  tx_signature text,
  metadata jsonb DEFAULT '{}'::jsonb
);

-- Indexes for efficient queries
CREATE INDEX IF NOT EXISTS collector_logs_timestamp_idx ON collector_logs (timestamp DESC);
CREATE INDEX IF NOT EXISTS collector_logs_level_idx ON collector_logs (level);

-- Function: Automatically cleanup old logs (keep last 200)
CREATE OR REPLACE FUNCTION cleanup_old_logs()
RETURNS TRIGGER AS $$
BEGIN
  DELETE FROM collector_logs
  WHERE id IN (
    SELECT id FROM collector_logs
    ORDER BY timestamp DESC
    OFFSET 200
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Auto-cleanup on every insert
DROP TRIGGER IF EXISTS cleanup_logs_trigger ON collector_logs;
CREATE TRIGGER cleanup_logs_trigger
  AFTER INSERT ON collector_logs
  FOR EACH STATEMENT
  EXECUTE FUNCTION cleanup_old_logs();

-- Enable Row Level Security
ALTER TABLE collector_logs ENABLE ROW LEVEL SECURITY;

-- Policy: Anyone can read logs (public monitoring)
CREATE POLICY "Anyone can read logs"
  ON collector_logs
  FOR SELECT
  USING (true);

-- Policy: Anon can insert logs (backend script)
CREATE POLICY "Anon can insert logs"
  ON collector_logs
  FOR INSERT
  TO anon
  WITH CHECK (true);
