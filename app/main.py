from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from .database import Base, SessionLocal, engine, get_db
from .models import ChangeEvent, DNSSnapshot, MonitoredDomain
from .monitor import DNSMonitorService, run_single_check
from .schemas import DomainCreate, DomainOut, EventOut

Base.metadata.create_all(bind=engine)
monitor = DNSMonitorService()
scheduler = BackgroundScheduler()
templates = Jinja2Templates(directory="app/templates")


def run_all_domains():
    db = SessionLocal()
    try:
        domains = db.query(MonitoredDomain).filter(MonitoredDomain.enabled.is_(True)).all()
        for d in domains:
            run_single_check(db, monitor, d)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(run_all_domains, "interval", seconds=300, id="dns_monitor_global", replace_existing=True)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="DNS Monitor", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/domains", response_model=DomainOut)
def create_domain(payload: DomainCreate, db: Session = Depends(get_db)):
    existing = db.query(MonitoredDomain).filter(MonitoredDomain.domain == payload.domain.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Domain already exists")

    domain = MonitoredDomain(
        domain=payload.domain.lower(),
        enabled=payload.enabled,
        check_interval_sec=payload.check_interval_sec,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


@app.get("/domains", response_model=list[DomainOut])
def list_domains(db: Session = Depends(get_db)):
    return db.query(MonitoredDomain).order_by(MonitoredDomain.domain.asc()).all()


@app.post("/domains/{domain_id}/run")
def run_domain_check(domain_id: int, db: Session = Depends(get_db)):
    domain = db.query(MonitoredDomain).filter(MonitoredDomain.id == domain_id).first()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    run_single_check(db, monitor, domain)
    return {"status": "done"}


@app.get("/domains/{domain_id}/events", response_model=list[EventOut])
def list_events(domain_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ChangeEvent)
        .filter(ChangeEvent.domain_id == domain_id)
        .order_by(desc(ChangeEvent.detected_at))
        .all()
    )


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    domains = db.query(MonitoredDomain).order_by(MonitoredDomain.domain.asc()).all()
    recent_events = (
        db.query(ChangeEvent)
        .options(joinedload(ChangeEvent.domain))
        .order_by(desc(ChangeEvent.detected_at))
        .limit(20)
        .all()
    )
    recent_snapshots = (
        db.query(DNSSnapshot)
        .options(
            joinedload(DNSSnapshot.domain),
            joinedload(DNSSnapshot.mx_records),
            joinedload(DNSSnapshot.mx_a_records),
        )
        .order_by(desc(DNSSnapshot.checked_at))
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "domains": domains,
            "recent_events": recent_events,
            "recent_snapshots": recent_snapshots,
        },
    )


@app.post("/ui/domains", response_class=RedirectResponse)
def create_domain_ui(
    domain: str = Form(...),
    check_interval_sec: int = Form(300),
    enabled: bool = Form(True),
    db: Session = Depends(get_db),
):
    existing = db.query(MonitoredDomain).filter(MonitoredDomain.domain == domain.lower()).first()
    if not existing:
        db.add(MonitoredDomain(domain=domain.lower(), check_interval_sec=check_interval_sec, enabled=enabled))
        db.commit()
    return RedirectResponse(url="/", status_code=303)


@app.post("/ui/domains/{domain_id}/run", response_class=RedirectResponse)
def run_domain_ui(domain_id: int, db: Session = Depends(get_db)):
    domain = db.query(MonitoredDomain).filter(MonitoredDomain.id == domain_id).first()
    if domain:
        run_single_check(db, monitor, domain)
    return RedirectResponse(url="/", status_code=303)
