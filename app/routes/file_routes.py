from fastapi import  APIRouter, UploadFile, HTTPException, Form, Depends, File
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from app.s3 import upload_to_s3
from app.utils import get_current_user, find_red_class
from app.models import Question, User
from app.database import get_db
import zipfile, shutil, os
import re
import logging
import json
from typing import List

# Loggerni sozlash
logging.basicConfig(
    level=logging.INFO,  # DEBUG darajasiga o'zgartirishingiz mumkin
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

router = APIRouter()
@router.post("/upload/")
async def upload_zips(
        files: List[UploadFile] = File(...),
        categories: List[str] = Form(...),
        subjects: List[str] = Form(...),
        db: Session = Depends(get_db)
):
    if len(files) != len(categories) or len(files) != len(subjects):
        raise HTTPException(
            status_code=400,
            detail="Fayllar, kategoriyalar va mavzular soni bir xil bo'lishi kerak"
        )

    questions = []

    for file, category, subject in zip(files, categories, subjects):
        content = await file.read()

        # Faylni vaqtinchalik saqlash
        zip_file_location = f"./uploaded_{file.filename}"
        with open(zip_file_location, "wb") as buffer:
            buffer.write(content)

        # ZIP Faylni ochish
        extract_dir = f"./extracted_{file.filename.split('.')[0]}"
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zip_file_location, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # HTML fayl va "images" papkasini topish
        html_file_path, images_dir = None, None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith(".html"):
                    html_file_path = os.path.join(root, file)
            for dir_name in dirs:
                if dir_name.lower() == "images":
                    images_dir = os.path.join(root, dir_name)

        if not html_file_path:
            raise HTTPException(status_code=400, detail=f"No HTML file found in the ZIP archive: {file.filename}.")

        # HTMLni o'qish va tahlil qilish
        with open(html_file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        paragraphs = soup.find_all("p", class_=lambda x: x and x.startswith("c"))
        red_class = find_red_class(soup)
        current_block = {"question": None, "variants": [], "correct_answer": None, "image": None}

        for paragraph in paragraphs:
            text = paragraph.get_text(strip=True)
            if not text:
                continue

            img_tag = paragraph.find("img")
            if img_tag:
                img_src = img_tag["src"]
                image_src = next(
                    (os.path.join(root, file) for root, dirs, files in os.walk(extract_dir) for file in files if file == os.path.basename(img_src)),
                    None
                )
                if not image_src:
                    raise HTTPException(status_code=400, detail=f"Image file not found: {img_src}")

                s3_url = upload_to_s3(image_src, f"images/{os.path.basename(image_src)}")
                current_block["image"] = s3_url

            if text[0].isdigit() and "." in text:
                if current_block["question"]:
                    options_text = "\n".join(current_block["variants"])
                    questions.append({
                        "text": current_block["question"],
                        "options": options_text,
                        "true_answer": current_block["correct_answer"],
                        "image": current_block["image"]
                    })
                current_block = {"question": text, "variants": [], "correct_answer": None, "image": None}
            print("Varant tekshirilmoqda")
            if text.startswith(("A)", "B)", "C)", "D)")):
                current_block["variants"].append(text)
                if red_class in paragraph.get("class", []):
                    current_block["correct_answer"] = text[0]
                
                else:
                    if current_block["variants"]:
                        current_block["variants"][-1] += f" {text}"

        # Yakuniy savolni qo'shish
        if current_block["question"]:
            options_text = "\n".join(current_block["variants"])
            questions.append({
                "text": current_block["question"],
                "options": options_text,
                "true_answer": current_block["correct_answer"],
                "image": current_block["image"]
            })

        # Tozalash
        shutil.rmtree(extract_dir, ignore_errors=True)
        os.remove(zip_file_location)

    # Savollarni bazaga saqlash
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

    return {"message": "Fayllar muvaffaqiyatli yuklandi"}
@router.get("/questions/")
def get_questions(db: Session = Depends(get_db)):
    # Ma'lumotlar bazasidagi barcha savollarni olish
    questions = db.query(Question).all()

    # Savollarni kategoriyalar bo'yicha guruhlash
    grouped_questions = {}
    for question in questions:
        if question.category not in grouped_questions:
            grouped_questions[question.category] = []
        grouped_questions[question.category].append({
            "category": question.category,
            "subject": question.subject,
            "text": question.text,
            "options": question.options,
            "true_answer": question.true_answer,
            "image": question.image
        })

    # Guruhlangan savollarni JSON formatida qaytarish
    return {"data": grouped_questions}


@router.delete("/delete-all-questions/", response_model=dict)
def delete_all_questions(db: Session = Depends(get_db)):
    try:
        db.query(Question).delete()
        db.commit()
        return {"message": "All questions have been deleted successfully"}
    except Exception as e:
        db.rollback()  # Xatolik yuzaga kelsa, tranzaktsiyani bekor qilish
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")


