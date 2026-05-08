import json
import random
from typing import List, Dict, Any
from datetime import datetime, timedelta


class SessionGenerator:
    """Generate random sessions based on statistical distributions from real data."""

    def __init__(self, train_data_path: str = None):
        self.event_types = ["clicks", "carts", "orders"]
        self.event_type_weights = [0.85, 0.10, 0.05]
        self.session_length_avg = 5
        self.session_length_std = 3
        self.inter_event_time_avg = 30
        self.aid_pool = list(range(1, 1800000))

        if train_data_path:
            self._learn_distributions(train_data_path)

    def _learn_distributions(self, train_data_path: str):
        """Learn distributions from training data."""
        session_lengths = []
        inter_event_times = []
        event_type_counts = {"clicks": 0, "carts": 0, "orders": 0}

        try:
            with open(train_data_path, 'r') as f:
                for i, line in enumerate(f):
                    if i >= 10000:
                        break
                    session = json.loads(line)
                    events = session.get("events", [])
                    session_lengths.append(len(events))

                    for evt in events:
                        event_type_counts[evt["type"]] += 1

                    if len(events) > 1:
                        times = sorted([e["ts"] for e in events])
                        for j in range(1, len(times)):
                            inter_event_times.append((times[j] - times[j-1]) / 1000)

            if session_lengths:
                self.session_length_avg = sum(session_lengths) / len(session_lengths)
                self.session_length_std = max(2, (sum((x - self.session_length_avg) ** 2 for x in session_lengths) / len(session_lengths)) ** 0.5)

            if inter_event_times:
                self.inter_event_time_avg = sum(inter_event_times) / len(inter_event_times)

            total_events = sum(event_type_counts.values())
            if total_events > 0:
                self.event_type_weights = [
                    event_type_counts["clicks"] / total_events,
                    event_type_counts["carts"] / total_events,
                    event_type_counts["orders"] / total_events,
                ]

        except FileNotFoundError:
            pass

    def generate_session(self, session_id: str = None, start_time: datetime = None) -> Dict[str, Any]:
        """Generate a single random session."""
        if session_id is None:
            session_id = f"sim_{random.randint(1000000, 9999999)}"

        if start_time is None:
            start_time = datetime.now()

        num_events = max(1, int(random.gauss(self.session_length_avg, self.session_length_std)))

        events = []
        current_time = start_time

        for _ in range(num_events):
            event_type = random.choices(self.event_types, weights=self.event_type_weights)[0]
            aid = random.choice(self.aid_pool)
            current_time = current_time + timedelta(seconds=max(1, random.expovariate(1 / self.inter_event_time_avg)))

            events.append({
                "aid": aid,
                "ts": int(current_time.timestamp() * 1000),
                "type": event_type
            })

        events.sort(key=lambda x: x["ts"])

        return {
            "session": session_id,
            "events": events
        }

    def generate_burst_session(self, session_id: str = None) -> Dict[str, Any]:
        """Generate a bot-like session with many rapid clicks."""
        if session_id is None:
            session_id = f"bot_{random.randint(1000000, 9999999)}"

        start_time = datetime.now()
        num_events = random.randint(100, 300)

        events = []
        current_time = start_time

        for i in range(num_events):
            aid = random.choice(self.aid_pool)
            current_time = current_time + timedelta(milliseconds=random.randint(10, 100))
            events.append({
                "aid": aid,
                "ts": int(current_time.timestamp() * 1000),
                "type": "clicks"
            })

        return {
            "session": session_id,
            "events": events
        }
