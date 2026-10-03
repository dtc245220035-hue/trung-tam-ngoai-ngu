import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from .ai import router as ai_router                              # ← THÊM
from .attendance import router as attendance_router
from .classes import router as classes_router
from .courses import router as courses_router
from .database import Base, SessionLocal, engine, get_db
from .deps import RedirectToLogin, current_user
from .enrollments import router as enrollments_router
from .invoices import router as invoices_router
from .lookup import router as lookup_router
from .models import ClassRoom, Course, Enrollment, Invoice, Student, Teacher, User
from .results import student_router as my_results_router
from .results import teacher_router as results_router
from .security import verify_password
from .seed import seed
from .self_service import router as self_service_router
from .stats import router as stats_router
from .students import router as students_router
from .teachers import router as teachers_router
from .web import BASE_DIR, flash, render

MAX_FAILED = 5
LOCK_MINUTES = 15


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="Hệ thống quản lý trung tâm ngoại ngữ có tích hợp AI", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-only-secret"),
                   max_age=60 * 60 * 8)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(students_router)
app.include_router(courses_router)
app.include_router(classes_router)
app.include_router(teachers_router)
app.include_router(enrollments_router)
app.include_router(invoices_router)
app.include_router(attendance_router)
app.include_router(results_router)
app.include_router(my_results_router)
app.include_router(self_service_router)
app.include_router(lookup_router)
app.include_router(stats_router)
app.include_router(ai_router)                                    # ← THÊM


@app.exception_handler(RedirectToLogin)
async def _to_login(_request: Request, _exc: RedirectToLogin):
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 403:
        return render(request, "403.html", status_code=403)
    if exc.status_code == 404:
        return render(request, "404.html", status_code=404)
    from fastapi.responses import JSONResponse
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.get("/")
def home():
    return RedirectResponse("/dashboard", status_code=303)


@app.get("/login")
def login_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html")


@app.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""),
          db: Session = Depends(get_db)):
    username = username.strip()

    def fail(msg: str):
        return render(request, "login.html", error=msg, username=username, status_code=400)

    if not username or not password:
        return fail("Vui lòng nhập đầy đủ thông tin")

    generic = "Tên đăng nhập hoặc mật khẩu không đúng"
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return fail(generic)
    if user.status == "locked":
        return fail("Tài khoản đã bị khóa, vui lòng liên hệ Admin")
    if user.status == "inactive":
        return fail("Tài khoản đang ngừng hoạt động, vui lòng liên hệ Admin")

    now = datetime.now()
    if user.locked_until and user.locked_until > now:
        mins = int((user.locked_until - now).total_seconds() // 60) + 1
        return fail(f"Tài khoản tạm khóa do nhập sai quá {MAX_FAILED} lần, thử lại sau {mins} phút")

    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_FAILED:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_attempts = 0
        db.commit()
        return fail(generic)

    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    request.session.clear()
    request.session["user_id"] = user.user_id
    request.session["role"] = user.role
    flash(request, "Đăng nhập thành công")
    return RedirectResponse("/dashboard", status_code=303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    flash(request, "Đã đăng xuất thành công")
    return RedirectResponse("/login", status_code=303)


def dashboard_data(db: Session, user: User) -> dict:
    data: dict = {}
    if user.role in ("admin", "consultant"):
        data["open_classes"] = (db.query(ClassRoom).filter(ClassRoom.status == "open")
                                .order_by(ClassRoom.class_code).all())
        data["n_students"] = db.query(Student).filter(Student.is_deleted.is_(False)).count()
        data["n_owing"] = db.query(Invoice).filter(Invoice.status != "paid").count()
    if user.role == "admin":
        data["n_teachers"] = db.query(Teacher).filter(Teacher.status == "active").count()
        data["n_courses"] = db.query(Course).count()
        data["n_open"] = len(data["open_classes"])
        data["revenue"] = db.query(func.coalesce(func.sum(Invoice.paid_amount), 0)).scalar()
        data["debt"] = db.query(
            func.coalesce(func.sum(Invoice.total_amount - Invoice.paid_amount), 0)).scalar()
    if user.role == "consultant":
        data["n_open"] = len(data["open_classes"])
        data["seats"] = sum(c.seats_left for c in data["open_classes"])
    if user.role == "teacher":
        t = db.query(Teacher).filter(Teacher.user_id == user.user_id).first()
        data["my_classes"] = (db.query(ClassRoom).filter(ClassRoom.teacher_id == t.teacher_id)
                              .order_by(ClassRoom.class_code).all()) if t else []
        data["n_my_students"] = sum(c.current_students for c in data["my_classes"])
    if user.role == "student":
        s = db.query(Student).filter(Student.user_id == user.user_id).first()
        enrolls = (db.query(Enrollment).filter(Enrollment.student_id == s.student_id,
                                               Enrollment.status == "active").all()) if s else []
        data["my_classes"] = [e.classroom for e in enrolls]
        data["owing"] = (db.query(Invoice).filter(Invoice.student_id == s.student_id,
                                                  Invoice.status != "paid").all()) if s else []
        data["student"] = s
    return data


@app.get("/dashboard")
def dashboard(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "dashboard.html", user=user, **dashboard_data(db, user))