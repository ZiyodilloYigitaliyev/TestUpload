# 3. routers/upload.py - Fayl yuklash
from fastapi import APIRouter, UploadFile, Form, Depends, HTTPException
from app.dependencies import upload_to_s3, get_db, verify_token
from sqlalchemy.orm import Session
from app.models import Question, User
from app.database import SessionLocal
from bs4 import BeautifulSoup
import shutil, zipfile, os


router = APIRouter(prefix="/upload", tags=["Upload"])


@router.post("/zip/")
async def upload_zip(file: UploadFile, subject: str = Form(...), category: str = Form(...), token: dict = Depends(verify_token), db: Session = Depends(get_db)):
    # Token orqali foydalanuvchining ma'lumotlarini olish
    username = token.get("sub")  # "sub" token ichidagi foydalanuvchi nomi (yoki boshqa parametr)
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
                if "c2" in span.get("class", []):
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

    try:
        os.remove(zip_file_location)
        shutil.rmtree(extract_dir)
    except Exception as e:
        print(f"Failed to clean up files: {e}")

    return {"questions": questions}

