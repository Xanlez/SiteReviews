import uvicorn
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext

# --- Настройки БД и Безопасности ---
DATABASE_URL = "sqlite:///./restaurants.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# --- Модели ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)


class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    reviews = relationship("Review", back_populates="restaurant", cascade="all, delete-orphan")


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String)
    text = Column(String)
    rating = Column(Integer)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    restaurant = relationship("Restaurant", back_populates="reviews")


Base.metadata.create_all(bind=engine)

app = FastAPI()
templates = Jinja2Templates(directory="templates")


# --- Инструменты ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_password_hash(password):
    return pwd_context.hash(password)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_current_user(credentials: HTTPBasicCredentials = Depends(security), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


@app.on_event("startup")
def startup_populate():
    db = SessionLocal()
    if not db.query(Restaurant).first():
        db.add(Restaurant(name="Пельменная №1"))
    if not db.query(User).filter_by(username="admin").first():
        db.add(User(username="admin", hashed_password=get_password_hash("admin123")))
    db.commit()
    db.close()


# --- Маршруты Клиента ---
@app.get("/")
def home():
    return RedirectResponse(url="/restaurant/1")


@app.get("/restaurant/{rest_id}")
def restaurant_page(rest_id: int, request: Request, db: Session = Depends(get_db)):
    rest = db.query(Restaurant).filter(Restaurant.id == rest_id).first()
    if not rest: raise HTTPException(status_code=404)
    revs = db.query(Review).filter(Review.restaurant_id == rest_id).order_by(Review.id.desc()).all()

    # ИСПРАВЛЕНО: Явные имена аргументов
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"restaurant": rest, "reviews": revs}
    )


@app.post("/add_review/{rest_id}")
def add_review(rest_id: int, user_name: str = Form(...), text: str = Form(...), rating: int = Form(...),
               db: Session = Depends(get_db)):
    db.add(Review(restaurant_id=rest_id, user_name=user_name, text=text, rating=rating))
    db.commit()
    return RedirectResponse(url=f"/restaurant/{rest_id}", status_code=303)


# --- Маршруты Админа ---
@app.get("/admin")
def admin_panel(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rests = db.query(Restaurant).all()

    # ИСПРАВЛЕНО: Явные имена аргументов
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"restaurants": rests}
    )


@app.post("/admin/add_restaurant")
def add_rest(name: str = Form(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.add(Restaurant(name=name))
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/add_staff")
def add_staff(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    if not db.query(User).filter_by(username=username).first():
        db.add(User(username=username, hashed_password=get_password_hash(password)))
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete_review/{rev_id}")
def del_rev(rev_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rev = db.query(Review).filter(Review.id == rev_id).first()
    if rev:
        db.delete(rev)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)