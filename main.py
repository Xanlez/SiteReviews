from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# БД и Настройки
DATABASE_URL = "sqlite:///./fastfood.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# Модели
class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    reviews = relationship("Review", back_populates="restaurant")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    text = Column(String)
    rating = Column(Integer)
    restaurant_id = Column(Integer, ForeignKey("restaurants.id"))
    restaurant = relationship("Restaurant", back_populates="reviews")

Base.metadata.create_all(bind=engine)
app = FastAPI()
templates = Jinja2Templates(directory="templates")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# Инициализация списка заведений (если пусто)
@app.on_event("startup")
def startup_populate(db: Session = next(get_db())):
    if not db.query(Restaurant).first():
        for name in ["Бургер Кинг", "Вкусно и точка", "KFC", "Додо Пицца"]:
            db.add(Restaurant(name=name))
        db.commit()

@app.get("/")
def index(request: Request, db: Session = Depends(get_db)):
    restaurants = db.query(Restaurant).all()
    reviews = db.query(Review).order_by(Review.id.desc()).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "restaurants": restaurants,
        "reviews": reviews
    })

@app.post("/add_review")
def add_review(
    restaurant_id: int = Form(...),
    text: str = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db)
):
    new_review = Review(restaurant_id=restaurant_id, text=text, rating=rating)
    db.add(new_review)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)