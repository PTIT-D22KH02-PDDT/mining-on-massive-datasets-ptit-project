"""
DB query helper used by report_generator.sh via: docker exec -i otto-api python3 < query_db.py <metric>
Usage: docker exec -i otto-api python3 < query_db.py spark
       docker exec -i otto-api python3 < query_db.py events
       docker exec -i otto-api python3 < query_db.py tables
       docker exec -i otto-api python3 < query_db.py all_events
"""

import os, sys, json, traceback

try:
    import psycopg2
except ImportError:
    print(json.dumps({"error": "psycopg2 not available"}))
    sys.exit(0)

PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB", "otto_recommender")
PG_USER = os.getenv("POSTGRES_USER", "otto")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "otto123")

arg = sys.argv[1] if len(sys.argv) > 1 else "tables"

try:
    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASS)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET TIME ZONE 'Asia/Ho_Chi_Minh'")

    if arg == "spark":
        cur.execute("""
            SELECT
                COUNT(*)::bigint AS batches,
                ROUND(AVG(batch_duration_ms))::bigint AS avg_ms,
                ROUND(MAX(batch_duration_ms))::bigint AS max_ms,
                ROUND(COALESCE(AVG(process_rows_per_second), 0))::bigint AS avg_rps,
                ROUND(COALESCE(SUM(input_rows_per_second), 0))::bigint AS total_rows,
                ROUND(AVG(batch_duration_ms::numeric / 1000), 2) AS avg_s
            FROM spark_metrics
            WHERE timestamp > NOW() - INTERVAL '30 minutes'
        """)
        row = cur.fetchone()
        if row and row[0] > 0:
            keys = ["batches", "avg_ms", "max_ms", "avg_rps", "total_rows", "avg_s"]
            print(json.dumps(dict(zip(keys, row)), default=str))
        else:
            print(json.dumps({"found": False}, default=str))

    elif arg == "events":
        cur.execute("""
            SELECT
                COUNT(*)::bigint AS events,
                ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - created_at))))::bigint AS avg_age_s,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (NOW() - created_at))))::bigint AS p50_s,
                ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (NOW() - created_at))))::bigint AS p95_s
            FROM collected_events
            WHERE created_at > NOW() - INTERVAL '15 minutes'
        """)
        row = cur.fetchone()
        if row and row[0] > 0:
            keys = ["events", "avg_age_s", "p50_s", "p95_s"]
            print(json.dumps(dict(zip(keys, row)), default=str))
        else:
            print(json.dumps({"found": False}, default=str))

    elif arg == "tables":
        cur.execute("""
            SELECT table_name, (SELECT COUNT(*) FROM information_schema.columns WHERE table_name=t.table_name) AS cols,
                   (SELECT reltuples::bigint FROM pg_class WHERE relname=t.table_name) AS est_rows
            FROM information_schema.tables t
            WHERE table_schema='public'
            ORDER BY table_name
        """)
        rows = cur.fetchall()
        tables = [{"name": r[0], "cols": r[1], "est_rows": r[2]} for r in rows]
        print(json.dumps({"tables": tables}, default=str))

    elif arg == "all_events":
        cur.execute("""
            SELECT event_type, COUNT(*)::bigint AS cnt
            FROM collected_events
            WHERE created_at > NOW() - INTERVAL '15 minutes'
            GROUP BY event_type
            ORDER BY cnt DESC
        """)
        rows = cur.fetchall()
        dist = [{"type": r[0], "count": r[1]} for r in rows]
        print(json.dumps({"event_distribution": dist}, default=str))

    cur.close()
    conn.close()
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, default=str))