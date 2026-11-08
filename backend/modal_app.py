"""TripAura backend on Modal (serverless containers, free $30/month credits).

Deploy:   modal deploy modal_app.py          (from the backend/ folder)
URL:      https://<workspace>--trip-aura-api.modal.run

Settings come from a Modal secret named "trip-aura-env" (DATABASE_URL, CORS_ORIGINS, ...);
create it with `modal secret create trip-aura-env KEY=value ...` or in the Modal dashboard.
"""
from __future__ import annotations

from pathlib import Path

import modal

BACKEND = Path(__file__).resolve().parent
IGNORE = ["**/__pycache__", "**/*.pyc"]

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(BACKEND / "requirements.txt"))
    .env({"DATA_DIR": "/opt/tripaura/data", "PYTHONUNBUFFERED": "1"})
    .workdir("/root")
    .add_local_dir(BACKEND / "app", "/root/app", copy=True, ignore=IGNORE)
    .add_local_dir(BACKEND / "scripts", "/root/scripts", copy=True, ignore=IGNORE)
    # bake the city index, embedding model and DuckDB extension into the image -> fast cold starts
    .run_commands("python scripts/prefetch.py")
)

app = modal.App("trip-aura-api")


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("trip-aura-env")],
    cpu=1.0,
    memory=2048,           # peak ~750 MB measured (Overture query + AI model + city index)
    timeout=600,
    scaledown_window=300,  # keep a warm container 5 min after the last request, then scale to zero
    min_containers=0,
    max_containers=1,      # one container: shared in-memory caches, predictable cost
)
@modal.concurrent(max_inputs=20)
@modal.asgi_app(label="trip-aura-api")
def api():
    from app.main import app as fastapi_app

    return fastapi_app
