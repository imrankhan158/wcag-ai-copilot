from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.health import router as health_router
from app.api.routes.chat import router as chat_router
from app.api.routes.check import router as check_router
from app.api.routes.criteria import router as criteria_router
from app.api.routes.auth_routes import router as auth_router
from app.api.routes.history import router as history_router

from app.db.session import Base, sync_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on startup
    print("Auto-creating PostgreSQL tables...", flush=True)
    Base.metadata.create_all(bind=sync_engine)
    print("PostgreSQL tables checked/created.", flush=True)
    yield

app = FastAPI(
    title="WCAG AI Copilot API",
    description="API for the WCAG AI Copilot service, providing endpoints for accessibility analysis and recommendations.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins or specify React port 5173
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/health", tags=["Health Check"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(check_router, prefix="/api", tags=["Check"])
app.include_router(criteria_router, prefix="/api", tags=["Criteria"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(history_router, prefix="/api", tags=["History"])
