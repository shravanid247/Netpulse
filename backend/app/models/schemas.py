from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Protocol = Literal["tcp", "udp", "quic"]

class ExperimentRequest(BaseModel):
    protocols: list[Protocol] = Field(min_length=1, description="List of protocols to evaluate")
    bandwidth_mbps: float = Field(gt=0, le=1000, description="Bandwidth in Mbps")
    latency_ms: float = Field(ge=0, le=5000, description="Latency in ms")
    packet_loss_pct: float = Field(ge=0, le=100, description="Packet loss percentage")
    duration_sec: int = Field(ge=1, le=3600, description="Duration in seconds")

    @field_validator("protocols")
    @classmethod
    def validate_unique_protocols(cls, v: list[Protocol]) -> list[Protocol]:
        seen: set[str] = set()
        unique: list[Protocol] = []
        for p in v:
            if p not in seen:
                seen.add(p)
                unique.append(p)
        return unique

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
    jitter_ms: float | None = None
    packet_loss_pct: float
    cpu_usage_pct: float
    transfer_time_sec: float
    handshake_success: bool | None = None
    raw_output: str | None = None

class ExperimentResponse(BaseModel):
    experiment_id: str
    status: str
    config: ExperimentRequest
    results: list[ResultResponse] = []
    raw_result_path: str | None = None
    error: str | None = None
