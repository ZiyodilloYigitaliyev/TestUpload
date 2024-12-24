
# 8. dependencies.py - Umumiy yordamchi funksiyalar
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session, sessionmaker
from app.database import SessionLocal
from app.models import User
import os
import datetime
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv

load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_access_token(data: dict, expires_delta):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

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

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION_NAME = os.getenv("S3_REGION")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# S3 mijozini sozlash
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION_NAME,
)

def upload_to_s3(file_path: str, key: str) -> str:
    try:
        s3_client.upload_file(file_path, BUCKET_NAME, key)
        s3_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION_NAME}.amazonaws.com/{key}"
        return s3_url
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials topilmadi.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AWS yuklashda xatolik yuz berdi: {str(e)}")
