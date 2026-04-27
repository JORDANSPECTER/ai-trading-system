from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import json
import os

app = FastAPI()

# Allow frontend later
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to signal file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIGNAL_PATH = os.path.join(BASE_DIR, "engine", "cougar_signal.json")


@app.get("/")
def home():
    return {"message": "COUGAR API is running"}


@app.get("/api/signal")
def get_signal():
    try:
        with open(SIGNAL_PATH, "r") as f:
            data = json.load(f)
        return data
    except Exception as e:
        return {"error": str(e)}
