# lecture_utils.py
from datetime import datetime
from zoneinfo import ZoneInfo
from models_lecture import LectureChallenge  # your model

TZ = ZoneInfo("America/New_York")

def _aware_local(dt):
    if dt is None: return None
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)

def is_open_now(ch) -> bool:
    now = datetime.now(TZ)
    if not ch.is_open: return False
    oa = _aware_local(ch.open_at)
    ca = _aware_local(ch.close_at)
    if oa and now < oa: return False
    if ca and now > ca: return False
    return True

def student_can_access(ch, student_section) -> bool:
    if not is_open_now(ch): return False
    scope = (ch.section_scope or "").strip().upper()
    if not scope or scope in {"ALL", "*"}: return True
    allowed = {int(s) for s in scope.split(",") if s.strip().isdigit()}
    try:
        return int(student_section) in allowed
    except (TypeError, ValueError):
        return False

def current_active_lecture_for(section):
    qs = (LectureChallenge.query
          .filter_by(is_open=True)
          .order_by(LectureChallenge.open_at.desc().nullslast()))
    for ch in qs:
        if student_can_access(ch, section):
            return ch
    return None

