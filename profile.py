from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from login import get_current_user, db_dependency
from model import User

router = APIRouter()


class UsernameRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    name: str = Field(min_length=3, max_length=30)

@router.post("/set_username", status_code=status.HTTP_200_OK)
async def set_username(req: UsernameRequest, db: db_dependency, current_user: dict = Depends(get_current_user)):
    
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This username is already taken")

    user = db.query(User).filter(User.id == current_user['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.username = req.username
    user.name = req.name
    db.commit()
    db.refresh(user)
    return {"message": "Username and name set successfully", "username": user.username, "name": user.name}


@router.put("/profile/update", status_code=status.HTTP_200_OK)
async def update_profile(db: db_dependency, req: UsernameRequest, current_user: dict = Depends(get_current_user)):

    user = db.query(User).filter(User.id == current_user['id']).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    existing = db.query(User).filter(User.username == req.username).first()

    if existing and existing.id != current_user['id']:
        raise HTTPException(status_code=400, detail="This username is already taken")
    user.username = req.username
    user.name = req.name
    db.commit()
    db.refresh(user)

    return {
        "message": "Profile updated successfully",
        "username": user.username,
        "name": user.name
    }

@router.get("/users/find_by_phone",status_code=status.HTTP_200_OK)
async def find_by_phone(phone: str, db:db_dependency,current_user : dict = Depends(get_current_user)):
    user = db.query(User).filter(User.member == phone).first()
    if not user or not user.username: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,detail="User not found..... ")
    return {"id" : user.id, "name":user.name or user.username, "username":user.username}





@router.get("/users/search", status_code=status.HTTP_200_OK)
async def search_users(q: str, db: db_dependency, current_user: dict = Depends(get_current_user)):

    if not q.strip():
        return []

    users = (
        db.query(User)
        .filter(User.username.ilike(f"%{q}%"), User.id != current_user['id'])
        .limit(20)
        .all()
    )
    return [
        {"id": u.id, "username": u.username, "number": u.number, "name":u.name}
        for u in users if u.username
    ]
@router.get("/users/{user_id}", status_code=status.HTTP_200_OK)
async def get_user_profile(user_id: int, db: db_dependency, current_user: dict = Depends(get_current_user)):
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    return {"id": user.id, "username": user.username, "number": user.number, "name":user.name}