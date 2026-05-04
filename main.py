from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import models
import database

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ─── Helper: get logged-in user from cookie ───────────────────────────────────
def get_current_user(request: Request, db: Session):
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == int(user_id)).first()


# ─── Home Page ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ─── Register ──────────────────────────────────────────────────────────────────
@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request, "error": None})


@app.post("/register")
def register_user(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("student"),
    db: Session = Depends(database.get_db),
):
    # Check if email already exists
    existing = db.query(models.User).filter(models.User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Email already registered!"},
        )

    new_user = models.User(name=name, email=email, password=password, role=role)
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/login", status_code=302)


# ─── Login ─────────────────────────────────────────────────────────────────────
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.post("/login")
def login_user(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db),
):
    user = db.query(models.User).filter(
        models.User.email == email,
        models.User.password == password,
    ).first()

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password!"},
        )

    # Store user id in cookie (simple session)
    response = RedirectResponse(url="/dashboard", status_code=302)
    response.set_cookie(key="user_id", value=str(user.id))
    return response


# ─── Logout ────────────────────────────────────────────────────────────────────
@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("user_id")
    return response


# ─── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    events = db.query(models.Event).all()
    # Get event IDs the user already registered for
    my_registrations = db.query(models.Registration).filter(
        models.Registration.user_id == user.id
    ).all()
    registered_event_ids = [r.event_id for r in my_registrations]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "events": events,
            "registered_event_ids": registered_event_ids,
        },
    )


# ─── All Events (public) ───────────────────────────────────────────────────────
@app.get("/events", response_class=HTMLResponse)
def all_events(request: Request, db: Session = Depends(database.get_db)):
    events = db.query(models.Event).all()
    user = get_current_user(request, db)
    return templates.TemplateResponse(
        "events.html", {"request": request, "events": events, "user": user}
    )


# ─── Register for Event ────────────────────────────────────────────────────────
@app.post("/register-event/{event_id}")
def register_for_event(
    event_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Check if already registered
    already = db.query(models.Registration).filter(
        models.Registration.user_id == user.id,
        models.Registration.event_id == event_id,
    ).first()

    if not already:
        reg = models.Registration(user_id=user.id, event_id=event_id)
        db.add(reg)
        db.commit()

    return RedirectResponse(url="/dashboard", status_code=302)


# ─── My Events ─────────────────────────────────────────────────────────────────
@app.get("/my-events", response_class=HTMLResponse)
def my_events(request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    registrations = db.query(models.Registration).filter(
        models.Registration.user_id == user.id
    ).all()
    event_ids = [r.event_id for r in registrations]
    my_event_list = db.query(models.Event).filter(models.Event.id.in_(event_ids)).all()

    return templates.TemplateResponse(
        "my_events.html",
        {"request": request, "user": user, "events": my_event_list},
    )


# ─── Admin: Create Event ───────────────────────────────────────────────────────
@app.get("/create-event", response_class=HTMLResponse)
def create_event_page(request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        "create_event.html", {"request": request, "user": user}
    )


@app.post("/create-event")
def create_event(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    date: str = Form(...),
    location: str = Form(""),
    db: Session = Depends(database.get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)

    new_event = models.Event(
        title=title, description=description, date=date, location=location
    )
    db.add(new_event)
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


# ─── Admin: Delete Event ───────────────────────────────────────────────────────
@app.post("/delete-event/{event_id}")
def delete_event(
    event_id: int,
    request: Request,
    db: Session = Depends(database.get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)

    # Delete related registrations first
    db.query(models.Registration).filter(
        models.Registration.event_id == event_id
    ).delete()
    db.query(models.Event).filter(models.Event.id == event_id).delete()
    db.commit()
    return RedirectResponse(url="/dashboard", status_code=302)


# ─── Admin: View All Registrations ────────────────────────────────────────────
@app.get("/admin/registrations", response_class=HTMLResponse)
def admin_registrations(request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse(url="/dashboard", status_code=302)

    # Get all registrations with user and event info
    regs = db.query(models.Registration).all()
    data = []
    for r in regs:
        student = db.query(models.User).filter(models.User.id == r.user_id).first()
        event = db.query(models.Event).filter(models.Event.id == r.event_id).first()
        if student and event:
            data.append({"student": student.name, "event": event.title, "date": event.date})

    return templates.TemplateResponse(
        "admin_registrations.html",
        {"request": request, "user": user, "data": data},
    )
