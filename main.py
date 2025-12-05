from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import drive
from database import engine
import models

# Create tables
# models.Base.metadata.create_all(bind=engine)

app = FastAPI()

origins = [
    "http://localhost:5173",  # Vite default
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(drive.router)

@app.get("/")
def read_root():
    return {"message": "PipeDesk Google Drive Backend"}
