from fastapi import  APIRouter, UploadFile, HTTPException, Form, Depends
from sqlalchemy.orm import Session
from bs4 import BeautifulSoup
from app.s3 import upload_to_s3
from app.utils import get_current_user, find_red_class
from app.models import Question, User
from app.database import get_db
import zipfile, shutil, os
import re

router = APIRouter()

@router.post("/upload/")
async def upload_zips(
    files: List[UploadFile],
    categories: List[str] = Form(...),
    subjects: List[str] = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if len(files) != len(categories) or len(files) != len(subjects):
        raise HTTPException(status_code=400, detail="The number of files, categories, and subjects must match.")

    questions = []
    for idx, file in enumerate(files):
        category = categories[idx]
        subject = subjects[idx]
        
        # Faylni tekshirish
        if not file.filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail=f"Invalid file type: {file.filename}. Please upload ZIP files.")

        # Save the uploaded ZIP file
        zip_file_location = f"./uploaded_{file.filename}"
        with open(zip_file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Extract the ZIP file
        extract_dir = f"./extracted_{file.filename.split('.')[0]}"
        with zipfile.ZipFile(zip_file_location, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

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
            raise HTTPException(status_code=400, detail=f"No HTML file found in the ZIP archive: {file.filename}.")

        # Parse HTML file
        with open(html_file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        paragraphs = soup.find_all("p", class_=lambda x: x and x.startswith("c"))
        current_block = {"question": None, "variants": [], "correct_answer": None, "image": None}
        red_class = find_red_class(soup)
        print(f"Red Class: {red_class}")
        for paragraph in paragraphs:
            text = paragraph.get_text(strip=True)
            if not text:
                continue

            img_tag = paragraph.find("img")
            if img_tag:
                img_src = img_tag["src"]

                image_src = None
                for root, dirs, files in os.walk(extract_dir):
                    for file in files:
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
                    options_text = "\n".join(current_block["variants"])
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
                    # Dinamik classni ishlatish
                    if red_class in span.get("class", []):
                        current_block["correct_answer"] = span.get_text(strip=True)[0]
            else:
                if current_block["variants"]:
                    current_block["variants"][-1] += f" {text}"

        if current_block["question"]:
            options_text = "\n".join(current_block["variants"])
            questions.append({
                "text": current_block["question"],
                "options": options_text,
                "true_answer": current_block["correct_answer"],
                "image": current_block["image"]
            })

        # Clean up extracted files
        shutil.rmtree(extract_dir)
        os.remove(zip_file_location)

    # Save questions to the questionbase
    try:
        for q in questions:
            question = Question(
                category=category,
                subject=subject,
                text=q["text"],
                options=q["options"],
                true_answer=q["true_answer"],
                image=q["image"]
            )
            db.add(question)
        db.commit()
    finally:
        db.close()

    return {"message": "Files uploaded successfully"}


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


