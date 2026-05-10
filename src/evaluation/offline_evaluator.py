import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
import psycopg2
from psycopg2.extras import Json


class OfflineEvaluator:
    """Evaluate model performance on validation set with PostgreSQL storage."""

    def __init__(
        self,
        pg_host: str = "postgres",
        pg_port: int = 5432,
        pg_db: str = "otto_recommender",
        pg_user: str = "otto",
        pg_password: str = "otto123",
    ):
        self.pg_conn = psycopg2.connect(
            host=pg_host, port=pg_port, database=pg_db, user=pg_user, password=pg_password
        )
        self.pg_conn.autocommit = True
        self._init_tables()

    def _init_tables(self):
        """Initialize PostgreSQL tables if not exists."""
        with self.pg_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS evaluation_results (
                    id SERIAL PRIMARY KEY,
                    session TEXT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    hit BOOLEAN,
                    latency_ms DOUBLE PRECISION,
                    metric_name TEXT,
                    metric_value DOUBLE PRECISION,
                    predicted_items INT[],
                    actual_aid INT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_eval_session ON evaluation_results(session)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_eval_metric ON evaluation_results(metric_name)")

    def load_session_data(self, file_path: str) -> Dict[str, List[int]]:
        """Load session data from JSONL file."""
        sessions = {}
        with open(file_path, 'r') as f:
            for line in f:
                data = json.loads(line.strip())
                session_id = data["session"]
                items = [e["aid"] for e in data.get("events", [])]
                sessions[session_id] = items
        return sessions

    def load_predictions(self, file_path: str) -> Dict[str, List[int]]:
        """Load predictions from JSONL file."""
        predictions = {}
        with open(file_path, 'r') as f:
            for line in f:
                data = json.loads(line.strip())
                session_id = data["session"]
                preds = data.get("predictions", [])
                predictions[session_id] = preds
        return predictions

    def evaluate(
        self,
        predictions: Dict[str, List[int]],
        ground_truth: Dict[str, List[int]],
        ground_truth_types: Optional[Dict[str, List[str]]] = None,
        ks: Optional[List[int]] = None,
    ) -> Dict[str, float]:
        """Evaluate predictions against ground truth."""
        from src.evaluation.metrics import evaluate_batch

        if ks is None:
            ks = [5, 10, 20]

        pred_list = []
        gt_list = []
        gt_types_list = []

        for session_id in predictions:
            if session_id in ground_truth:
                pred_list.append(predictions[session_id])
                gt_list.append(ground_truth[session_id])
                if ground_truth_types and session_id in ground_truth_types:
                    gt_types_list.append(ground_truth_types[session_id])
                else:
                    gt_types_list.append(None)

        if gt_types_list and all(t is not None for t in gt_types_list):
            return evaluate_batch(pred_list, gt_list, gt_types_list, ks)
        else:
            return evaluate_batch(pred_list, gt_list, None, ks)

    def save_results_to_db(self, results: Dict[str, float], model_type: str = "covisitation"):
        """Save evaluation results to PostgreSQL."""
        with self.pg_conn.cursor() as cur:
            for metric_name, metric_value in results.items():
                cur.execute(
                    "INSERT INTO evaluation_results (ts, metric_name, metric_value) VALUES (NOW(), %s, %s)",
                    (metric_name, metric_value)
                )

    def get_historical_metrics(self, limit: int = 100) -> List[Dict]:
        """Retrieve historical evaluation metrics from PostgreSQL."""
        with self.pg_conn.cursor() as cur:
            cur.execute("""
                SELECT metric_name, metric_value, ts
                FROM evaluation_results
                WHERE metric_name IS NOT NULL
                ORDER BY ts DESC
                LIMIT %s
            """, (limit,))
            return [
                {"metric": row[0], "value": row[1], "timestamp": row[2]}
                for row in cur.fetchall()
            ]

    def print_results(self, results: Dict[str, float]):
        """Print evaluation results in a formatted way."""
        print("\n" + "="*50)
        print("OFFLINE EVALUATION RESULTS")
        print("="*50)

        for metric_name, value in results.items():
            print(f"  {metric_name}: {value:.4f}")

        print("="*50 + "\n")

    def close(self):
        """Close PostgreSQL connection."""
        if self.pg_conn:
            self.pg_conn.close()


class OnlineEvaluator:
    """Real-time evaluation with Redis (state) + PostgreSQL (storage)."""

    def __init__(
        self,
        bootstrap_servers: str,
        redis_host: str = "redis",
        redis_port: int = 6379,
        pg_host: str = "postgres",
        pg_port: int = 5432,
        pg_db: str = "otto_recommender",
        pg_user: str = "otto",
        pg_password: str = "otto123",
        predictions_topic: str = "predictions",
        user_events_topic: str = "user-events",
        results_topic: str = "evaluation-results",
    ):
        self.bootstrap_servers = bootstrap_servers
        self.predictions_topic = predictions_topic
        self.user_events_topic = user_events_topic
        self.results_topic = results_topic

        self.consumer = None
        self.producer = None
        self.prediction_cache = defaultdict(list)
        self.latencies = []

        # Redis for real-time state
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)

        # PostgreSQL for persistent storage
        self.pg_conn = psycopg2.connect(
            host=pg_host, port=pg_port, database=pg_db, user=pg_user, password=pg_password
        )
        self.pg_conn.autocommit = True
        self._init_tables()

    def _init_tables(self):
        """Initialize PostgreSQL tables."""
        with self.pg_conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS online_evaluation (
                    id SERIAL PRIMARY KEY,
                    session TEXT NOT NULL,
                    ts TIMESTAMPTZ NOT NULL,
                    hit BOOLEAN,
                    latency_ms DOUBLE PRECISION,
                    predicted_items INT[],
                    actual_aid INT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

    async def start(self):
        """Start Kafka consumer and producer."""
        self.consumer = AIOKafkaConsumer(
            self.predictions_topic,
            self.user_events_topic,
            bootstrap_servers=self.bootstrap_servers,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            group_id="evaluation-group",
            auto_offset_reset="latest",
        )
        await self.consumer.start()

        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
        await self.producer.start()
        logger.info("Online evaluator started with Redis + PostgreSQL")

    async def stop(self):
        """Stop all connections."""
        if self.consumer:
            await self.consumer.stop()
        if self.producer:
            await self.producer.stop()
        if self.redis:
            self.redis.close()
        if self.pg_conn:
            self.pg_conn.close()

    async def run(self):
        """Main loop to process messages."""
        try:
            async for msg in self.consumer:
                topic = msg.topic
                if topic == self.predictions_topic:
                    await self._handle_prediction(msg.value)
                elif topic == self.user_events_topic:
                    await self._handle_actual_event(msg.value)
        except Exception as e:
            logger.error(f"Error in online evaluator: {e}")

    async def _handle_prediction(self, data: dict):
        """Cache predictions."""
        session_id = data.get("session")
        predictions = data.get("predictions", {})
        timestamp = data.get("ts", datetime.now().timestamp() * 1000)

        self.prediction_cache[session_id].append({
            "predictions": predictions,
            "ts": timestamp,
        })

        # Cache in Redis
        self.redis.setex(
            f"prediction:{session_id}",
            300,
            json.dumps(predictions)
        )

    async def _handle_actual_event(self, data: dict):
        """Evaluate predictions when actual event occurs."""
        session_id = data.get("session")
        actual_aid = data.get("aid")
        timestamp = data.get("ts")

        if session_id not in self.prediction_cache:
            return

        cached = self.prediction_cache[session_id]
        if not cached:
            return

        latest_pred = cached[-1]
        predictions = latest_pred["predictions"]

        hit = actual_aid in predictions.get("clicks", [])
        latency = (timestamp - latest_pred["ts"]) / 1000

        # Store in PostgreSQL
        with self.pg_conn.cursor() as cur:
            cur.execute(
                """INSERT INTO online_evaluation
                   (session, ts, hit, latency_ms, predicted_items, actual_aid)
                   VALUES (%s, to_timestamp(%s/1000.0), %s, %s, %s, %s)""",
                (session_id, timestamp, hit, latency, list(predictions.get("clicks", [])), actual_aid)
            )

        # Send to results topic
        result = {
            "session": session_id,
            "actual_aid": actual_aid,
            "hit": hit,
            "latency_ms": latency,
            "timestamp": datetime.now().isoformat(),
        }
        await self.producer.send(self.results_topic, result)

        self.latencies.append(latency)

    def get_stats(self) -> dict:
        """Get current evaluation statistics."""
        if not self.latencies:
            return {"avg_latency": 0, "count": 0}

        return {
            "avg_latency": sum(self.latencies) / len(self.latencies),
            "min_latency": min(self.latencies),
            "max_latency": max(self.latencies),
            "count": len(self.latencies),
        }
