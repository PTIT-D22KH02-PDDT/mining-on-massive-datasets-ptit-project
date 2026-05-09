-- =============================================================================
-- OTTO Recommender System — PostgreSQL Unified Schema
-- Auto-executed on first docker-compose up
-- =============================================================================

-- 1. ANALYTICS TABLES (Traffic & Performance)
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stats_hourly (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    total_events INT DEFAULT 0,
    total_clicks INT DEFAULT 0,
    total_carts INT DEFAULT 0,
    total_orders INT DEFAULT 0,
    total_sessions INT DEFAULT 0,
    unique_sessions INT DEFAULT 0,
    unique_items INT DEFAULT 0,
    click_to_cart_rate FLOAT DEFAULT 0,
    cart_to_order_rate FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stats_items (
    aid INT PRIMARY KEY,
    total_clicks INT DEFAULT 0,
    total_carts INT DEFAULT 0,
    total_orders INT DEFAULT 0,
    click_to_cart_rate FLOAT DEFAULT 0,
    click_to_order_rate FLOAT DEFAULT 0,
    cart_to_order_rate FLOAT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS stats_sessions (
    session_type VARCHAR(30) PRIMARY KEY,
    count INT DEFAULT 0,
    avg_length FLOAT DEFAULT 0,
    avg_duration_sec FLOAT DEFAULT 0,
    pct_of_total FLOAT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS funnel_stats (
    id SERIAL PRIMARY KEY,
    total_sessions INT,
    sessions_with_clicks INT,
    sessions_with_carts INT,
    sessions_with_orders INT,
    click_to_cart_rate FLOAT,
    cart_to_order_rate FLOAT,
    click_to_order_rate FLOAT,
    computed_at TIMESTAMP DEFAULT NOW()
);

-- Advanced Funnel (Model Performance Evaluation)
CREATE TABLE IF NOT EXISTS advanced_funnel_stats (
    model_used VARCHAR(30) PRIMARY KEY,
    total_sessions BIGINT DEFAULT 0,
    sessions_with_clicks BIGINT DEFAULT 0,
    sessions_with_carts BIGINT DEFAULT 0,
    sessions_with_orders BIGINT DEFAULT 0,
    click_to_order_rate DOUBLE PRECISION DEFAULT 0,
    last_updated TIMESTAMP DEFAULT NOW()
);


-- 2. RECOMMENDER CORE TABLES
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS popular_items (
    id SERIAL PRIMARY KEY,
    time_scope VARCHAR(20),
    event_type VARCHAR(10),
    aid INT NOT NULL,
    count INT NOT NULL,
    rank INT NOT NULL,
    computed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(time_scope, event_type, aid)
);

CREATE TABLE IF NOT EXISTS predictions_log (
    id SERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    model_used VARCHAR(30),
    session_length INT,
    predicted_clicks INT[],
    predicted_carts INT[],
    predicted_orders INT[],
    latency_ms FLOAT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS collected_events (
    id SERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    aid INT NOT NULL,
    event_type VARCHAR(10) NOT NULL,
    ts BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
);


-- 3. EVALUATION TABLES (Offline & Online)
--------------------------------------------------------------------------------
-- API Online Hit Rate tracking
CREATE TABLE IF NOT EXISTS online_hits (
    id SERIAL PRIMARY KEY,
    session_id BIGINT,
    aid INT,
    event_type TEXT,
    is_hit BOOLEAN,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Offline Metric Results
CREATE TABLE IF NOT EXISTS evaluation_results (
    id SERIAL PRIMARY KEY,
    session TEXT,
    ts TIMESTAMPTZ,
    hit BOOLEAN,
    latency_ms DOUBLE PRECISION,
    metric_name TEXT,
    metric_value DOUBLE PRECISION,
    predicted_items INT[],
    actual_aid INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Kafka-based Online Evaluation
CREATE TABLE IF NOT EXISTS online_evaluation (
    id SERIAL PRIMARY KEY,
    session TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    hit BOOLEAN,
    latency_ms DOUBLE PRECISION,
    predicted_items INT[],
    actual_aid INT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);


-- 4. MONITORING TABLES (Health & Anomalies)
--------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS anomaly_logs (
    id SERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    anomaly_type VARCHAR(30),
    details JSONB,
    detected_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS spark_metrics (
    id SERIAL PRIMARY KEY,
    query_id VARCHAR(50),
    query_name VARCHAR(100),
    batch_id BIGINT,
    input_rows_per_second FLOAT,
    process_rows_per_second FLOAT,
    batch_duration_ms BIGINT,
    timestamp TIMESTAMP DEFAULT NOW()
);


-- 5. INDEXES for Performance
--------------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_stats_items_clicks ON stats_items(total_clicks DESC);
CREATE INDEX IF NOT EXISTS idx_stats_items_orders ON stats_items(total_orders DESC);
CREATE INDEX IF NOT EXISTS idx_collected_events_session ON collected_events(session_id);
CREATE INDEX IF NOT EXISTS idx_predictions_log_session ON predictions_log(session_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_logs_session ON anomaly_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_spark_metrics_timestamp ON spark_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_eval_session ON evaluation_results(session);
CREATE INDEX IF NOT EXISTS idx_eval_metric ON evaluation_results(metric_name);
CREATE INDEX IF NOT EXISTS idx_popular_items_composite ON popular_items(event_type, time_scope, count DESC);
