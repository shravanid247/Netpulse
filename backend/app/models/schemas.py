import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Protocol = Literal["tcp", "udp", "quic"]
NodeType = Literal["client", "switch", "server"]

SAFE_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")

class TopologyNode(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="Unique node identifier")
    label: str = Field(min_length=1, max_length=64, description="Display label")
    type: NodeType = Field(description="Node role: client, switch, or server")

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        v = v.strip()
        if not SAFE_IDENTIFIER_REGEX.match(v):
            raise ValueError(f"Invalid node ID '{v}'. Must be alphanumeric with hyphens, underscores, or dots.")
        return v

class TopologyEdge(BaseModel):
    id: str = Field(min_length=1, max_length=64, description="Unique edge identifier")
    source: str = Field(min_length=1, max_length=64, description="Source node ID")
    target: str = Field(min_length=1, max_length=64, description="Target node ID")
    protocol: Protocol | None = Field(default=None, description="Transport protocol for this link")
    bandwidth_mbps: float | None = Field(default=None, gt=0, le=10000, description="Link bandwidth override in Mbps")
    latency_ms: float | None = Field(default=None, ge=0, le=5000, description="Link latency override in ms")
    packet_loss_pct: float | None = Field(default=None, ge=0, le=100, description="Link loss override percentage")

class TopologySpec(BaseModel):
    nodes: list[TopologyNode] = Field(min_length=2, max_length=25, description="Network nodes in graph")
    edges: list[TopologyEdge] = Field(min_length=1, max_length=40, description="Links between nodes")

    @field_validator("nodes")
    @classmethod
    def validate_nodes(cls, nodes: list[TopologyNode]) -> list[TopologyNode]:
        ids = [n.id for n in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate node IDs found in topology specification")
        types = {n.type for n in nodes}
        if "client" not in types:
            raise ValueError("Topology must contain at least one client host (traffic generator)")
        if "server" not in types:
            raise ValueError("Topology must contain at least one server host (traffic receiver)")
        return nodes

    @model_validator(mode="after")
    def validate_graph_connectivity(self) -> "TopologySpec":
        node_ids = {n.id for n in self.nodes}
        for edge in self.edges:
            if edge.source not in node_ids:
                raise ValueError(f"Edge source '{edge.source}' does not exist in topology nodes")
            if edge.target not in node_ids:
                raise ValueError(f"Edge target '{edge.target}' does not exist in topology nodes")
            if edge.source == edge.target:
                raise ValueError(f"Self-loop detected on edge '{edge.id}' ({edge.source} -> {edge.target})")

        # Build adjacency graph for undirected traversal
        adj: dict[str, set[str]] = {n.id: set() for n in self.nodes}
        for edge in self.edges:
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)

        # Check path from at least one client to at least one server
        clients = [n.id for n in self.nodes if n.type == "client"]
        servers = {n.id for n in self.nodes if n.type == "server"}

        path_found = False
        for client in clients:
            visited = set()
            queue = [client]
            while queue:
                curr = queue.pop(0)
                if curr in servers:
                    path_found = True
                    break
                visited.add(curr)
                for neighbor in adj.get(curr, set()):
                    if neighbor not in visited and neighbor not in queue:
                        queue.append(neighbor)
            if path_found:
                break

        if not path_found:
            raise ValueError("No connected path found between any client host and server host in topology")

        return self

class ExperimentRequest(BaseModel):
    protocols: list[Protocol] = Field(min_length=1, description="List of protocols to evaluate")
    bandwidth_mbps: float = Field(gt=0, le=1000, description="Bandwidth in Mbps")
    latency_ms: float = Field(ge=0, le=5000, description="Latency in ms")
    packet_loss_pct: float = Field(ge=0, le=100, description="Packet loss percentage")
    duration_sec: int = Field(ge=1, le=3600, description="Duration in seconds")
    topology: TopologySpec | None = Field(default=None, description="Dynamic network topology specification")

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

class PresetItem(BaseModel):
    bandwidth_mbps: float
    latency_ms: float
    packet_loss_pct: float

class ProtocolMetrics(BaseModel):
    protocol: str
    throughput_mbps: float
    latency_ms: float
    jitter_ms: float | None = None
    packet_loss_pct: float
    cpu_usage_pct: float
    transfer_time_sec: float
    handshake_success: bool | None = None
    throughput_efficiency_pct: float | None = None
    throughput_ratio_vs_tcp: float | None = None
    latency_inflation_pct: float | None = None
    cpu_cost_per_mbps: float | None = None

class ComparisonSummary(BaseModel):
    fastest_protocol: str | None = None
    lowest_latency_protocol: str | None = None
    most_cpu_efficient: str | None = None
    protocol_count: int = 0
    notes: list[str] = []

class ComparisonResponse(BaseModel):
    experiment_id: str
    status: str
    config: ExperimentRequest
    protocols: dict[str, ProtocolMetrics] = {}
    summary: ComparisonSummary

class ExperimentSummaryItem(BaseModel):
    experiment_id: str
    status: str
    protocols: list[str]
    bandwidth_mbps: float | None = None
    latency_ms: float | None = None
    packet_loss_pct: float | None = None
    duration_sec: int | None = None
    created_at: str | None = None
    completed_at: str | None = None
    results_summary: list[dict[str, Any]] = []
