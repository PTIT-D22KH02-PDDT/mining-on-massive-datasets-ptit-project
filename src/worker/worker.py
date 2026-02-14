import threading
from typing import Optional

from src.core import KafkaListenerService, logging

logger = logging.getLogger(__name__)
class Worker:
    def __init__(self):
        self.logger = logger

        self.is_running = False
        self.shutdown_event = threading.Event()

        self.kafka_consumer = Optional[KafkaListenerService] = None
