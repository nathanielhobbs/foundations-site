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

