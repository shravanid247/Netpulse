import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.database import check_db_connection, get_db
from app.db.models import Experiment
from app.models.schemas import ExperimentRequest, ExperimentResponse, ResultResponse
from app.services.experiment_runner import runner

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

    return ExperimentResponse(
        experiment_id=experiment.id,
        status=experiment.status,
        config=ExperimentRequest(
            protocols=protocols,
            bandwidth_mbps=experiment.bandwidth_mbps,
            latency_ms=experiment.latency_ms,
            packet_loss_pct=experiment.packet_loss_pct,
            duration_sec=experiment.duration_sec,
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

@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(Experiment).order_by(Experiment.created_at.desc())).all()
    results = []
    for row in rows:
        try:
            protocols = json.loads(row.protocols)
        except Exception:
            protocols = [row.protocols]
        results.append({
            "experiment_id": row.id,
            "status": row.status,
            "protocols": protocols,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return results

