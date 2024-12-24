from fastapi import FastAPI, UploadFile, HTTPException, Form, Depends
from bs4 import BeautifulSoup
from fastapi.security import HTTPBearer
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import shutil
import zipfile
import os
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import re

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    options = Column(Text, nullable=False)
    true_answer = Column(String, nullable=True)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    subject = Column(String, nullable=True)
    user_id = Column(Integer, nullable=False)

    
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

Base.metadata.create_all(bind=engine)

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
S3_REGION = os.getenv("S3_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# S3 mijozini sozlash
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=S3_REGION,
)

def upload_to_s3(file_path: str, key: str) -> str:
    try:
        s3_client.upload_file(file_path, S3_BUCKET_NAME, key)
        s3_url = f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{key}"
        return s3_url
    except NoCredentialsError:
        raise HTTPException(status_code=500, detail="AWS credentials topilmadi.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AWS yuklashda xatolik yuz berdi: {str(e)}")

# FastAPI app
app = FastAPI()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

# Token Generation
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

# Routes
@app.post("/register/", response_model=dict)
def register(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registered successfully"}

@app.post("/login/", response_model=Token)
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/upload/")
async def upload_zip(file: UploadFile, subject: str = Form(...), category: str = Form(...), current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a ZIP file.")

    # Save the uploaded ZIP file
    zip_file_location = f"./uploaded_{file.filename}"
    with open(zip_file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Extract the ZIP file
    extract_dir = "./extracted_files"
    with zipfile.ZipFile(zip_file_location, 'r') as zip_ref:
        zip_ref.extractall(extract_dir)

    # Log ZIP contents
    for root, dirs, files in os.walk(extract_dir):
        print(f"Root: {root}, Dirs: {dirs}, Files: {files}")

    # Find the HTML file and image directory in the extracted files
    html_file_path = None
    images_dir = None
    for root, dirs, files in os.walk(extract_dir):
        for file in files:
            if file.endswith(".html"):
                html_file_path = os.path.join(root, file)
        for dir_name in dirs:
            if dir_name.lower() == "images":
                images_dir = os.path.join(root, dir_name)

    if not html_file_path:
        raise HTTPException(status_code=400, detail="No HTML file found in the ZIP archive.")

    # Parse HTML file
    with open(html_file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    questions = []
    paragraphs = soup.find_all("p", class_="c3")
    current_block = {"question": None, "variants": [], "correct_answer": None, "image": None}

    for paragraph in paragraphs:
        text = paragraph.get_text(strip=True)
        if not text:
            continue

        img_tag = paragraph.find("img")
        if img_tag:
            img_src = img_tag["src"]
            
            image_src = None
            for root, dirs, files in os.walk(extract_dir):
                for files in files:
                    if file == os.path.basename(img_src):
                        image_src = os.path.join(root, file)
                        break
                    if image_src:
                        break
                
                if not image_src:
                    raise HTTPException(status_code=400, detail=f"Image file not found: {img_src}")
            
            image_key = f"images/{os.path.basename(image_src)}"
            s3_url = upload_to_s3(image_src, image_key)
            current_block["image"] = s3_url

        if text[0].isdigit() and "." in text:
            if current_block["question"]:
                options_text = " ".join(current_block["variants"])
                questions.append({
                    "text": current_block["question"],
                    "options": options_text,
                    "true_answer": current_block["correct_answer"],
                    "image": current_block["image"]
                })
            current_block = {"question": text, "variants": [], "correct_answer": None, "image": None}
        elif text.startswith(("A)", "B)", "C)", "D)")):
            current_block["variants"].append(text)
            span_tags = paragraph.find_all("span")
            for span in span_tags:
                if "c2" in span.get("class", []):
                    current_block["correct_answer"] = span.get_text(strip=True)[0]
        else:
            if current_block["variants"]:
                current_block["variants"][-1] += f" {text}"

    if current_block["question"]:
        options_text = " ".join(current_block["variants"])
        questions.append({
            "text": current_block["question"],
            "options": options_text,
            "true_answer": current_block["correct_answer"],
            "image": current_block["image"]
        })

    db = SessionLocal()
    try:
        for q in questions:
            question = Question(
                text=q["text"],
                options=q["options"],
                true_answer=q["true_answer"],
                image=q["image"],
                category=category,
                subject=subject,
                user_id=current_user.id
            )
            db.add(question)
        db.commit()
    finally:
        db.close()

    os.remove(zip_file_location)
    shutil.rmtree(extract_dir)

    return {"questions": questions}


@app.get("/questions/")
def get_questions(db: Session = Depends(get_db)):
    questions = db.query(Question).all()
    
    grouped_questions = {}
    for question in questions:
        if question.category not in grouped_questions:
            grouped_questions[question.category] = []
        grouped_questions[question.category].append({
            "id": question.id,
            "category": question.category,
            "subject": question.subject,
            "text": question.text,
            "options": question.options,
            "true_answer": question.true_answer,
            "image": question.image
        })
    
    return grouped_questions


@app.delete("/delete-all-questions/", response_model=dict)
def delete_all_questions(db: Session = Depends(get_db)):
    try:
        # Barcha ma'lumotlarni o'chirish
        db.query(Question).delete()
        db.commit()
        return {"message": "All questions have been deleted successfully"}
    except Exception as e:
        db.rollback()  # Xatolik yuzaga kelsa, tranzaktsiyani bekor qilish
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")