import uvicorn
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship

# --- Новое имя базы данных ---
DATABASE_URL = "sqlite:///./restaurants.db"
# ------------------------------

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Restaurant(Base):
    __tablename__ = "restaurants"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True)
    reviews = relationship("Review", back_populates="restaurant")


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup_populate():
    db = SessionLocal()
    # Проверяем наличие Пельменной
    if not db.query(Restaurant).filter_by(name="Пельменная №1").first():
        db.add(Restaurant(name="Пельменная №1"))
        db.commit()
    db.close()


@app.get("/")
def read_root():
    # Авто-редирект на первую страницу
    return RedirectResponse(url="/restaurant/1")


@app.get("/restaurant/{rest_id}")
def restaurant_page(rest_id: int, request: Request, db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == rest_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Заведение не найдено")

    reviews = db.query(Review).filter(Review.restaurant_id == rest_id).order_by(Review.id.desc()).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"restaurant": restaurant, "reviews": reviews}
    )


@app.post("/add_review/{rest_id}")
def add_review(
        rest_id: int,
        user_name: str = Form(...),
        text: str = Form(...),
        rating: int = Form(...),
        db: Session = Depends(get_db)
):
    new_review = Review(restaurant_id=rest_id, user_name=user_name, text=text, rating=rating)
    db.add(new_review)
    db.commit()
    return RedirectResponse(url=f"/restaurant/{rest_id}", status_code=303)

# Страница для добавления новых ресторанов
@app.get("/admin/add_restaurant")
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# ... (начало кода с моделями и настройками БД остается прежним) ...

# --- Админ-панель: Список всех заведений и ИХ отзывов ---
@app.get("/admin")
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # Загружаем рестораны вместе с их отзывами
    restaurants = db.query(Restaurant).all()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"restaurants": restaurants}
    )

# --- Добавление заведения ---
@app.post("/admin/add_restaurant")
def admin_add_rest(name: str = Form(...), db: Session = Depends(get_db)):
    if name:
        db.add(Restaurant(name=name))
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# --- Удаление отзыва ---
@app.post("/admin/delete_review/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if review:
        db.delete(review)
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# ... (остальные эндпоинты /restaurant/{id} остаются без изменений) ...

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)