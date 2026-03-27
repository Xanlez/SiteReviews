import uvicorn
from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext

# --- Настройки ДВУХ баз данных ---
RESTAURANT_DB = "sqlite:///./restaurants.db"
USER_DB = "sqlite:///./users.db"

r_engine = create_engine(RESTAURANT_DB, connect_args={"check_same_thread": False})
u_engine = create_engine(USER_DB, connect_args={"check_same_thread": False})

SessionRest = sessionmaker(bind=r_engine)
SessionUser = sessionmaker(bind=u_engine)

Base = declarative_base()

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
    slug = Column(String, unique=True, index=True)
    reviews = relationship("Review", back_populates="restaurant", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    user_name = Column(String)
    text = Column(String)
    rating = Column(Integer)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    restaurant = relationship("Restaurant", back_populates="reviews")

Base.metadata.create_all(bind=r_engine, tables=[Restaurant.__table__, Review.__table__])
Base.metadata.create_all(bind=u_engine, tables=[User.__table__])

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Сессии БД ---
def get_r_db():
    db = SessionRest()
    try:
        yield db
    finally:
        db.close()

def get_u_db():
    db = SessionUser()
    try:
        yield db
    finally:
        db.close()

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_current_user(credentials: HTTPBasicCredentials = Depends(security), db: Session = Depends(get_u_db)):
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    return user

@app.on_event("startup")
def startup():
    r_db, u_db = SessionRest(), SessionUser()
    if not r_db.query(Restaurant).first():
        r_db.add(Restaurant(name="Пельменная №1", slug="pelmennaya"))
    if not u_db.query(User).filter_by(username="admin").first():
        u_db.add(User(username="admin", hashed_password=get_password_hash("admin123")))
    r_db.commit(); u_db.commit(); r_db.close(); u_db.close()

# --- Клиентские маршруты ---
@app.get("/")
def home():
    return RedirectResponse(url="/restaurant/pelmennaya")

@app.get("/restaurant/{slug}")
def restaurant_page(slug: str, request: Request, db: Session = Depends(get_r_db)):
    rest = db.query(Restaurant).filter(Restaurant.slug == slug).first()
    if not rest:
        raise HTTPException(status_code=404)
    revs = db.query(Review).filter(Review.restaurant_id == rest.id).order_by(Review.id.desc()).all()
    return templates.TemplateResponse(request=request, name="index.html", context={"restaurant": rest, "reviews": revs})

@app.post("/add_review/{slug}")
def add_review(slug: str, user_name: str = Form(...), text: str = Form(...), rating: int = Form(...), db: Session = Depends(get_r_db)):
    rest = db.query(Restaurant).filter(Restaurant.slug == slug).first()
    if not rest:
        raise HTTPException(status_code=404)
    db.add(Review(restaurant_id=rest.id, user_name=user_name, text=text, rating=rating))
    db.commit()
    return RedirectResponse(url=f"/restaurant/{slug}", status_code=303)

# --- Админские маршруты ---
@app.get("/admin")
def admin_panel(request: Request, r_db: Session = Depends(get_r_db), u_db: Session = Depends(get_u_db), user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="admin.html", context={
        "restaurants": r_db.query(Restaurant).all(),
        "staff": u_db.query(User).all(),
        "current_admin": user.username
    })

@app.post("/admin/add_restaurant")
def add_rest(name: str = Form(...), slug: str = Form(...), db: Session = Depends(get_r_db), u: User = Depends(get_current_user)):
    db.add(Restaurant(name=name, slug=slug.lower().replace(" ", "")))
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete_restaurant/{rest_id}")
def delete_rest(rest_id: int, db: Session = Depends(get_r_db), u: User = Depends(get_current_user)):
    rest = db.query(Restaurant).filter(Restaurant.id == rest_id).first()
    if rest:
        db.delete(rest)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/add_staff")
def add_staff(username: str = Form(...), password: str = Form(...), db: Session = Depends(get_u_db), u: User = Depends(get_current_user)):
    if not db.query(User).filter_by(username=username).first():
        db.add(User(username=username, hashed_password=get_password_hash(password)))
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete_staff/{user_id}")
def delete_staff(user_id: int, db: Session = Depends(get_u_db), u: User = Depends(get_current_user)):
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.username != u.username:
        db.delete(target)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/change_password")
def change_password(user_id: int = Form(...), new_password: str = Form(...), db: Session = Depends(get_u_db), u: User = Depends(get_current_user)):
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        target.hashed_password = get_password_hash(new_password)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/delete_review/{rev_id}")
def del_rev(rev_id: int, db: Session = Depends(get_r_db), u: User = Depends(get_current_user)):
    rev = db.query(Review).filter(Review.id == rev_id).first()
    if rev:
        db.delete(rev)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)