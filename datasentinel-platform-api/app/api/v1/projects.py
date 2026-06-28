from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Project, DQARun, DQAViolation, Dataset
from app.schemas import ProjectCreate, ProjectOut

from app.core.tenancy import resolve_tenant_id

router = APIRouter()

@router.get("/", response_model=List[ProjectOut])
def list_projects(db: Session = Depends(get_db), user=Depends(get_current_user)):
    tenant_id = resolve_tenant_id(db)
    return db.query(Project).filter(Project.is_active == True, Project.tenant_id == tenant_id).all()

@router.post("/", response_model=ProjectOut)
def create_project(data: ProjectCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    tenant_id = resolve_tenant_id(db)
    project = Project(**data.model_dump(), tenant_id=tenant_id, created_by=user.id)
    db.add(project); db.commit(); db.refresh(project)
    return project

@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p: raise HTTPException(404, "Project not found")
    return p

@router.get("/{project_id}/summary")
def project_summary(project_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project: raise HTTPException(404, "Project not found")
    total_datasets = db.query(Dataset).filter(Dataset.project_id == project_id).count()
    runs = db.query(DQARun).filter(DQARun.project_id == project_id).order_by(DQARun.triggered_at.desc()).limit(5).all()
    latest_run = runs[0] if runs else None
    return {
        "project_id": str(project_id),
        "name": project.name,
        "total_datasets": total_datasets,
        "latest_readiness_score": latest_run.readiness_score if latest_run else None,
        "latest_run_status": latest_run.status if latest_run else None,
        "recent_runs": [{"id": str(r.id), "status": r.status, "readiness_score": r.readiness_score,
                          "triggered_at": r.triggered_at.isoformat(), "total_violations": r.total_violations} for r in runs]
    }

@router.delete("/{project_id}")
def archive_project(project_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    p = db.query(Project).filter(Project.id == project_id).first()
    if not p: raise HTTPException(404, "Project not found")
    p.is_active = False; db.commit()
    return {"message": "Project archived"}
