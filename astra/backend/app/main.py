from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
from app.routers.auth import router as auth_router
from app.routers.requirements import router as requirements_router
from app.routers.projects import projects_router, traceability_router, artifacts_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup (Alembic preferred for production)
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="ASTRA — Systems Engineering Platform",
    description="Requirements tracking, traceability, and systems engineering management.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers under /api/v1
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(requirements_router, prefix=API_PREFIX)
app.include_router(traceability_router, prefix=API_PREFIX)
app.include_router(artifacts_router, prefix=API_PREFIX)


@app.get("/")
def root():
    return {
        "name": "ASTRA",
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
