-- =============================================================================
-- Data Retention Policy - Cleanup Old Data
-- Phase 6.1: Periodic cleanup to prevent unbounded table growth
-- =============================================================================

-- Cleanup predictions_log (older than 30 days)
DELETE FROM predictions_log WHERE created_at < NOW() - INTERVAL '30 days';

-- Cleanup collected_events (older than 30 days)
DELETE FROM collected_events WHERE created_at < NOW() - INTERVAL '30 days';

-- Cleanup spark_metrics (older than 7 days)
DELETE FROM spark_metrics WHERE timestamp < NOW() - INTERVAL '7 days';

-- Cleanup online_hits (older than 30 days)
DELETE FROM online_hits WHERE timestamp < NOW() - INTERVAL '30 days';

-- Cleanup online_metrics (older than 30 days)
DELETE FROM online_metrics WHERE created_at < NOW() - INTERVAL '30 days';

-- Vacuum + Analyze to reclaim space and update query planner stats
VACUUM ANALYZE predictions_log;
VACUUM ANALYZE collected_events;
VACUUM ANALYZE spark_metrics;
VACUUM ANALYZE online_hits;
VACUUM ANALYZE online_metrics;