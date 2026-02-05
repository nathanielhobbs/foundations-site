# models_practice.py
from datetime import datetime
from extensions import db

class PracticeProgress(db.Model):
    __tablename__ = "practice_progress"

    id = db.Column(db.Integer, primary_key=True)

    netid = db.Column(db.String(64), nullable=False, index=True)
    slug  = db.Column(db.String(128), nullable=False, index=True)

    section = db.Column(db.Integer, nullable=True, index=True)

    attempts        = db.Column(db.Integer, nullable=False, default=0)
    completed_at    = db.Column(db.DateTime, nullable=True, index=True)
    last_attempt_at = db.Column(db.DateTime, nullable=True, index=True)

    __table_args__ = (
        db.UniqueConstraint("netid", "slug", name="uq_practice_progress"),
    )


