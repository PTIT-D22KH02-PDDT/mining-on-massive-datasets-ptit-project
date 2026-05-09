"""
Client Simulator — Replays sessions from test.jsonl via HTTP to the API server.
Supports multiple concurrent users via asyncio.

Usage:
    python -m src.simulator.client --file test.jsonl --sessions 10 --speed 5
"""

import asyncio
import argparse
import json
import logging
import time
import random
from pathlib import Path
from typing import List, Dict, Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("simulator")


async def replay_session(
    client: httpx.AsyncClient,
    api_url: str,
    session_data: Dict[str, Any],
    speed: float = 1.0,
    delay_between_events: float = 0.5,
):
    """Replay a single session, sending events one-by-one to the API."""
    session_id = session_data["session"]
    events = session_data["events"]

    logger.info(f"Starting session {session_id} ({len(events)} events)")

    for i, event in enumerate(events):
        payload = {
            "session_id": session_id,
            "aid": event["aid"],
            "type": event["type"],
            "ts": event.get("ts"),
        }

        try:
            resp = await client.post(f"{api_url}/api/event", json=payload, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                recs_clicks = data["recommendations"].get("clicks", [])[:5]
                logger.info(
                    f"  [{session_id}] Event {i+1}/{len(events)}: "
                    f"{event['type']:6s} aid={event['aid']:>8d} - "
                    f"model={data['model_used']}, "
                    f"latency={data['latency_ms']:.1f}ms, "
                    f"top5_clicks={recs_clicks}"
                )
            else:
                logger.warning(f"  [{session_id}] HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.error(f"  [{session_id}] Error: {e}")

        # Simulate real-time delay between events
        if speed > 0 and i < len(events) - 1:
            await asyncio.sleep(delay_between_events / speed)

    logger.info(f"Session {session_id} completed ({len(events)} events)")


async def run_simulator(
    file_path: str,
    api_url: str,
    max_sessions: int = 10,
    concurrency: int = 3,
    speed: float = 5.0,
    delay_between_events: float = 0.3,
):
    """
    Main simulator: read sessions from JSONL, replay them concurrently.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return

    # Load sessions
    sessions = []
    with open(path, "r") as f:
        for i, line in enumerate(f):
            if i >= max_sessions:
                break
            sessions.append(json.loads(line))

    logger.info(f"Loaded {len(sessions)} sessions from {file_path}")
    logger.info(f"API: {api_url}, Concurrency: {concurrency}, Speed: {speed}x")
    logger.info("=" * 60)

    # Run with semaphore to limit concurrency
    sem = asyncio.Semaphore(concurrency)

    async def bounded_replay(client, session_data):
        async with sem:
            await replay_session(client, api_url, session_data, speed, delay_between_events)

    async with httpx.AsyncClient() as client:
        # Check API health first
        try:
            resp = await client.get(f"{api_url}/api/health", timeout=5.0)
            logger.info(f"API Health: {resp.json()}")
        except Exception as e:
            logger.error(f"Cannot reach API at {api_url}: {e}")
            return

        start = time.time()

        tasks = [bounded_replay(client, s) for s in sessions]
        await asyncio.gather(*tasks)

        elapsed = time.time() - start
        total_events = sum(len(s["events"]) for s in sessions)
        logger.info("=" * 60)
        logger.info(
            f"Done! {len(sessions)} sessions, {total_events} events in {elapsed:.1f}s "
            f"({total_events/elapsed:.1f} events/sec)"
        )

        # Show final stats
        try:
            resp = await client.get(f"{api_url}/api/stats", timeout=5.0)
            stats = resp.json()
            logger.info(f"Server stats: {json.dumps(stats, indent=2)}")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="OTTO Session Simulator")
    parser.add_argument("--file", default="literature-review/duong/test.jsonl", help="Path to JSONL file")
    parser.add_argument("--api", default="http://localhost:8000", help="API server URL")
    parser.add_argument("--sessions", type=int, default=10, help="Number of sessions to replay")
    parser.add_argument("--concurrency", type=int, default=3, help="Max concurrent sessions")
    parser.add_argument("--speed", type=float, default=5.0, help="Speed multiplier (0=no delay)")
    parser.add_argument("--delay", type=float, default=0.3, help="Base delay between events (seconds)")
    args = parser.parse_args()

    asyncio.run(
        run_simulator(
            file_path=args.file,
            api_url=args.api,
            max_sessions=args.sessions,
            concurrency=args.concurrency,
            speed=args.speed,
            delay_between_events=args.delay,
        )
    )


if __name__ == "__main__":
    main()
