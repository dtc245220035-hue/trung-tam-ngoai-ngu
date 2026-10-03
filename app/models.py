from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey,
                        Integer, Numeric, String, Time, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
MONEY = Numeric(12, 2, asdecimal=False)


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(10), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    __table_args__ = (
        CheckConstraint("role IN ('admin','consultant','teacher','student')", name="ck_users_role"),
        CheckConstraint("status IN ('active','inactive','locked')", name="ck_users_status"),
    )


class Student(Base):
    __tablename__ = "students"
    student_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), unique=True, nullable=False)
    student_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    date_of_birth: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    level: Mapped[str | None] = mapped_column(String(5), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user = relationship("User")
    enrollments = relationship("Enrollment", back_populates="student")
    invoices = relationship("Invoice", back_populates="student")
    __table_args__ = (
        CheckConstraint("level IS NULL OR level IN ('A1','A2','B1','B2','C1','C2')", name="ck_students_level"),
    )


class Teacher(Base):
    __tablename__ = "teachers"
    teacher_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), unique=True, nullable=False)
    teacher_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    specialization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    degree: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    user = relationship("User")
    classes = relationship("ClassRoom", back_populates="teacher")
    __table_args__ = (
        CheckConstraint("status IN ('active','inactive')", name="ck_teachers_status"),
    )


class Course(Base):
    __tablename__ = "courses"
    course_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    course_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    level: Mapped[str] = mapped_column(String(5), nullable=False)
    tuition_fee: Mapped[float] = mapped_column(MONEY, nullable=False)
    duration: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    classes = relationship("ClassRoom", back_populates="course")
    __table_args__ = (
        CheckConstraint("tuition_fee > 0", name="ck_courses_fee"),
        CheckConstraint("duration > 0", name="ck_courses_duration"),
        CheckConstraint("level IN ('A1','A2','B1','B2','C1','C2')", name="ck_courses_level"),
    )


class ClassRoom(Base):
    __tablename__ = "classes"
    class_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id"), nullable=False)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("teachers.teacher_id"), nullable=True)
    room: Mapped[str | None] = mapped_column(String(20), nullable=True)
    max_students: Mapped[int] = mapped_column(Integer, nullable=False)
    current_students: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    course = relationship("Course", back_populates="classes")
    teacher = relationship("Teacher", back_populates="classes")
    schedules = relationship("Schedule", back_populates="classroom", cascade="all, delete-orphan")
    enrollments = relationship("Enrollment", back_populates="classroom")
    __table_args__ = (
        CheckConstraint("max_students > 0 AND max_students <= 30", name="ck_classes_max"),
        CheckConstraint("current_students >= 0 AND current_students <= max_students", name="ck_classes_current"),
        CheckConstraint("status IN ('open','closed')", name="ck_classes_status"),
    )

    @property
    def seats_left(self) -> int:
        return self.max_students - self.current_students


class Schedule(Base):
    __tablename__ = "schedules"
    schedule_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.class_id"), nullable=False)
    day_of_week: Mapped[str] = mapped_column(String(10), nullable=False)
    start_time: Mapped[datetime] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime] = mapped_column(Time, nullable=False)
    start_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    end_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    classroom = relationship("ClassRoom", back_populates="schedules")
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_schedules_time"),
        CheckConstraint("start_date < end_date", name="ck_schedules_date"),
    )


class Enrollment(Base):
    __tablename__ = "enrollments"
    enrollment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.class_id"), nullable=False)
    enroll_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    student = relationship("Student", back_populates="enrollments")
    classroom = relationship("ClassRoom", back_populates="enrollments")
    __table_args__ = (
        UniqueConstraint("student_id", "class_id", name="uq_enrollment"),
        CheckConstraint("status IN ('active','cancelled')", name="ck_enrollments_status"),
    )


class Invoice(Base):
    __tablename__ = "invoices"
    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.class_id"), nullable=False)
    total_amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    paid_amount: Mapped[float] = mapped_column(MONEY, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unpaid")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    student = relationship("Student", back_populates="invoices")
    classroom = relationship("ClassRoom")
    payments = relationship("Payment", back_populates="invoice")
    __table_args__ = (
        CheckConstraint("total_amount > 0", name="ck_invoices_total"),
        CheckConstraint("paid_amount >= 0 AND paid_amount <= total_amount", name="ck_invoices_paid"),
        CheckConstraint("status IN ('unpaid','partial','paid')", name="ck_invoices_status"),
    )

    @property
    def remaining_amount(self) -> float:
        return self.total_amount - self.paid_amount


class Payment(Base):
    __tablename__ = "payments"
    payment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.invoice_id"), nullable=False)
    amount: Mapped[float] = mapped_column(MONEY, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    payment_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    invoice = relationship("Invoice", back_populates="payments")
    creator = relationship("User", foreign_keys=[created_by])
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount"),
        CheckConstraint("method IN ('cash','transfer')", name="ck_payments_method"),
    )


class Attendance(Base):
    __tablename__ = "attendance"
    attendance_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.class_id"), nullable=False)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id"), nullable=False)
    session_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    student = relationship("Student")
    classroom = relationship("ClassRoom")
    __table_args__ = (
        UniqueConstraint("class_id", "student_id", "session_date", name="uq_attendance"),
        CheckConstraint("status IN ('present','absent','late')", name="ck_attendance_status"),
    )


class Result(Base):
    __tablename__ = "results"
    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id"), nullable=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("classes.class_id"), nullable=False)
    listening: Mapped[float] = mapped_column(Float, nullable=False)
    speaking: Mapped[float] = mapped_column(Float, nullable=False)
    reading: Mapped[float] = mapped_column(Float, nullable=False)
    writing: Mapped[float] = mapped_column(Float, nullable=False)
    average: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    student = relationship("Student")
    classroom = relationship("ClassRoom")
    __table_args__ = (
        CheckConstraint("listening BETWEEN 0 AND 10 AND speaking BETWEEN 0 AND 10 AND reading BETWEEN 0 AND 10 AND writing BETWEEN 0 AND 10", name="ck_results_score"),
        UniqueConstraint("student_id", "class_id", name="uq_results"),
    )
