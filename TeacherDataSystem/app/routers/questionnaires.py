"""
问卷系统API
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import secrets

from sqlalchemy.orm.attributes import flag_modified

from app.database import get_db
from app.models import Questionnaire, QuestionnaireResponse, Teacher
from app.deps import require_admin, assert_admin_or_teacher
from app.utils.age_birth import normalize_extra_age_birth

router = APIRouter(prefix="/api/questionnaires", tags=["问卷系统"])


class QuestionnaireField(BaseModel):
    name: str
    label: str
    type: str  # text, number, select, date, etc.
    required: bool = False
    options: Optional[List[str]] = None  # 用于select类型


class QuestionnaireCreate(BaseModel):
    title: str
    description: Optional[str] = None
    fields: List[QuestionnaireField]
    teacher_ids: List[int]
    deadline: Optional[datetime] = None
    created_by: Optional[str] = None


class QuestionnaireResponseCreate(BaseModel):
    questionnaire_id: int
    teacher_id: int
    answers: Dict[str, Any]


class QuestionnaireReview(BaseModel):
    status: str  # approved/rejected
    comment: Optional[str] = None


class QuestionnaireResponseResponse(BaseModel):
    id: int
    questionnaire_id: int
    teacher_id: int
    teacher_name: str
    answers: Dict[str, Any]
    status: str
    confirmed_status: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    reviewed_by: Optional[str]
    reviewed_at: Optional[datetime]
    review_comment: Optional[str]
    submitted_at: datetime

    class Config:
        from_attributes = True


class QuestionnaireResponseFull(BaseModel):
    id: int
    title: str
    description: Optional[str]
    fields: List[Dict[str, Any]]
    teacher_ids: List[int]
    status: str
    created_by: Optional[str]
    created_at: datetime
    deadline: Optional[datetime]
    share_token: Optional[str] = None

    class Config:
        from_attributes = True


class TeacherAuth(BaseModel):
    id_number: str
    phone: str


class ConfirmRequest(BaseModel):
    confirmed: bool  # True=确认信息, False=信息有误


@router.get(
    "/",
    response_model=List[QuestionnaireResponseFull],
    dependencies=[Depends(require_admin)],
)
def get_questionnaires(
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取问卷列表"""
    query = db.query(Questionnaire)
    if status:
        query = query.filter(Questionnaire.status == status)
    questionnaires = query.all()
    return questionnaires


@router.get(
    "/{questionnaire_id}",
    response_model=QuestionnaireResponseFull,
    dependencies=[Depends(require_admin)],
)
def get_questionnaire(questionnaire_id: int, db: Session = Depends(get_db)):
    """获取单个问卷"""
    questionnaire = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="问卷不存在")
    return questionnaire


@router.post(
    "/",
    response_model=QuestionnaireResponseFull,
    dependencies=[Depends(require_admin)],
)
def create_questionnaire(questionnaire: QuestionnaireCreate, db: Session = Depends(get_db)):
    """创建问卷"""
    fields_data = [field.model_dump() for field in questionnaire.fields]
    
    # 生成分享token
    share_token = secrets.token_urlsafe(32)
    
    db_questionnaire = Questionnaire(
        title=questionnaire.title,
        description=questionnaire.description,
        fields=fields_data,
        teacher_ids=questionnaire.teacher_ids,
        deadline=questionnaire.deadline,
        created_by=questionnaire.created_by,
        status="active",
        share_token=share_token
    )
    db.add(db_questionnaire)
    db.commit()
    db.refresh(db_questionnaire)
    return db_questionnaire


@router.post("/responses", response_model=QuestionnaireResponseResponse)
def submit_response(
    request: Request,
    response: QuestionnaireResponseCreate,
    db: Session = Depends(get_db),
):
    """提交问卷回答（须管理员登录，或教师登录且 teacher_id 与本人一致）"""
    assert_admin_or_teacher(request, response.teacher_id)

    questionnaire = db.query(Questionnaire).filter(Questionnaire.id == response.questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="问卷不存在")
    
    if questionnaire.status != "active":
        raise HTTPException(status_code=400, detail="问卷已关闭")
    
    # 检查是否已提交
    existing = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.questionnaire_id == response.questionnaire_id,
        QuestionnaireResponse.teacher_id == response.teacher_id
    ).first()
    
    if existing:
        # 更新已有回答
        existing.answers = response.answers
        existing.submitted_at = datetime.now()
        existing.status = "pending"
    else:
        # 创建新回答
        existing = QuestionnaireResponse(
            questionnaire_id=response.questionnaire_id,
            teacher_id=response.teacher_id,
            answers=response.answers,
            status="pending"
        )
        db.add(existing)
    
    db.commit()
    db.refresh(existing)

    teacher = db.query(Teacher).filter(Teacher.id == response.teacher_id).first()
    # 提交问卷后，先合并到教师扩展数据；这样导出填报任务时可直接取到这些字段。
    if teacher:
        if not teacher.extra_data:
            teacher.extra_data = {}
        teacher.extra_data.update(existing.answers)
        normalize_extra_age_birth(teacher.extra_data, existing.submitted_at or datetime.now())
        flag_modified(teacher, "extra_data")
        teacher.updated_at = datetime.now()
        db.commit()

    return QuestionnaireResponseResponse(
        id=existing.id,
        questionnaire_id=existing.questionnaire_id,
        teacher_id=existing.teacher_id,
        teacher_name=teacher.name if teacher else "",
        answers=existing.answers,
        status=existing.status,
        confirmed_status=getattr(existing, "confirmed_status", None),
        confirmed_at=getattr(existing, "confirmed_at", None),
        reviewed_by=existing.reviewed_by,
        reviewed_at=existing.reviewed_at,
        review_comment=existing.review_comment,
        submitted_at=existing.submitted_at
    )


@router.get(
    "/responses/{response_id}",
    response_model=QuestionnaireResponseResponse,
    dependencies=[Depends(require_admin)],
)
def get_response(response_id: int, db: Session = Depends(get_db)):
    """获取单个回答"""
    response = db.query(QuestionnaireResponse).filter(QuestionnaireResponse.id == response_id).first()
    if not response:
        raise HTTPException(status_code=404, detail="回答不存在")
    
    teacher = db.query(Teacher).filter(Teacher.id == response.teacher_id).first()
    return QuestionnaireResponseResponse(
        id=response.id,
        questionnaire_id=response.questionnaire_id,
        teacher_id=response.teacher_id,
        teacher_name=teacher.name if teacher else "",
        answers=response.answers,
        status=response.status,
        confirmed_status=response.confirmed_status,
        confirmed_at=response.confirmed_at,
        reviewed_by=response.reviewed_by,
        reviewed_at=response.reviewed_at,
        review_comment=response.review_comment,
        submitted_at=response.submitted_at
    )


class ResponseUpdate(BaseModel):
    answers: Dict[str, Any]


@router.put(
    "/responses/{response_id}",
    response_model=QuestionnaireResponseResponse,
    dependencies=[Depends(require_admin)],
)
def update_response(response_id: int, update_data: ResponseUpdate, db: Session = Depends(get_db)):
    """更新回答（管理员代填）"""
    response = db.query(QuestionnaireResponse).filter(QuestionnaireResponse.id == response_id).first()
    if not response:
        raise HTTPException(status_code=404, detail="回答不存在")
    
    response.answers = update_data.answers
    response.submitted_at = datetime.now()

    teacher = db.query(Teacher).filter(Teacher.id == response.teacher_id).first()
    if teacher:
        if not teacher.extra_data:
            teacher.extra_data = {}
        teacher.extra_data.update(response.answers)
        normalize_extra_age_birth(teacher.extra_data, response.submitted_at or datetime.now())
        flag_modified(teacher, "extra_data")
        teacher.updated_at = datetime.now()

    db.commit()
    db.refresh(response)

    return QuestionnaireResponseResponse(
        id=response.id,
        questionnaire_id=response.questionnaire_id,
        teacher_id=response.teacher_id,
        teacher_name=teacher.name if teacher else "",
        answers=response.answers,
        status=response.status,
        confirmed_status=response.confirmed_status,
        confirmed_at=response.confirmed_at,
        reviewed_by=response.reviewed_by,
        reviewed_at=response.reviewed_at,
        review_comment=response.review_comment,
        submitted_at=response.submitted_at
    )


@router.get(
    "/{questionnaire_id}/responses",
    response_model=List[QuestionnaireResponseResponse],
    dependencies=[Depends(require_admin)],
)
def get_questionnaire_responses(
    questionnaire_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取问卷的所有回答"""
    query = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.questionnaire_id == questionnaire_id
    )
    if status:
        query = query.filter(QuestionnaireResponse.status == status)
    
    responses = query.all()
    result = []
    for response in responses:
        teacher = db.query(Teacher).filter(Teacher.id == response.teacher_id).first()
        result.append(QuestionnaireResponseResponse(
            id=response.id,
            questionnaire_id=response.questionnaire_id,
            teacher_id=response.teacher_id,
            teacher_name=teacher.name if teacher else "",
            answers=response.answers,
            status=response.status,
            confirmed_status=response.confirmed_status,
            confirmed_at=response.confirmed_at,
            reviewed_by=response.reviewed_by,
            reviewed_at=response.reviewed_at,
            review_comment=response.review_comment,
            submitted_at=response.submitted_at
        ))
    return result


@router.post(
    "/responses/{response_id}/review",
    dependencies=[Depends(require_admin)],
)
def review_response(
    response_id: int,
    review: QuestionnaireReview,
    db: Session = Depends(get_db),
    reviewed_by: Optional[str] = Query(None, description="审核人署名，可空"),
):
    """审核问卷回答"""
    response = db.query(QuestionnaireResponse).filter(QuestionnaireResponse.id == response_id).first()
    if not response:
        raise HTTPException(status_code=404, detail="回答不存在")
    
    response.status = review.status
    response.reviewed_by = reviewed_by or "管理员"
    response.reviewed_at = datetime.now()
    response.review_comment = review.comment
    
    # 如果审核通过，合并到教师数据
    if review.status == "approved":
        teacher = db.query(Teacher).filter(Teacher.id == response.teacher_id).first()
        if teacher:
            # 合并答案到extra_data
            if not teacher.extra_data:
                teacher.extra_data = {}
            teacher.extra_data.update(response.answers)
            normalize_extra_age_birth(teacher.extra_data, datetime.now())
            flag_modified(teacher, "extra_data")
            teacher.updated_at = datetime.now()
    
    db.commit()
    return {"message": "审核完成"}


@router.put(
    "/{questionnaire_id}/close",
    dependencies=[Depends(require_admin)],
)
def close_questionnaire(questionnaire_id: int, db: Session = Depends(get_db)):
    """关闭问卷"""
    questionnaire = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="问卷不存在")
    
    questionnaire.status = "closed"
    db.commit()
    return {"message": "问卷已关闭"}


@router.get(
    "/{questionnaire_id}/share-link",
    dependencies=[Depends(require_admin)],
)
def get_share_link(questionnaire_id: int, db: Session = Depends(get_db)):
    """获取问卷分享链接"""
    questionnaire = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="问卷不存在")
    
    # 如果没有token，生成一个
    if not questionnaire.share_token:
        questionnaire.share_token = secrets.token_urlsafe(32)
        db.commit()
    
    # 这里需要根据实际部署的域名来生成链接
    # 暂时使用相对路径，前端会处理
    share_url = f"/confirm/{questionnaire.share_token}"
    
    return {
        "share_token": questionnaire.share_token,
        "share_url": share_url,
        "full_url": share_url  # 前端可以拼接完整URL
    }


@router.post("/confirm/{share_token}/auth")
def authenticate_teacher(share_token: str, auth: TeacherAuth, db: Session = Depends(get_db)):
    """教师身份验证（通过身份证号和手机号）"""
    # 查找问卷
    questionnaire = db.query(Questionnaire).filter(Questionnaire.share_token == share_token).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="问卷不存在或链接无效")
    
    # 验证教师身份
    teacher = db.query(Teacher).filter(
        Teacher.id_number == auth.id_number,
        Teacher.phone == auth.phone
    ).first()
    
    if not teacher:
        raise HTTPException(status_code=401, detail="身份证号或手机号不正确")
    
    # 检查教师是否在问卷的教师列表中
    # 确保teacher_ids是整数列表进行比较
    q_teacher_ids = [int(tid) for tid in questionnaire.teacher_ids if tid is not None] if questionnaire.teacher_ids else []
    if teacher.id not in q_teacher_ids:
        raise HTTPException(status_code=403, detail="您不在本次问卷的教师列表中")
    
    # 查找或创建问卷回答
    response = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.questionnaire_id == questionnaire.id,
        QuestionnaireResponse.teacher_id == teacher.id
    ).first()
    
    # 如果没有回答，创建一个空的（用于确认）
    if not response:
        response = QuestionnaireResponse(
            questionnaire_id=questionnaire.id,
            teacher_id=teacher.id,
            answers={},  # 空回答，仅用于确认
            status="pending",
            confirmed_status="pending"
        )
        db.add(response)
        db.commit()
        db.refresh(response)
    
    return {
        "teacher_id": teacher.id,
        "teacher_name": teacher.name,
        "questionnaire_id": questionnaire.id,
        "questionnaire_title": questionnaire.title,
        "response_id": response.id,
        "answers": response.answers,
        "confirmed_status": response.confirmed_status,
        "fields": questionnaire.fields
    }


@router.post("/confirm/{share_token}/confirm")
def confirm_response(share_token: str, auth: TeacherAuth, confirm: ConfirmRequest, db: Session = Depends(get_db)):
    """确认或拒绝问卷信息"""
    # 验证身份
    questionnaire = db.query(Questionnaire).filter(Questionnaire.share_token == share_token).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="问卷不存在或链接无效")
    
    teacher = db.query(Teacher).filter(
        Teacher.id_number == auth.id_number,
        Teacher.phone == auth.phone
    ).first()
    
    # 确保teacher_ids是整数列表进行比较
    q_teacher_ids = [int(tid) for tid in questionnaire.teacher_ids if tid is not None] if questionnaire.teacher_ids else []
    if not teacher or teacher.id not in q_teacher_ids:
        raise HTTPException(status_code=401, detail="身份验证失败")
    
    # 查找回答
    response = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.questionnaire_id == questionnaire.id,
        QuestionnaireResponse.teacher_id == teacher.id
    ).first()
    
    if not response:
        raise HTTPException(status_code=404, detail="未找到您的问卷回答")
    
    # 更新确认状态
    response.confirmed_status = "confirmed" if confirm.confirmed else "rejected"
    response.confirmed_at = datetime.now()
    db.commit()
    
    return {
        "message": "确认成功" if confirm.confirmed else "已标记为信息有误",
        "confirmed_status": response.confirmed_status
    }

