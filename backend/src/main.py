from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router

app = FastAPI(title="DropForge Reservation Engine")

# Allow requests from the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the routes
app.include_router(router, prefix="/api/v1")