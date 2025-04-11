# session_manager.py

from models import UserSession
from config import db
from datetime import datetime

# Variable interna para guardar la sesión actual
_current_session = None

def get_session():
    global _current_session
    return _current_session

def set_session(session):
    global _current_session
    _current_session = session

def load_or_create_session(phone_number):
    global _current_session
    _current_session = UserSession.query.filter_by(phone_number=phone_number).first()

    if not _current_session:
        _current_session = UserSession(phone_number=phone_number)
        db.session.add(_current_session)
        db.session.commit()
    
    return _current_session
