from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import pandas as pd
import os, shutil, uuid as uuid_lib
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.config import settings
from app.models import Dataset, Project
from app.schemas import DatasetOut
from app.core.tenancy import resolve_tenant_id
from app.services.storage import get_dataset_store

router = APIRouter()

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

def _load_dataframe(path: str) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)

def _profile_dataframe(df: pd.DataFrame) -> list:
    cols = []
    for col in df.columns:
        series = df[col]
        null_count = int(series.isnull().sum())
        dtype = str(series.dtype)
        is_numeric = pd.api.types.is_numeric_dtype(series)
        meta = {
            "name": col,
            "dtype": dtype,
            "null_count": null_count,
            "null_pct": round(null_count / len(df) * 100, 2) if len(df) else 0,
            "unique_count": int(series.nunique()),
        }
        if is_numeric:
            meta.update({
                "min": round(float(series.min()), 4) if null_count < len(df) else None,
                "max": round(float(series.max()), 4) if null_count < len(df) else None,
                "mean": round(float(series.mean()), 4) if null_count < len(df) else None,
                "std": round(float(series.std()), 4) if null_count < len(df) else None,
            })
        cols.append(meta)
    return cols

@router.post("/upload", response_model=DatasetOut)
async def upload_dataset(
    project_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not supported. Use CSV or Excel.")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id = str(uuid_lib.uuid4())
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    tenant_id = resolve_tenant_id(db, project.tenant_id)

    content = await file.read()
    store = get_dataset_store()
    dest_uri = store.build_dataset_uri(str(tenant_id), file_id, ext)
    store.save_bytes(dest_uri, content)

    try:
        df = store.load_df(dest_uri)
        cols_meta = _profile_dataframe(df)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {str(e)}")

    dataset = Dataset(
        tenant_id=tenant_id,
        project_id=project_id,
        name=file.filename,
        source_type=ext.lstrip("."),
        row_count=len(df),
        column_count=len(df.columns),
        columns_meta=cols_meta,
        storage_path=dest_uri if not dest_uri.startswith("s3://") else None,
        s3_uri=dest_uri if dest_uri.startswith("s3://") else None,
        ingested_by=user.id,
        status="ready"
    )
    db.add(dataset); db.commit(); db.refresh(dataset)
    return dataset

@router.get("/", response_model=List[DatasetOut])
def list_datasets(project_id: Optional[UUID] = None, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(Dataset)
    if project_id:
        q = q.filter(Dataset.project_id == project_id)
    return q.order_by(Dataset.ingested_at.desc()).all()

@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    d = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not d: raise HTTPException(404, "Dataset not found")
    return d

@router.get("/{dataset_id}/profile")
def dataset_profile(dataset_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    d = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not d: raise HTTPException(404, "Dataset not found")
    return {"dataset_id": str(dataset_id), "name": d.name, "row_count": d.row_count,
            "column_count": d.column_count, "columns": d.columns_meta}

@router.get("/{dataset_id}/preview")
def dataset_preview(dataset_id: UUID, rows: int = 20, db: Session = Depends(get_db), user=Depends(get_current_user)):
    d = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not d: raise HTTPException(404, "Dataset not found")
    if not d.storage_path and not d.s3_uri:
        raise HTTPException(404, "File not found on disk")
    store = get_dataset_store()
    df = store.load_df(store.resolve_uri(d)).head(rows)
    return {"columns": list(df.columns), "rows": df.fillna("").astype(str).values.tolist()}

@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    d = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not d: raise HTTPException(404, "Dataset not found")
    if d.storage_path and os.path.exists(d.storage_path):
        os.remove(d.storage_path)
    db.delete(d); db.commit()
    return {"message": "Dataset deleted"}
