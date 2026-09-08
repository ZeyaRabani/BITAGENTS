"""
Legacy entry point - runs the unified BIT Agents API.

Prefer: python agents_api.py
"""

from agents_api import API_HOST, API_PORT, app

if __name__ == "__main__":
    import uvicorn

    print(f"Starting BIT Agents API (via dca_api shim) on http://{API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)
