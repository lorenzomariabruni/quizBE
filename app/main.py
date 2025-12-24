from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from app.socket_manager import sio
from app.routes import router
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Quiz Backend", version="1.0.0")

# CORS - Allow all origins for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes with /api prefix
app.include_router(router, prefix="/api")

# Mount Socket.IO
socket_app = socketio.ASGIApp(sio, app)

@app.get("/")
def root():
    return {"message": "Quiz Backend API", "status": "running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:socket_app", host="0.0.0.0", port=8000, reload=True)