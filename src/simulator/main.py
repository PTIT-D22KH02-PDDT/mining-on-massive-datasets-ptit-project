import asyncio
import json
import random
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from src.simulator.producer import SessionProducer
from src.simulator.session_generator import SessionGenerator
from src.simulator.scenarios import TrafficScenario, ScenarioType
from src.core.config import get_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONFIG = get_config()
KAFKA_SERVERS = CONFIG.get("kafka", {}).get("bootstrap_servers", "localhost:29092")
TRAIN_DATA_PATH = "datasets/raw/train.jsonl"


async def replay_from_file(producer: SessionProducer, file_path: str, speed_multiplier: float = 1.0):
    """Replay sessions from a JSONL file."""
    logger.info(f"Replaying sessions from {file_path} at {speed_multiplier}x speed")

    with open(file_path, 'r') as f:
        for line in f:
            session_data = json.loads(line.strip())
            await producer.send_session_replay(session_data, speed_multiplier)

    logger.info("Finished replaying sessions")


async def run_scenario_mode(
    producer: SessionProducer,
    scenario_type: ScenarioType,
    duration_seconds: int = 300,
    train_data_path: Optional[str] = None,
):
    """Run simulator in scenario mode with concurrent sessions."""
    config = TrafficScenario.get_config(scenario_type)
    generator = SessionGenerator(train_data_path)

    logger.info(f"Starting {scenario_type.value} scenario for {duration_seconds}s")
    logger.info(f"Config: {config}")

    start_time = datetime.now()
    tasks = []

    async def session_loop():
        session_count = 0
        while (datetime.now() - start_time).seconds < duration_seconds:
            if random.random() < config.get("burst_probability", 0):
                session = generator.generate_burst_session()
            else:
                session = generator.generate_session()

            await producer.send_session(session)

            gap = config["session_gap_seconds"] / config["speed_multiplier"]
            await asyncio.sleep(gap)
            session_count += 1

        logger.info(f"Session loop ended. Generated {session_count} sessions")

    for _ in range(config["concurrent_sessions"]):
        task = asyncio.create_task(session_loop())
        tasks.append(task)
        await asyncio.sleep(0.1)

    await asyncio.gather(*tasks)
    logger.info(f"{scenario_type.value} scenario completed")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="OTTO Session Simulator")
    parser.add_argument("--mode", choices=["replay", "scenario", "mixed"], default="scenario")
    parser.add_argument("--scenario", choices=TrafficScenario.get_all_scenarios(), default="normal")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed multiplier")
    parser.add_argument("--duration", type=int, default=300, help="Duration in seconds")
    parser.add_argument("--file", type=str, help="Path to JSONL file for replay")
    args = parser.parse_args()

    producer = SessionProducer(KAFKA_SERVERS, topic="user-events")

    try:
        await producer.start()
        logger.info("Producer started")

        if args.mode == "replay":
            file_path = args.file or "datasets/raw/test.jsonl"
            await replay_from_file(producer, file_path, args.speed)

        elif args.mode == "scenario":
            scenario = ScenarioType(args.scenario)
            await run_scenario_mode(
                producer,
                scenario,
                duration_seconds=args.duration,
                train_data_path=TRAIN_DATA_PATH if Path(TRAIN_DATA_PATH).exists() else None,
            )

        elif args.mode == "mixed":
            file_path = args.file or "datasets/raw/test.jsonl"
            if Path(file_path).exists():
                replay_task = asyncio.create_task(
                    replay_from_file(producer, file_path, args.speed)
                )
                scenario_task = asyncio.create_task(
                    run_scenario_mode(
                        producer,
                        ScenarioType(args.scenario),
                        duration_seconds=args.duration,
                        train_data_path=TRAIN_DATA_PATH if Path(TRAIN_DATA_PATH).exists() else None,
                    )
                )
                await asyncio.gather(replay_task, scenario_task)
            else:
                logger.warning(f"File {file_path} not found, running scenario only")
                await run_scenario_mode(
                    producer,
                    ScenarioType(args.scenario),
                    duration_seconds=args.duration,
                )

    except KeyboardInterrupt:
        logger.info("Stopped by user")
    finally:
        await producer.stop()
        logger.info("Producer stopped")


if __name__ == "__main__":
    asyncio.run(main())
