from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User


class RedirectToLogin(Exception):
    pass


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid = request.session.get("user_id")
    if not uid:
        raise RedirectToLogin()
    user = db.get(User, uid)
    if not user or user.status != "active":
        request.session.clear()
        raise RedirectToLogin()
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403)
        return user
    return checker
