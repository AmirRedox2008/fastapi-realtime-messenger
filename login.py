#login.py
from database import Base,session_local
from pydantic import BaseModel ,Field
from fastapi import APIRouter, Depends, HTTPException,status
from typing import Annotated
from sqlalchemy.orm import Session
from jose import jwt,JWTError
from passlib.context import CryptContext
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from model import User
from datetime import datetime, timedelta


router = APIRouter()

SECRET_KEY = 'b405a4bcb878d609def61055eb49af7e4a4a9093138351d57173041a9c910428'
ALGORITHM = "HS256"


class CreateUserRequest(BaseModel):
    number : str = Field(min_length=10,max_length=13)
    email : str = Field(min_length=3,max_length=30)
    password : str

class Token(BaseModel):
    access_token: str
    token_type: str


def get_db():
    db = session_local()
    try:
        yield db
    finally:
        db.close()

bcrypt_context = CryptContext(schemes=['bcrypt'],deprecated = 'auto')
db_dependency = Annotated[Session,Depends(get_db)]
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

router = APIRouter()


@router.post("/register",status_code=status.HTTP_201_CREATED)
async def register(Createrequest:CreateUserRequest, db:db_dependency):
    existing_user = db.query(User).filter(User.email == Createrequest.email).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT)
    create_user_model = User(
        number = Createrequest.number,
        email = Createrequest.email,
        hashed_password = bcrypt_context.hash(Createrequest.password)
    )
    try:
        db.add(create_user_model)
        db.commit()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{e}")

@router.post("/login",status_code=status.HTTP_200_OK)
async def login(db:db_dependency,form_data : OAuth2PasswordRequestForm = Depends()):
    user = db.query(User).filter(User.number == form_data.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,)
    if not bcrypt_context.verify(form_data.password,user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Incorrect Password")
    token = create_access_token(user.number, user.id, timedelta(minutes=30))
    return {'access_token': token, "token_type": "bearer"}


def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        number: str = payload.get('sub')
        user_id: int = payload.get('id')
        if number is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Could not vaild user")
        return {'number': number, 'id': user_id}
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,detail="Could not vaild user")
    
@router.get('/me', status_code=status.HTTP_200_OK)
async def get_me(db: db_dependency,current_user: dict = Depends(get_current_user)):
    
    user_model = db.query(User).filter(User.id == current_user['id']).first()
    
    if not user_model:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        'message': 'welcome', 
        'id': user_model.id,
        'number': user_model.number,
        'name':user_model.name,
        'username': user_model.username  }

# @router.get("/users")
# async def get_all_users(db: db_dependency,current_user: dict = Depends(get_current_user)):
#     users = db.query(User).filter(User.id != current_user['id']).all()

#     return [{"id": user.id, "number": user.number} for user in users]


# For Frontend Side :


def create_access_token(number: str,user_id : int, expire_delta:timedelta):
    encode = {'sub': number, 'id':user_id}
    expires = datetime.utcnow() + expire_delta
    encode.update({'exp': expires})
    return jwt.encode(encode,SECRET_KEY,algorithm=ALGORITHM)

# async def authenticate_user(username:str,password:str,db:db_dependency):
#     user = db.query(User).filter(User.number == check).first()
#     if not user:
#         return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,)
#     if not bcrypt_context.verify(password,user.hashed_password):
#         return False
#     return True




