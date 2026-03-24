"""
公章审批系统API
"""

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
import json
import os
import uuid

import config
from app.database import get_db
from app.models import SealRequest, Teacher
from app.deps import require_admin
from app.sessions import verify_teacher_session

router = APIRouter(prefix="/api", tags=["公章审批"])


def _get_teacher_id_from_request(request: Request) -> int:
    token = request.headers.get("X-Teacher-Token") or request.cookies.get("teacher_token") or ""
    if not token:
        raise HTTPException(status_code=401, detail="请先登录（教师token缺失）")
    teacher_id = verify_teacher_session(token)
    if not teacher_id:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return int(teacher_id)


def _parse_stamp_positions(stamp_positions: Any) -> List[Dict[str, Any]]:
    """
    stamp_positions 期望为：
    [
      {"page": 0, "x": 123.4, "y": 56.7},
      ...
    ]
    """
    if stamp_positions is None:
        return []
    if isinstance(stamp_positions, str):
        try:
            stamp_positions = json.loads(stamp_positions)
        except Exception:
            raise HTTPException(status_code=400, detail="stamp_positions 不是合法JSON")

    if not isinstance(stamp_positions, list):
        raise HTTPException(status_code=400, detail="stamp_positions 必须是数组")

    out: List[Dict[str, Any]] = []
    for i, pos in enumerate(stamp_positions):
        if not isinstance(pos, dict):
            raise HTTPException(status_code=400, detail=f"stamp_positions[{i}] 格式错误")
        page = pos.get("page")
        x = pos.get("x")
        y = pos.get("y")
        if page is None or x is None or y is None:
            raise HTTPException(status_code=400, detail=f"stamp_positions[{i}] 缺少 page/x/y")
        try:
            page = int(page)
            x = float(x)
            y = float(y)
        except Exception:
            raise HTTPException(status_code=400, detail=f"stamp_positions[{i}] page/x/y 类型不正确")
        out.append({"page": page, "x": x, "y": y})
    return out


@router.post("/seal-requests")
async def create_seal_request(
    request: Request,
    pdf: UploadFile = File(...),
    stamp_positions: str = Form(...),
    remark: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    teacher_id = _get_teacher_id_from_request(request)

    positions = _parse_stamp_positions(stamp_positions)
    if len(positions) == 0:
        raise HTTPException(status_code=400, detail="请至少选择一个公章盖章位置")

    # save uploaded pdf
    seals_dir = config.UPLOAD_DIR / "seals"
    seals_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(pdf.filename).suffix.lower() or ".pdf"
    safe_ext = ext if ext in {".pdf"} else ".pdf"
    filename = f"{teacher_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}{safe_ext}"
    pdf_path = seals_dir / filename

    content = await pdf.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传的PDF内容为空")
    with open(pdf_path, "wb") as f:
        f.write(content)

    db_req = SealRequest(
        teacher_id=teacher_id,
        pdf_path=str(pdf_path),
        stamp_positions=positions,
        remark=remark,
        status="pending",
    )
    db.add(db_req)
    db.commit()
    db.refresh(db_req)

    return {
        "ok": True,
        "id": db_req.id,
        "status": db_req.status,
        "created_at": db_req.created_at,
    }


@router.get("/seal-requests/my")
async def my_seal_requests(
    request: Request,
    db: Session = Depends(get_db),
):
    teacher_id = _get_teacher_id_from_request(request)
    items = (
        db.query(SealRequest)
        .filter(SealRequest.teacher_id == teacher_id)
        .order_by(SealRequest.created_at.desc())
        .all()
    )
    return [
        {
            "id": it.id,
            "status": it.status,
            "remark": it.remark,
            "stamp_count": len(it.stamp_positions or []),
            "created_at": it.created_at,
            "reviewed_at": it.reviewed_at,
        }
        for it in items
    ]


@router.get("/seal-requests/{request_id}")
async def get_seal_request_detail(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
):
    # teacher can view owner; if not logged, forbid
    teacher_id = _get_teacher_id_from_request(request)

    item = db.query(SealRequest).filter(SealRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="申请不存在")
    if item.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="无权查看此申请")

    return {
        "id": item.id,
        "status": item.status,
        "remark": item.remark,
        "stamp_positions": item.stamp_positions or [],
        "created_at": item.created_at,
        "reviewed_at": item.reviewed_at,
        "review_comment": item.review_comment,
    }


@router.get("/seal-requests/{request_id}/pdf")
async def get_seal_request_pdf(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
):
    teacher_id = _get_teacher_id_from_request(request)
    item = db.query(SealRequest).filter(SealRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="申请不存在")
    if item.teacher_id != teacher_id:
        raise HTTPException(status_code=403, detail="无权查看此PDF")

    pdf_path = item.pdf_path
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF文件不存在")

    from fastapi.responses import FileResponse
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=Path(pdf_path).name,
        headers={"Content-Disposition": "inline"},
    )


class SealReviewBody(BaseModel):
    status: str  # approved / rejected
    comment: Optional[str] = None


@router.get("/admin/seal-requests", dependencies=[Depends(require_admin)])
async def admin_list_seal_requests(
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(SealRequest).order_by(SealRequest.created_at.desc())
    if status:
        q = q.filter(SealRequest.status == status)

    items = q.all()
    out = []
    for it in items:
        teacher = db.query(Teacher).filter(Teacher.id == it.teacher_id).first()
        out.append(
            {
                "id": it.id,
                "teacher_id": it.teacher_id,
                "teacher_name": teacher.name if teacher else "",
                "status": it.status,
                "remark": it.remark,
                "stamp_count": len(it.stamp_positions or []),
                "created_at": it.created_at,
                "reviewed_at": it.reviewed_at,
                "review_comment": it.review_comment,
            }
        )
    return out


@router.post("/admin/seal-requests/{request_id}/review", dependencies=[Depends(require_admin)])
async def admin_review_seal_request(
    request: Request,
    request_id: int,
    body: SealReviewBody,
    db: Session = Depends(get_db),
):
    item = db.query(SealRequest).filter(SealRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="申请不存在")

    new_status = (body.status or "").strip().lower()
    if new_status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="status 只能是 approved 或 rejected")

    item.status = "approved" if new_status == "approved" else "rejected"
    item.reviewed_at = datetime.now()
    item.review_comment = body.comment

    # store admin token (best effort)
    item.reviewed_by = request.headers.get("X-Admin-Token") or request.cookies.get("admin_token")

    db.commit()
    return {"ok": True, "id": item.id, "status": item.status}


@router.get("/admin/seal-requests/{request_id}", dependencies=[Depends(require_admin)])
async def admin_get_seal_request_detail(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(SealRequest).filter(SealRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="申请不存在")

    teacher = db.query(Teacher).filter(Teacher.id == item.teacher_id).first()
    return {
        "id": item.id,
        "teacher_id": item.teacher_id,
        "teacher_name": teacher.name if teacher else "",
        "status": item.status,
        "remark": item.remark,
        "stamp_positions": item.stamp_positions or [],
        "created_at": item.created_at,
        "reviewed_at": item.reviewed_at,
        "review_comment": item.review_comment,
    }


@router.get("/admin/seal-requests/{request_id}/pdf", dependencies=[Depends(require_admin)])
async def admin_get_seal_request_pdf(
    request: Request,
    request_id: int,
    db: Session = Depends(get_db),
):
    item = db.query(SealRequest).filter(SealRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="申请不存在")

    pdf_path = item.pdf_path
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF文件不存在")

    from fastapi.responses import FileResponse
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=Path(pdf_path).name,
        headers={"Content-Disposition": "inline"},
    )

