# imports ---------------------------------------------
from fastapi import FastAPI, APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .routers import queue_service
from . import models
from . import schemas
from .Database import engine, SessionLocal, get_db

app = FastAPI()


@app.on_event("startup")
def startup():
    pass  # create_all disabled for diagnosis until /health works
    # models.Base.metadata.create_all(bind=engine)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
#Log 422 validation errors so you can see what the backend expects vs receives.
    errors = exc.errors()
    print("[Queue API] Validation failed:", request.url.path)
    for e in errors:
        print("  -", e.get("loc"), ":", e.get("msg"))
    return JSONResponse(status_code=422, content={"detail": errors})


app.include_router(queue_service.router)
# --------------------------------------------------------