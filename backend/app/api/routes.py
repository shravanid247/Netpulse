import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.database import SessionLocal
from app.db.models import Experiment
from app.models.schemas import ExperimentRequest
from app.services.experiment_runner import runner

router = APIRouter()

@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "netpulse-api", "version": "1.0.0"}

@router.post("/experiment/start")
async def start_experiment(request: ExperimentRequest) -> dict[str, str]:
    experiment_id = f"EXP-{uuid4().hex[:6].upper()}"
    session = SessionLocal()
    try:
        session.add(Experiment(id=experiment_id, status="PENDING", protocols=json.dumps(request.protocols), bandwidth_mbps=request.bandwidth_mbps, latency_ms=request.latency_ms, packet_loss_pct=request.packet_loss_pct, duration_sec=request.duration_sec))
        session.commit()
    finally:
        session.close()
    runner.start(experiment_id, request)
    return {"experiment_id": experiment_id, "status": "PENDING"}

def get_experiment(experiment_id: str) -> Experiment:
    session = SessionLocal()
    experiment = session.scalars(select(Experiment).options(selectinload(Experiment.results)).where(Experiment.id == experiment_id)).first()
    session.expunge(experiment) if experiment else None
    session.close()
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return experiment

@router.get("/experiment/status/{experiment_id}")
def experiment_status(experiment_id: str) -> dict[str, Any]:
    experiment = get_experiment(experiment_id)
    return {"experiment_id": experiment.id, "status": experiment.status, "error": experiment.error}

@router.get("/experiment/results/{experiment_id}")
def experiment_results(experiment_id: str) -> dict[str, Any]:
    experiment = get_experiment(experiment_id)
    return {"experiment_id": experiment.id, "status": experiment.status, "config": {"protocols": json.loads(experiment.protocols), "bandwidth_mbps": experiment.bandwidth_mbps, "latency_ms": experiment.latency_ms, "packet_loss_pct": experiment.packet_loss_pct, "duration_sec": experiment.duration_sec}, "results": [result.__dict__ for result in experiment.results], "error": experiment.error}

@router.get("/experiments")
def list_experiments() -> list[dict[str, Any]]:
    session = SessionLocal()
    try:
        rows = session.scalars(select(Experiment).order_by(Experiment.created_at.desc())).all()
        return [{"experiment_id": row.id, "status": row.status, "protocols": json.loads(row.protocols), "created_at": row.created_at.isoformat()} for row in rows]
    finally:
        session.close()

@router.websocket("/ws/experiment/{experiment_id}")
async def experiment_socket(websocket: WebSocket, experiment_id: str) -> None:
    await websocket.accept()
    get_experiment(experiment_id)
    queue = await runner.subscribe(experiment_id)
    try:
        while True:
            await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, RuntimeError):
        runner.unsubscribe(experiment_id, queue)
