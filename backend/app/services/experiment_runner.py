import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.db.database import SessionLocal
from app.db.models import Experiment, Result
from app.models.schemas import ExperimentRequest, MetricSnapshot

class ExperimentRunner:
    def __init__(self) -> None:
        self.subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self.tasks: set[asyncio.Task[None]] = set()

    def start(self, experiment_id: str, config: ExperimentRequest) -> None:
        task = asyncio.create_task(self.run(experiment_id, config))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def publish(self, experiment_id: str, snapshot: MetricSnapshot | dict[str, Any]) -> None:
        message = snapshot.model_dump() if isinstance(snapshot, MetricSnapshot) else snapshot
        for queue in self.subscribers.get(experiment_id, set()).copy():
            await queue.put(message)

    async def subscribe(self, experiment_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.subscribers.setdefault(experiment_id, set()).add(queue)
        return queue

    def unsubscribe(self, experiment_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.subscribers.get(experiment_id, set()).discard(queue)

    async def run(self, experiment_id: str, config: ExperimentRequest) -> None:
        session = SessionLocal()
        experiment = session.get(Experiment, experiment_id)
        if experiment is None:
            session.close()
            return
        try:
            experiment.status = "RUNNING"
            session.commit()
            for elapsed in range(config.duration_sec + 1):
                if elapsed:
                    await asyncio.sleep(1)
                for protocol in config.protocols:
                    throughput = self._throughput(protocol, config, elapsed)
                    sent = int(max(1, throughput * 125000 * max(elapsed, 1)))
                    received = round(sent * (1 - config.packet_loss_pct / 100))
                    await self.publish(experiment_id, MetricSnapshot(
                        experiment_id=experiment_id, protocol=protocol, elapsed_sec=elapsed,
                        packets_sent=sent, packets_received=received, throughput_mbps=throughput,
                        latency_ms=config.latency_ms, packet_loss_pct=config.packet_loss_pct,
                    ))
            for protocol in config.protocols:
                session.add(Result(
                    experiment_id=experiment_id, protocol=protocol,
                    throughput_mbps=self._throughput(protocol, config, config.duration_sec),
                    latency_ms=config.latency_ms, jitter_ms=round(config.latency_ms * 0.08, 2),
                    packet_loss_pct=config.packet_loss_pct, cpu_usage_pct=self._cpu(protocol, config),
                    transfer_time_sec=float(config.duration_sec),
                ))
            experiment.status = "COMPLETE"
            experiment.completed_at = datetime.now(timezone.utc)
            session.commit()
            await self.publish(experiment_id, {"type": "complete", "experiment_id": experiment_id, "status": "COMPLETE"})
        except asyncio.CancelledError:
            experiment.status = "FAILED"
            experiment.error = "Experiment cancelled"
            session.commit()
            raise
        except Exception as error:
            experiment.status = "FAILED"
            experiment.error = str(error)
            session.commit()
            await self.publish(experiment_id, {"type": "error", "experiment_id": experiment_id, "status": "FAILED", "error": str(error)})
        finally:
            session.close()

    @staticmethod
    def _throughput(protocol: str, config: ExperimentRequest, elapsed: int) -> float:
        efficiency = {"tcp": 0.82, "udp": 0.96, "quic": 0.90}[protocol]
        penalty = 1 - (config.packet_loss_pct / 130) - (config.latency_ms / 5000)
        warmup = min(1, 0.7 + elapsed * 0.1)
        return round(max(0.1, config.bandwidth_mbps * efficiency * penalty * warmup), 2)

    @staticmethod
    def _cpu(protocol: str, config: ExperimentRequest) -> float:
        return round({"tcp": 18, "udp": 12, "quic": 28}[protocol] + config.packet_loss_pct * 0.4, 2)

runner = ExperimentRunner()
