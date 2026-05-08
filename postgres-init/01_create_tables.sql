-- =============================================================================
-- OTTO Recommender System — PostgreSQL Schema
-- Auto-executed on first docker-compose up
-- =============================================================================

-- Thống kê theo cửa sổ thời gian (từ Spark / batch)
CREATE TABLE IF NOT EXISTS stats_hourly (
    id SERIAL PRIMARY KEY,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    total_events INT DEFAULT 0,
    total_clicks INT DEFAULT 0,
    total_carts INT DEFAULT 0,
    total_orders INT DEFAULT 0,
    unique_sessions INT DEFAULT 0,
    unique_items INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Thống kê sản phẩm
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

-- Phân loại sessions
CREATE TABLE IF NOT EXISTS stats_sessions (
    session_type VARCHAR(30) PRIMARY KEY,
    count INT DEFAULT 0,
    avg_length FLOAT DEFAULT 0,
    avg_duration_sec FLOAT DEFAULT 0,
    pct_of_total FLOAT DEFAULT 0
);

-- Log predictions (từ API server)
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

-- Anomaly logs
CREATE TABLE IF NOT EXISTS anomaly_logs (
    id SERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    anomaly_type VARCHAR(30),
    details JSONB,
    detected_at TIMESTAMP DEFAULT NOW()
);

-- Sản phẩm phổ biến (pre-computed, cho cold start)
CREATE TABLE IF NOT EXISTS popular_items (
    id SERIAL PRIMARY KEY,
    time_scope VARCHAR(20),
    event_type VARCHAR(10),
    aid INT NOT NULL,
    count INT NOT NULL,
    rank INT NOT NULL,
    computed_at TIMESTAMP DEFAULT NOW()
);

-- Funnel analysis
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

-- Collected events (cho retrain sau này)
CREATE TABLE IF NOT EXISTS collected_events (
    id SERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL,
    aid INT NOT NULL,
    event_type VARCHAR(10) NOT NULL,
    ts BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collected_events_session ON collected_events(session_id);
CREATE INDEX IF NOT EXISTS idx_predictions_log_session ON predictions_log(session_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_logs_session ON anomaly_logs(session_id);
CREATE INDEX IF NOT EXISTS idx_stats_items_clicks ON stats_items(total_clicks DESC);
CREATE INDEX IF NOT EXISTS idx_stats_items_orders ON stats_items(total_orders DESC);
