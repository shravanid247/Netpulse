import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.db.database import create_tables

@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        create_tables()
    except Exception as exc:
        # Avoid exposing raw DSN/passwords in startup logs
        err_first_line = str(exc).split("\n")[0]
        print(f"[NetPulse] Note: Database table initialization during startup: {err_first_line}")
    yield

app = FastAPI(title="NetPulse API", version="1.0.0", lifespan=lifespan)

raw_cors = os.getenv("CORS_ORIGIN", "http://localhost:3000,http://127.0.0.1:3000")
cors_origins = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

