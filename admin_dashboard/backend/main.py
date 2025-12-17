from fastapi import FastAPI, Depends
import os
from ... import database
from contextlib import asynccontextmanager
import json

# --- Database Connection ---
DB_CLIENT = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes the database connection on startup."""
    global DB_CLIENT
    if os.getenv("FIRESTORE_EMULATOR_HOST"):
        with open("dummy_creds_for_backend.json") as f:
            cred_json_string = f.read()
        DB_CLIENT = database.init_firebase(cred_json_string, is_json_string=True)
    else:
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        if cred_path:
            DB_CLIENT = database.init_firebase(cred_path)
        else:
            # In a real scenario, you might want to prevent startup if the DB can't be connected.
            print("WARNING: FIREBASE_CREDENTIALS_PATH not set. Real database will not be available.")
    yield
    # No shutdown tasks needed for this simple case
    DB_CLIENT = None


app = FastAPI(lifespan=lifespan)

def get_db():
    """Dependency to get the database client."""
    if DB_CLIENT is None:
        raise Exception("Database client not initialized.")
    return DB_CLIENT

@app.get("/")
def read_root():
    return {"message": "Hello World"}

@app.get("/api/users")
def get_users(db=Depends(get_db)):
    """Returns a list of all users and their XP."""
    users = database.get_leaderboard(db, limit=1000) 
    return {"users": users}
