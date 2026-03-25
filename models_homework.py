# models_homework.py
from datetime import datetime
from extensions import db

class HomeworkSubmission(db.Model):
    __tablename__ = "homework_submissions"

    id = db.Column(db.Integer, primary_key=True)

    slug = db.Column(db.String(64), nullable=False, index=True)   # "hw1", "hw2"
    netid = db.Column(db.String(64), nullable=False, index=True)
    section = db.Column(db.Integer, nullable=True, index=True)
    code = db.Column(db.Text, nullable=False)                     # student.py contents
    result_json = db.Column(db.Text, nullable=False)              # json string of grader result

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    is_final = db.Column(db.Integer, nullable=False, default=0)

    due_at = db.Column(db.Text)         # ISO string
    submitted_at = db.Column(db.Text)   # ISO string

    late_seconds = db.Column(db.Integer, nullable=False, default=0)
    late_days = db.Column(db.Integer, nullable=False, default=0)

    score_raw = db.Column(db.Float)
    penalty_frac = db.Column(db.Float, nullable=False, default=0.0)
    score_final = db.Column(db.Float)

    # reopen mechanism
    reopened_from_id = db.Column(db.Integer, nullable=True)
    reopened_at = db.Column(db.Text, nullable=True)
    reopen_penalty_frac = db.Column(db.Float, nullable=False, default=0.0)
    score_final_after_reopen = db.Column(db.Float, nullable=True)
    diff_base_code = db.Column(db.Text, nullable=True)
