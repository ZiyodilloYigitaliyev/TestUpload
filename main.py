from fastapi import FastAPI, UploadFile, HTTPException, Form, Depends
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import shutil
import zipfile
import os
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL").replace("postgres://", "postgresql://")
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
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
    subject =  Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

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

# FastAPI app
app = FastAPI()

@app.post("/upload/")
async def upload_zip(file: UploadFile, subject: str = Form(...), category: str = Form(...)):
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
                subject=subject
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
    
    # Savollarni kategoriyalariga qarab guruhlash
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

