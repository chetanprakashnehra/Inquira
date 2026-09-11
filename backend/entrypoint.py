import sys
import os
import traceback

print("=== Starting Inquira Backend Container ===", flush=True)
print(f"Python version: {sys.version}", flush=True)
port = int(os.environ.get("PORT", 10000))
print(f"PORT: {port}", flush=True)
print(f"ENVIRONMENT: {os.environ.get('ENVIRONMENT', 'not set')}", flush=True)

try:
    print("Loading application configuration...", flush=True)
    from app.config import settings
    print(f"Settings loaded: {settings.PROJECT_NAME} ({settings.ENVIRONMENT})", flush=True)
    
    print("Importing FastAPI core...", flush=True)
    from app.core.database import init_db
    print("Importing API router...", flush=True)
    from app.api.v1.router import api_router
    print("Importing FastAPI application...", flush=True)
    from app.main import app
    print("FastAPI app imported successfully!", flush=True)
except Exception as e:
    print(f"!!! CRITICAL STARTUP ERROR: {e} !!!", flush=True)
    traceback.print_exc()
    sys.exit(1)


if __name__ == "__main__":
    import uvicorn
    print(f"Launching Uvicorn on 0.0.0.0:{port}...", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

