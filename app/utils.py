from fastapi.security import HTTPBearer
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import *
from app.models import User, Question
from datetime import datetime, timedelta
import os
import re
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 250

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(question: dict, expires_delta: timedelta = None):
    to_encode = question.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(HTTPBearer()), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")



def find_red_class(soup):
    style_tags = soup.find_all("style")
    for style_tag in style_tags:
        styles = style_tag.string
        if styles:
            matches = re.findall(r'\.(\w+)\s*{[^}]*color:\s*#ff0000\s*;?', styles, re.IGNORECASE)
            if matches:
                return matches[0]
    return None

