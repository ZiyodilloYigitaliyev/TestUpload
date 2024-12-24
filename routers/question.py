# 4. routers/question.py - Savollar bilan ishlash
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.models import Question, User
from app.dependencies import get_db, get_current_user

router = APIRouter(prefix="/questions", tags=["Questions"])

@router.get("/questions")
def get_questions(db: Session = Depends(get_db)):
    questions = db.query(Question).all()
    
    grouped_questions = {}
    for question in questions:
        user = db.query(User).filter(User.id == question.user_id).first()
        username = user.username if user else "Unknown"

        if username not in grouped_questions:
            grouped_questions[username] = []
        grouped_questions[username].append({
            "id": question.id,
            "category": question.category,
            "subject": question.subject,
            "text": question.text,
            "options": question.options,
            "true_answer": question.true_answer,
            "image": question.image
        })
    
    return grouped_questions

@router.delete("/delete-my-questions/", response_model=dict)
def delete_user_questions(db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    try:
        deleted_count = db.query(Question).filter(Question.username == current_user).delete()
        db.commit()
        return {"message": f"{deleted_count} questions deleted successfully", "username": current_user}
    except Exception as e:
        db.rollback()  # Xatolik yuzaga kelsa tranzaktsiyani bekor qilish
        raise HTTPException(status_code=500, detail=f"Error occurred: {str(e)}")
