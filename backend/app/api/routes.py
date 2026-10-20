import json
import re
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.database import check_db_connection, get_db
from app.db.models import Experiment
from app.models.schemas import (
    ComparisonResponse,
    ExperimentRequest,
    ExperimentResponse,
    ExperimentSummaryItem,
    PresetItem,
    ResultResponse,
)
from app.services.analytics import (
    build_comparison,
    export_experiment_csv,
    export_experiment_json,
)
from app.services.experiment_runner import runner

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RAW_RESULTS_DIR = PROJECT_ROOT / "results" / "raw"
SAFE_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
ALLOWED_PROTOCOLS = {"tcp", "udp", "quic"}

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "netpulse-api", "version": "1.0.0"}

@router.get("/health/db")
def health_db(response: Response) -> dict[str, str]:
    ok, message = check_db_connection()
    if not ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "disconnected", "detail": message}
    return {"status": "ok", "database": "connected"}

@router.get("/presets", response_model=dict[str, PresetItem])
def get_presets() -> dict[str, Any]:
    """Retrieve all verified standardized network condition presets."""
    from network.presets import list_presets
    return list_presets()

@router.post("/experiment/start", status_code=status.HTTP_201_CREATED)
async def start_experiment(
    request: ExperimentRequest,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    experiment_id = f"EXP-{uuid4().hex[:6].upper()}"
    experiment = Experiment(
        id=experiment_id,
        status="PENDING",
        protocols=json.dumps(request.protocols),
        bandwidth_mbps=request.bandwidth_mbps,
        latency_ms=request.latency_ms,
        packet_loss_pct=request.packet_loss_pct,
        duration_sec=request.duration_sec,
    )
    db.add(experiment)
    db.commit()
    runner.start(experiment_id, request)
    return {"experiment_id": experiment_id, "status": "PENDING"}

def get_experiment_or_404(experiment_id: str, db: Session) -> Experiment:
    if not SAFE_ID_REGEX.match(experiment_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid experiment ID format: '{experiment_id}'",
        )
    query = (
        select(Experiment)
        .options(selectinload(Experiment.results))
        .where(Experiment.id == experiment_id)
    )
    experiment = db.scalars(query).first()
    if not experiment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_id}' not found",
        )
    return experiment

@router.get("/experiment/status/{experiment_id}")
def experiment_status(
    experiment_id: str,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    experiment = get_experiment_or_404(experiment_id, db)
    return {
        "experiment_id": experiment.id,
        "status": experiment.status,
        "error": experiment.error,
    }

@router.get("/experiment/results/{experiment_id}", response_model=ExperimentResponse)
def experiment_results(
    experiment_id: str,
    db: Session = Depends(get_db),
) -> ExperimentResponse:
    experiment = get_experiment_or_404(experiment_id, db)
    try:
        protocols = json.loads(experiment.protocols)
    except Exception:
        protocols = [experiment.protocols]

    topo_spec = None
    topo_file = RAW_RESULTS_DIR / f"{experiment.id}_topo.json"
    if topo_file.is_file():
        try:
            topo_spec = json.loads(topo_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    return ExperimentResponse(
        experiment_id=experiment.id,
        status=experiment.status,
        config=ExperimentRequest(
            protocols=protocols,
            bandwidth_mbps=experiment.bandwidth_mbps,
            latency_ms=experiment.latency_ms,
            packet_loss_pct=experiment.packet_loss_pct,
            duration_sec=experiment.duration_sec,
            topology=topo_spec,
        ),
        results=[
            ResultResponse(
                protocol=result.protocol,
                throughput_mbps=result.throughput_mbps,
                latency_ms=result.latency_ms,
                jitter_ms=result.jitter_ms,
                packet_loss_pct=result.packet_loss_pct,
                cpu_usage_pct=result.cpu_usage_pct,
                transfer_time_sec=result.transfer_time_sec,
                handshake_success=result.handshake_success,
                raw_output=result.raw_output,
            )
            for result in experiment.results
        ],
        raw_result_path=experiment.raw_result_path,
        error=experiment.error,
    )

@router.get("/experiment/compare/{experiment_id}", response_model=ComparisonResponse)
def compare_experiment(
    experiment_id: str,
    db: Session = Depends(get_db),
) -> ComparisonResponse:
    """Evaluate performance across protocols and derive comparative research metrics."""
    experiment = get_experiment_or_404(experiment_id, db)
    return build_comparison(experiment)

@router.get("/experiment/export/{experiment_id}")
def export_experiment(
    experiment_id: str,
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: Session = Depends(get_db),
) -> Response:
    """Export complete research dataset in downloadable CSV or JSON format."""
    experiment = get_experiment_or_404(experiment_id, db)
    comp = build_comparison(experiment)

    if format == "json":
        data = export_experiment_json(experiment, comp)
        return Response(
            content=json.dumps(data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="netpulse_{experiment_id}.json"'},
        )

    csv_data = export_experiment_csv(experiment, comp)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="netpulse_{experiment_id}.csv"'},
    )

@router.get("/experiment/raw/{experiment_id}/{protocol}")
def get_raw_result(
    experiment_id: str,
    protocol: str,
    db: Session = Depends(get_db),
) -> Response:
    """Safely retrieve the raw JSON benchmark artifact for an experiment and protocol."""
    if not SAFE_ID_REGEX.match(experiment_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid experiment ID format")

    proto_lower = protocol.lower().strip()
    if proto_lower not in ALLOWED_PROTOCOLS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid protocol '{protocol}'. Allowed: {', '.join(sorted(ALLOWED_PROTOCOLS))}",
        )

    experiment = get_experiment_or_404(experiment_id, db)

    # Secure path verification
    target = (RAW_RESULTS_DIR / f"{experiment.id}_{proto_lower}.json").resolve()
    if target.parent != RAW_RESULTS_DIR.resolve() or not target.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Raw result artifact not found for experiment '{experiment_id}' protocol '{proto_lower}'",
        )

    return Response(content=target.read_text(encoding="utf-8"), media_type="application/json")

@router.get("/experiments", response_model=list[ExperimentSummaryItem])
def list_experiments(db: Session = Depends(get_db)) -> list[ExperimentSummaryItem]:
    """Retrieve historical experiments with summary metrics while preserving backward compatibility."""
    rows = db.scalars(
        select(Experiment)
        .options(selectinload(Experiment.results))
        .order_by(Experiment.created_at.desc())
    ).all()
    results = []
    for row in rows:
        try:
            protocols = json.loads(row.protocols)
        except Exception:
            protocols = [row.protocols]

        results_summary = [
            {
                "protocol": r.protocol,
                "throughput_mbps": r.throughput_mbps,
                "latency_ms": r.latency_ms,
                "packet_loss_pct": r.packet_loss_pct,
                "cpu_usage_pct": r.cpu_usage_pct,
                "handshake_success": r.handshake_success,
            }
            for r in row.results
        ]

        results.append(
            ExperimentSummaryItem(
                experiment_id=row.id,
                status=row.status,
                protocols=protocols,
                bandwidth_mbps=row.bandwidth_mbps,
                latency_ms=row.latency_ms,
                packet_loss_pct=row.packet_loss_pct,
                duration_sec=row.duration_sec,
                created_at=row.created_at.isoformat() if row.created_at else None,
                completed_at=row.completed_at.isoformat() if row.completed_at else None,
                results_summary=results_summary,
            )
        )
    return results
