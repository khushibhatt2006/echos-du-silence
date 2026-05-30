from sqlalchemy import create_engine, Column, Integer, String, DateTime, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./echos_du_silence.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Photo(Base):
    __tablename__ = "photos"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, nullable=False)       # Cloudinary public_id
    original_filename = Column(String, nullable=False)
    caption = Column(String(200), nullable=False)
    mood = Column(String(50), nullable=False)
    file_size = Column(BigInteger, default=0)
    url = Column(String, nullable=True)                          # Cloudinary URL
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "caption": self.caption,
            "mood": self.mood,
            "file_size": self.file_size,
            "url": self.url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

def init_db():
    Base.metadata.create_all(bind=engine)
    print("✦ Database initialized")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
