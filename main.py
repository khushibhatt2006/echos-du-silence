from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import uvicorn
import os
import cloudinary
import cloudinary.uploader
from pathlib import Path
from typing import Optional
from database.db import init_db, get_db, Photo
from sqlalchemy.orm import Session

BASE_DIR = Path(__file__).resolve().parent

# Cloudinary config
cloudinary.config(
    cloud_name="deqp9v6rq",
    api_key="794723288575591",
    api_secret="75yjbOhvFrOLZbcHcT2Zf7XHZzk"
)

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

# Serve static assets (music, etc.)
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve frontend
@app.get("/")
def root():
    return FileResponse(str(BASE_DIR / "index.html"))

@app.get("/health")
def health():
    return {"status": "ok"}

# Get all photos
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
    return {"total": total, "photos": [p.to_dict() for p in photos]}

# Get single photo
@app.get("/photos/{photo_id}")
def get_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo.to_dict()

# Upload photo to Cloudinary
@app.post("/photos/upload", status_code=201)
async def upload_photo(
    file: UploadFile = File(...),
    caption: str = Form(...),
    mood: str = Form(...),
    db: Session = Depends(get_db)
):
    if mood not in MOODS:
        raise HTTPException(status_code=400, detail=f"Invalid mood '{mood}'. Choose from: {', '.join(MOODS)}")

    caption = caption.strip()
    if not caption or len(caption) > 200:
        raise HTTPException(status_code=400, detail="Caption must be between 1 and 200 characters")

    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File type '{ext}' not allowed.")

    contents = await file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(status_code=413, detail=f"File too large ({size_mb:.1f}MB). Max: {MAX_FILE_SIZE_MB}MB")

    # Upload to Cloudinary
    try:
        result = cloudinary.uploader.upload(
            contents,
            folder="echos-du-silence",
            resource_type="image"
        )
        cloudinary_url = result["secure_url"]
        cloudinary_id = result["public_id"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cloudinary upload failed: {str(e)}")

    # Save to database
    photo = Photo(
        filename=cloudinary_id,
        original_filename=file.filename,
        caption=caption,
        mood=mood,
        file_size=len(contents),
        url=cloudinary_url
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)

    return {"message": "Photo uploaded successfully", "photo": photo.to_dict()}

# Delete photo
@app.delete("/photos/{photo_id}")
def delete_photo(photo_id: int, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo not found")
    try:
        cloudinary.uploader.destroy(photo.filename)
    except:
        pass
    db.delete(photo)
    db.commit()
    return {"message": f"Photo {photo_id} deleted successfully"}

# Stats
@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Photo).count()
    by_mood = {}
    for mood in MOODS:
        by_mood[mood] = db.query(Photo).filter(Photo.mood == mood).count()
    return {"total_photos": total, "by_mood": by_mood}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
