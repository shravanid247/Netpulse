import asyncio
import json
import logging
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.database import SessionLocal
from app.db.models import Experiment, Result
from app.models.schemas import ExperimentRequest, MetricSnapshot

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_RESULTS_DIR = PROJECT_ROOT / "results" / "raw"
SYSTEM_HELPER_PATH = Path("/usr/local/libexec/netpulse-runner")
FALLBACK_HELPER_PATH = PROJECT_ROOT / "experiments" / "privileged_helper.py"


def get_helper_command() -> list[str]:
    """Resolve helper executable path."""
    if SYSTEM_HELPER_PATH.is_file() and os.access(SYSTEM_HELPER_PATH, os.X_OK):
        return ["sudo", str(SYSTEM_HELPER_PATH)]
    # Fallback for development environments before system installation
    return ["sudo", "/usr/bin/python3", str(FALLBACK_HELPER_PATH)]


class ExperimentRunner:
    def __init__(self) -> None:
        self.subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    @property
    def execution_mode(self) -> str:
        return os.getenv("NETPULSE_EXECUTION_MODE", "simulation").lower().strip()

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
        # Protect Mininet and traffic control resources from concurrent runs
        async with self._lock:
            session = SessionLocal()
            experiment = session.get(Experiment, experiment_id)
            if experiment is None:
                session.close()
                return

            try:
                experiment.status = "RUNNING"
                session.commit()

                if self.execution_mode == "real":
                    await self._run_real(experiment, config, session)
                else:
                    await self._run_simulation(experiment, config, session)

                experiment.status = "COMPLETE"
                experiment.completed_at = datetime.now(timezone.utc)
                session.commit()
                await self.publish(experiment_id, {"type": "complete", "experiment_id": experiment_id, "status": "COMPLETE"})
            except asyncio.CancelledError:
                logger.warning("Experiment %s was cancelled", experiment_id)
                experiment.status = "FAILED"
                experiment.error = "Experiment cancelled"
                session.commit()
                await self.publish(experiment_id, {"type": "error", "experiment_id": experiment_id, "status": "FAILED", "error": "Experiment cancelled"})
                raise
            except Exception as error:
                logger.exception("Experiment execution failed for %s: %s", experiment_id, error)
                experiment.status = "FAILED"
                experiment.error = str(error)
                session.commit()
                await self.publish(experiment_id, {"type": "error", "experiment_id": experiment_id, "status": "FAILED", "error": str(error)})
            finally:
                session.close()

    async def _run_real(self, experiment: Experiment, config: ExperimentRequest, session: Any) -> None:
        """Execute real Mininet + iperf3 experiments via the privileged helper."""
        RAW_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        saved_paths: list[str] = []
        helper_base_cmd = get_helper_command()

        try:
            for protocol in config.protocols:
                raw_file = RAW_RESULTS_DIR / f"{experiment.id}_{protocol}.json"
                cmd = helper_base_cmd + [
                    "--action", "run",
                    "--experiment-id", experiment.id,
                    "--protocol", protocol,
                    "--duration", str(config.duration_sec),
                    "--bandwidth", str(config.bandwidth_mbps),
                    "--latency", str(config.latency_ms),
                    "--packet-loss", str(config.packet_loss_pct),
                    "--output-file", str(raw_file),
                ]

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(PROJECT_ROOT),
                )
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(),
                        timeout=max(45, config.duration_sec + 35),
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    raise RuntimeError(f"Helper timed out for protocol {protocol}")

                if proc.returncode != 0:
                    err_text = stderr_bytes.decode().strip() or stdout_bytes.decode().strip()
                    # Handle transient iperf3 UDP control socket timeout under heavy link loss
                    if "Resource temporarily unavailable" in err_text:
                        logger.warning("iperf3 transient socket error for %s; cleaning and retrying once...", protocol)
                        cleanup_cmd = helper_base_cmd + ["--action", "cleanup"]
                        clean_retry = await asyncio.create_subprocess_exec(
                            *cleanup_cmd,
                            stdout=asyncio.subprocess.DEVNULL,
                            stderr=asyncio.subprocess.DEVNULL,
                            cwd=str(PROJECT_ROOT),
                        )
                        await asyncio.wait_for(clean_retry.wait(), timeout=15)
                        await asyncio.sleep(1.0)

                        retry_proc = await asyncio.create_subprocess_exec(
                            *cmd,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            cwd=str(PROJECT_ROOT),
                        )
                        stdout_bytes, stderr_bytes = await asyncio.wait_for(
                            retry_proc.communicate(), timeout=max(45, config.duration_sec + 35)
                        )
                        if retry_proc.returncode != 0:
                            err_text = stderr_bytes.decode().strip() or stdout_bytes.decode().strip()
                            raise RuntimeError(f"Helper failed for protocol {protocol} (exit code {retry_proc.returncode}): {err_text}")
                    else:
                        raise RuntimeError(f"Helper failed for protocol {protocol} (exit code {proc.returncode}): {err_text}")

                try:
                    result_data = json.loads(stdout_bytes.decode())
                except json.JSONDecodeError as err:
                    raise RuntimeError(f"Failed to parse helper output for {protocol}: {err}")

                raw_output = result_data.get("raw_output")
                loss_val = result_data.get("packet_loss_pct")
                measured_loss = float(loss_val) if loss_val is not None else 0.0

                result_obj = Result(
                    experiment_id=experiment.id,
                    protocol=protocol,
                    throughput_mbps=result_data.get("throughput_mbps", 0.0),
                    latency_ms=result_data.get("latency_ms", 0.0),
                    jitter_ms=result_data.get("jitter_ms"),
                    packet_loss_pct=measured_loss,
                    cpu_usage_pct=result_data.get("cpu_usage_pct", 0.0),
                    transfer_time_sec=result_data.get("transfer_time_sec", float(config.duration_sec)),
                    handshake_success=result_data.get("handshake_success"),
                    raw_output=raw_output,
                )
                session.add(result_obj)
                saved_paths.append(str(raw_file))

                # Publish final snapshot for this protocol
                await self.publish(experiment.id, MetricSnapshot(
                    experiment_id=experiment.id,
                    protocol=protocol,
                    elapsed_sec=float(config.duration_sec),
                    packets_sent=int(result_data.get("throughput_mbps", 0.0) * 125000 * config.duration_sec),
                    packets_received=int(result_data.get("throughput_mbps", 0.0) * 125000 * config.duration_sec * (1 - measured_loss / 100)),
                    throughput_mbps=result_data.get("throughput_mbps", 0.0),
                    latency_ms=result_data.get("latency_ms", 0.0),
                    packet_loss_pct=measured_loss,
                ))

            if saved_paths:
                experiment.raw_result_path = ";".join(saved_paths)
        finally:
            # Guarantee Mininet and traffic control cleanup runs even on error or cancellation
            cleanup_cmd = helper_base_cmd + ["--action", "cleanup"]
            try:
                clean_proc = await asyncio.create_subprocess_exec(
                    *cleanup_cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    cwd=str(PROJECT_ROOT),
                )
                await asyncio.wait_for(clean_proc.wait(), timeout=15)
            except Exception as clean_err:
                logger.warning("Cleanup command error: %s", clean_err)
            # Allow virtual interfaces and OVS kernel datapath to settle before next experiment
            await asyncio.sleep(1.0)

    async def _run_simulation(self, experiment: Experiment, config: ExperimentRequest, session: Any) -> None:
        """Run simulated experiment metrics."""
        RAW_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        for elapsed in range(config.duration_sec + 1):
            if elapsed:
                await asyncio.sleep(1)
            for protocol in config.protocols:
                throughput = self._throughput(protocol, config, elapsed)
                sent = int(max(1, throughput * 125000 * max(elapsed, 1)))
                received = round(sent * (1 - config.packet_loss_pct / 100))
                await self.publish(experiment.id, MetricSnapshot(
                    experiment_id=experiment.id, protocol=protocol, elapsed_sec=elapsed,
                    packets_sent=sent, packets_received=received, throughput_mbps=throughput,
                    latency_ms=config.latency_ms, packet_loss_pct=config.packet_loss_pct,
                ))

        sim_paths = []
        for protocol in config.protocols:
            jitter = round(config.latency_ms * 0.08, 2) if protocol == "udp" else None
            handshake_ok = True if protocol == "quic" else None
            simulated_raw = json.dumps({
                "mode": "simulation",
                "protocol": protocol,
                "duration_sec": config.duration_sec,
                "target_bandwidth_mbps": config.bandwidth_mbps,
                "target_latency_ms": config.latency_ms,
                "target_packet_loss_pct": config.packet_loss_pct,
                "throughput_mbps": self._throughput(protocol, config, config.duration_sec),
            }, indent=2)
            sim_file = RAW_RESULTS_DIR / f"{experiment.id}_{protocol}.json"
            sim_file.write_text(simulated_raw, encoding="utf-8")
            sim_paths.append(str(sim_file))

            session.add(Result(
                experiment_id=experiment.id, protocol=protocol,
                throughput_mbps=self._throughput(protocol, config, config.duration_sec),
                latency_ms=config.latency_ms, jitter_ms=jitter,
                packet_loss_pct=config.packet_loss_pct, cpu_usage_pct=self._cpu(protocol, config),
                transfer_time_sec=float(config.duration_sec),
                handshake_success=handshake_ok,
                raw_output=simulated_raw,
            ))

        if sim_paths:
            experiment.raw_result_path = ";".join(sim_paths)

    @staticmethod
    def _throughput(protocol: str, config: ExperimentRequest, elapsed: int) -> float:
        efficiency = {"tcp": 0.82, "udp": 0.96, "quic": 0.90}.get(protocol, 0.80)
        penalty = 1 - (config.packet_loss_pct / 130) - (config.latency_ms / 5000)
        warmup = min(1, 0.7 + elapsed * 0.1)
        return round(max(0.1, config.bandwidth_mbps * efficiency * penalty * warmup), 2)

    @staticmethod
    def _cpu(protocol: str, config: ExperimentRequest) -> float:
        return round({"tcp": 18, "udp": 12, "quic": 28}.get(protocol, 15) + config.packet_loss_pct * 0.4, 2)


runner = ExperimentRunner()
