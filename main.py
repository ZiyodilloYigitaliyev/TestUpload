from fastapi import FastAPI, UploadFile, HTTPException
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import shutil
import zipfile
import os

# Database setup
DATABASE_URL = "sqlite:///./questions.db"
Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=False)
    options = Column(Text, nullable=False)
    true_answer = Column(String, nullable=True)
    image = Column(String, nullable=True)

Base.metadata.create_all(bind=engine)

# FastAPI app
app = FastAPI()

@app.post("/upload/")
async def upload_zip(file: UploadFile):
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

        # Check if the paragraph contains an image
        img_tag = paragraph.find("img")
        if img_tag and images_dir:
            image_src = os.path.join(images_dir, img_tag["src"])
            current_block["image"] = image_src

        # Check if the text starts with a question number (e.g., "1.", "2.")
        if text[0].isdigit() and "." in text:
            # If a new question starts, save the current block
            if current_block["question"]:
                options_text = " ".join(current_block["variants"])
                questions.append({
                    "text": current_block["question"],
                    "options": options_text,
                    "true_answer": current_block["correct_answer"],
                    "image": current_block["image"]
                })
            
            # Start a new question block
            current_block = {"question": text, "variants": [], "correct_answer": None, "image": None}
        elif text.startswith(("A)", "B)", "C)", "D)")):
            # Add variants to the current block
            current_block["variants"].append(text)

            # Check for red color indicating the correct answer
            span_tags = paragraph.find_all("span")
            for span in span_tags:
                if "c2" in span.get("class", []):
                    current_block["correct_answer"] = span.get_text(strip=True)[0]  # Extract "A", "B", "C", or "D"
        else:
            # Append misidentified variants to the last variant if needed
            if current_block["variants"]:
                current_block["variants"][-1] += f" {text}"

    # Append the last question block
    if current_block["question"]:
        options_text = " ".join(current_block["variants"])
        questions.append({
            "text": current_block["question"],
            "options": options_text,
            "true_answer": current_block["correct_answer"],
            "image": current_block["image"]
        })

    # Save to database
    db = SessionLocal()
    try:
        for q in questions:
            question = Question(
                text=q["text"],
                options=q["options"],
                true_answer=q["true_answer"],
                image=q["image"]
            )
            db.add(question)
        db.commit()
    finally:
        db.close()

    # Clean up temporary files
    os.remove(zip_file_location)
    shutil.rmtree(extract_dir)

    return {"questions": questions}
