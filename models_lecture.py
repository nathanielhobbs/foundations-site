# models_lecture.py
from datetime import datetime
from extensions import db

class LectureChallenge(db.Model):
    __tablename__ = 'lecture_challenges'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, index=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    prompt_md = db.Column(db.Text, nullable=False)
    is_open = db.Column(db.Boolean, default=True, nullable=False)
    show_leaderboard = db.Column(db.Boolean, default=True, nullable=False)
    open_at = db.Column(db.DateTime, nullable=True)
    close_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class LectureSubmission(db.Model):
    __tablename__ = 'lecture_submissions'
    id = db.Column(db.Integer, primary_key=True)
    challenge_id = db.Column(db.Integer, db.ForeignKey('lecture_challenges.id'), nullable=False, index=True)
    netid = db.Column(db.String(64), index=True, nullable=False)
    display_name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.Text, nullable=False)
    keystrokes_json = db.Column(db.Text, nullable=True)
    run_output = db.Column(db.Text, nullable=True)
    runtime_ms = db.Column(db.Integer, nullable=True)
    language = db.Column(db.String(32), default='python', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    approved = db.Column(db.Boolean, default=False, nullable=False)
    points = db.Column(db.Integer, default=0, nullable=False)
    public_replay = db.Column(db.Boolean, default=False, nullable=False)


    status = db.Column(db.String(16), nullable=False, default='pending')  # 'pending'|'approved'|'rejected'
    feedback = db.Column(db.Text, nullable=True)


    challenge = db.relationship('LectureChallenge', backref=db.backref('submissions', lazy='dynamic'))

