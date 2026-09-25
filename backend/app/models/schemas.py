from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

Protocol = Literal["tcp", "udp", "quic"]

class ExperimentRequest(BaseModel):
    protocols: list[Protocol] = Field(min_length=1)
    bandwidth_mbps: float = Field(gt=0, le=1000)
    latency_ms: float = Field(ge=0, le=5000)
    packet_loss_pct: float = Field(ge=0, le=100)
    duration_sec: int = Field(ge=1, le=3600)

class MetricSnapshot(BaseModel):
    experiment_id: str
    protocol: str
    elapsed_sec: float
    packets_sent: int
    packets_received: int
    throughput_mbps: float
    latency_ms: float
    packet_loss_pct: float

class ResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    protocol: str
    throughput_mbps: float
    latency_ms: float
    jitter_ms: float
    packet_loss_pct: float
    cpu_usage_pct: float
    transfer_time_sec: float

class ExperimentResponse(BaseModel):
    experiment_id: str
    status: str
    config: ExperimentRequest
    results: list[ResultResponse] = []
    error: str | None = None
