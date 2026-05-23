-- e2e_latency.sql
-- Do E2E pipeline latency: tu event creation -> co trong DB

WITH e2e AS (
  SELECT
    created_at AS event_time,
    NOW() - created_at AS age,
    EXTRACT(EPOCH FROM (NOW() - created_at)) AS age_seconds
  FROM collected_events
  WHERE created_at > NOW() - INTERVAL '15 minutes'
)
SELECT
  COUNT(*) AS total_events,
  ROUND(AVG(age_seconds)) AS avg_seconds,
  ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY age_seconds)) AS p50_seconds,
  ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY age_seconds)) AS p90_seconds,
  ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY age_seconds)) AS p95_seconds,
  ROUND(MAX(age_seconds)) AS max_seconds,
  CASE
    WHEN AVG(age_seconds) < 10 THEN 'REALTIME'
    WHEN AVG(age_seconds) < 30 THEN 'NEAR_REALTIME'
    WHEN AVG(age_seconds) < 60 THEN 'BATCH_LIKE'
    ELSE 'OFFLINE'
  END AS freshness_verdict
FROM e2e;
