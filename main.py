from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.router import router

app = FastAPI(
    title="AllConverter",
    description="Multi-format file converter collection",
    version="0.1.0",
)

app.include_router(router, prefix="/api")

# Serve static/ at root; html=True makes directory requests serve index.html
app.mount("/", StaticFiles(directory="static", html=True), name="static")
