from enum import Enum
from typing import Optional
from datetime import datetime


class ScenarioType(Enum):
    NORMAL = "normal"
    FLASH_SALE = "flash_sale"
    BOT_TRAFFIC = "bot_traffic"
    QUIET_HOURS = "quiet_hours"


class TrafficScenario:
    """Define traffic scenario modes for the simulator."""

    @staticmethod
    def get_config(scenario: ScenarioType) -> dict:
        configs = {
            ScenarioType.NORMAL: {
                "speed_multiplier": 1.0,
                "concurrent_sessions": 5,
                "session_gap_seconds": 10,
                "burst_probability": 0.0,
            },
            ScenarioType.FLASH_SALE: {
                "speed_multiplier": 2.0,
                "concurrent_sessions": 20,
                "session_gap_seconds": 2,
                "burst_probability": 0.3,
            },
            ScenarioType.BOT_TRAFFIC: {
                "speed_multiplier": 5.0,
                "concurrent_sessions": 10,
                "session_gap_seconds": 1,
                "burst_probability": 0.8,
                "use_burst_sessions": True,
            },
            ScenarioType.QUIET_HOURS: {
                "speed_multiplier": 0.5,
                "concurrent_sessions": 2,
                "session_gap_seconds": 30,
                "burst_probability": 0.0,
            },
        }
        return configs.get(scenario, configs[ScenarioType.NORMAL])

    @staticmethod
    def get_all_scenarios() -> list:
        return [s.value for s in ScenarioType]

    @staticmethod
    def get_next_scenario(current: ScenarioType, auto_cycle: bool = False) -> Optional[ScenarioType]:
        if not auto_cycle:
            return None
        scenarios = list(ScenarioType)
        idx = scenarios.index(current)
        return scenarios[(idx + 1) % len(scenarios)]
