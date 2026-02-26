"""
Temp-Mon FastAPI server.
- Serves the pre-built React frontend from ../frontend/dist
- Provides REST + SSE API for the control panel
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (one level above backend/)
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from controller import Controller

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("main")

# ── App lifecycle ─────────────────────────────────────────────────────────────
controller = Controller()
_bg_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _bg_task
    _bg_task = asyncio.create_task(controller.run())
    log.info("Background controller started")
    yield
    if _bg_task:
        _bg_task.cancel()
        try:
            await _bg_task
        except asyncio.CancelledError:
            pass
    log.info("Shutdown complete")


app = FastAPI(title="Temp-Mon", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Snapshot of the current system state."""
    state = controller.get_current()
    if state is None:
        raise HTTPException(status_code=503, detail="Controller not ready yet")
    return state


@app.get("/api/stream")
async def sse_stream():
    """Server-Sent Events stream - pushes a JSON event on every poll cycle."""
    queue = controller.subscribe()

    async def event_generator():
        try:
            # Send current state immediately so UI doesn't wait for first poll
            current = controller.get_current()
            if current:
                yield f"data: {json.dumps(current)}\n\n"

            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    # Send a keepalive comment so the connection stays alive
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            controller.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/relay/{name}/override")
async def set_override(name: str, state: bool):
    """Manually force a relay on (state=true) or off (state=false)."""
    if not controller.override_relay(name, state):
        raise HTTPException(status_code=404, detail=f"Unknown relay: {name}")
    return {"relay": name, "state": state, "is_overridden": True}


@app.delete("/api/relay/{name}/override")
async def clear_override(name: str):
    """Return a relay to automatic temperature-based control."""
    if not controller.clear_relay_override(name):
        raise HTTPException(status_code=404, detail=f"Unknown relay: {name}")
    return {"relay": name, "is_overridden": False}


@app.put("/api/can/enabled")
async def set_can_enabled(state: bool):
    """Enable or disable the CAN bus commander at runtime."""
    controller.set_can_enabled(state)
    return {"can_enabled": state}


# ── Static frontend ───────────────────────────────────────────────────────────
_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
    log.info("Serving frontend from %s", _dist)
else:
    log.warning("Frontend dist not found at %s – run 'npm run build' in frontend/", _dist)

    @app.get("/")
    async def root():
        return {"message": "Frontend not built. Run `npm run build` inside frontend/"}


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_level="info")
