from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from contextlib import asynccontextmanager
import uvicorn
import os
import uuid
import shutil
from pathlib import Path
from typing import Optional
from database.db import init_db, get_db, Photo
from sqlalchemy.orm import Session

# Base directory = folder where main.py lives
BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE_MB = 15
MOODS = {"nights", "mountains", "calm", "fire"}

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Échos du Silence API",
    description="Backend for the photography portfolio",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve uploaded images as static files
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Serve static assets (music, etc.)
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Serve frontend ───────────────────────────────────────────────────────────
@app.get("/")
def root():
    return FileResponse(str(BASE_DIR / "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}


# ─── Get all photos ───────────────────────────────────────────────────────────
@app.get("/photos")
def get_photos(
    mood: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    query = db.query(Photo).order_by(Photo.created_at.desc())
    if mood and mood != "all":
        if mood not in MOODS:
            raise HTTPException(status_code=400, detail=f"Invalid mood. Choose from: {', '.join(MOODS)}")
        query = query.filter(Photo.mood == mood)
    total = query.count()
    photos = query.offset(offset).limit(limit).all()
    return {
        "total": total,
        "photos": [p.to_dict() for p in photos]
    }


# ─── Get single photo ─────────────────────────────────────────────────────────
@app.get("/photos/{photo_id}")
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo.to_dict()


# ─── Upload photo ─────────────────────────────────────────────────────────────
@app.post("/photos/upload", status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    caption: str = Form(...),
    mood: str = Form(...),
    db: Session = Depends(get_db)
):
    # Validate mood
    if mood not in MOODS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mood '{mood}'. Choose from: {', '.join(MOODS)}"
        )

    # Validate caption
    caption = caption.strip()
    if not caption or len(caption) > 200:
        raise HTTPException(
            status_code=400,
            detail="Caption must be between 1 and 200 characters"
        )

    # Validate file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Validate file size
    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f}MB). Maximum allowed: {MAX_FILE_SIZE_MB}MB"
        )

    # Save file with unique name
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    file_path = UPLOAD_DIR / unique_filename
    with open(file_path, "wb") as f:
        f.write(contents)

    # Save to database
    photo = Photo(
        filename=unique_filename,
        original_filename=file.filename,
        caption=caption,
        mood=mood,
        file_size=len(contents)
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    return {
        "message": "Photo uploaded successfully",
        "photo": photo.to_dict()
    }


# ─── Delete photo ─────────────────────────────────────────────────────────────
@app.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")

    # Delete file from disk
    file_path = UPLOAD_DIR / photo.filename
    if file_path.exists():
        file_path.unlink()

    db.delete(photo)
    db.commit()
    return {"message": f"Photo {photo_id} deleted successfully"}


# ─── Stats ────────────────────────────────────────────────────────────────────
@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Photo).count()
    by_mood = {}
    for mood in MOODS:
        by_mood[mood] = db.query(Photo).filter(Photo.mood == mood).count()
    return {"total_photos": total, "by_mood": by_mood}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
