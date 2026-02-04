from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import DATABASE_URL

# ── Engine ───────────────────────────────────────────────────
# check_same_thread=False is required for SQLite + FastAPI
# because requests may be handled on different threads
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# ── Session factory ──────────────────────────────────────────
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ── Base class ───────────────────────────────────────────────
# All models inherit from this
Base = declarative_base()


# ── Helper: get a DB session (use with `with` or dependency injection) ─
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Create all tables on startup ─────────────────────────────
def init_db():
    Base.metadata.create_all(bind=engine)