"""
教师信息管理API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from app.database import get_db
from app.models import Teacher, SealRequest
from app.utils.validators import clean_teacher_data
from app.deps import require_admin

router = APIRouter(
    prefix="/api/teachers",
    tags=["教师管理"],
    dependencies=[Depends(require_admin)],
)


class TeacherCreate(BaseModel):
    name: str
    sex: Optional[str] = None
    id_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    title: Optional[str] = None
    extra_data: Optional[dict] = Field(default_factory=dict)


class TeacherUpdate(BaseModel):
    name: Optional[str] = None
    sex: Optional[str] = None
    id_number: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    title: Optional[str] = None
    extra_data: Optional[dict] = None


class TeacherResponse(BaseModel):
    id: int
    name: str
    sex: Optional[str]
    id_number: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    department: Optional[str]
    position: Optional[str]
    title: Optional[str]
    extra_data: dict
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/", response_model=List[TeacherResponse])
def get_teachers(
    skip: int = 0,
    limit: int = 10000,  # 增加默认限制，支持更多教师
    department: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取教师列表"""
    query = db.query(Teacher)
    if department:
        query = query.filter(Teacher.department == department)
    if search:
        # 支持按姓名、手机号、身份证号搜索
        search_filter = (
            Teacher.name.contains(search) |
            Teacher.phone.contains(search) |
            Teacher.id_number.contains(search)
        )
        query = query.filter(search_filter)
    teachers = query.offset(skip).limit(limit).all()
    # 不在 GET 列表时写库；如需修复历史数据请用单独脚本或导入流程
    return teachers


@router.get("/{teacher_id}", response_model=TeacherResponse)
def get_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """获取单个教师信息"""
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    return teacher


@router.post("/", response_model=TeacherResponse)
def create_teacher(teacher: TeacherCreate, db: Session = Depends(get_db)):
    """创建教师信息"""
    # 数据清洗
    cleaned_data = clean_teacher_data(teacher.dict())
    
    # 检查身份证号是否重复
    if cleaned_data.get('id_number'):
        existing = db.query(Teacher).filter(Teacher.id_number == cleaned_data['id_number']).first()
        if existing:
            raise HTTPException(status_code=400, detail="身份证号已存在")
    
    db_teacher = Teacher(**cleaned_data)
    db.add(db_teacher)
    db.commit()
    db.refresh(db_teacher)
    return db_teacher


@router.put("/{teacher_id}", response_model=TeacherResponse)
def update_teacher(teacher_id: int, teacher: TeacherUpdate, db: Session = Depends(get_db)):
    """更新教师信息"""
    db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not db_teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    
    update_data = teacher.dict(exclude_unset=True)
    if update_data:
        cleaned_data = clean_teacher_data(update_data)
        
        # 检查身份证号是否重复（排除当前教师）
        if 'id_number' in cleaned_data and cleaned_data.get('id_number'):
            existing = db.query(Teacher).filter(
                Teacher.id_number == cleaned_data['id_number'],
                Teacher.id != teacher_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="身份证号已被其他教师使用")
        
        for key, value in cleaned_data.items():
            setattr(db_teacher, key, value)
        db_teacher.updated_at = datetime.now()
        db.commit()
        db.refresh(db_teacher)
    
    return db_teacher


@router.delete("/{teacher_id}")
def delete_teacher(teacher_id: int, db: Session = Depends(get_db)):
    """删除教师信息"""
    from app.models import QuestionnaireResponse
    
    db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not db_teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    
    # 先删除关联的问卷回答与公章申请，避免外键约束错误
    responses = db.query(QuestionnaireResponse).filter(
        QuestionnaireResponse.teacher_id == teacher_id
    ).all()
    for response in responses:
        db.delete(response)

    seals = db.query(SealRequest).filter(SealRequest.teacher_id == teacher_id).all()
    for s in seals:
        db.delete(s)

    db.delete(db_teacher)
    db.commit()
    return {"message": "删除成功"}


class BatchDeleteRequest(BaseModel):
    teacher_ids: List[int]


@router.post("/batch-delete")
def delete_teachers_batch(request: BatchDeleteRequest, db: Session = Depends(get_db)):
    """批量删除教师"""
    from app.models import QuestionnaireResponse
    
    teacher_ids = request.teacher_ids
    if not teacher_ids:
        raise HTTPException(status_code=400, detail="请提供要删除的教师ID列表")
    
    deleted_count = 0
    failed_ids = []
    
    for teacher_id in teacher_ids:
        try:
            db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
            if not db_teacher:
                failed_ids.append({"id": teacher_id, "reason": "教师不存在"})
                continue
            
            responses = db.query(QuestionnaireResponse).filter(
                QuestionnaireResponse.teacher_id == teacher_id
            ).all()
            for response in responses:
                db.delete(response)

            for s in db.query(SealRequest).filter(SealRequest.teacher_id == teacher_id).all():
                db.delete(s)

            db.delete(db_teacher)
            deleted_count += 1
        except Exception as e:
            failed_ids.append({"id": teacher_id, "reason": str(e)})
    
    db.commit()
    
    return {
        "message": f"成功删除 {deleted_count} 个教师",
        "deleted_count": deleted_count,
        "failed": failed_ids
    }


@router.get("/export/csv")
def export_teachers_csv(db: Session = Depends(get_db)):
    """导出教师数据为CSV"""
    import csv
    import io
    from fastapi.responses import Response
    
    teachers = db.query(Teacher).all()
    
    # 创建CSV内容
    output = io.StringIO()
    writer = csv.writer(output)
    
    # 获取所有可能的字段（包括extra_data中的动态字段）
    all_fields = set(['id', 'name', 'sex', 'id_number', 'phone', 'email', 'department', 'position', 'title'])
    for teacher in teachers:
        if teacher.extra_data:
            all_fields.update(teacher.extra_data.keys())
    
    # 排序字段，基础字段在前，extra_data字段在后
    base_fields = ['id', 'name', 'sex', 'id_number', 'phone', 'email', 'department', 'position', 'title']
    extra_fields = sorted([f for f in all_fields if f not in base_fields])
    field_order = base_fields + extra_fields + ['created_at', 'updated_at']
    
    # 写入表头
    writer.writerow(field_order)
    
    # 写入数据
    for teacher in teachers:
        row = []
        for field in field_order:
            if field in base_fields:
                value = getattr(teacher, field, '')
                # 特殊处理手机号和身份证号：如果是浮点数格式，转换为整数字符串
                if field in ['phone', 'id_number'] and value:
                    if '.' in str(value):
                        try:
                            value = str(int(float(value)))
                        except (ValueError, TypeError):
                            pass
            elif field == 'created_at':
                value = teacher.created_at.strftime('%Y-%m-%d %H:%M:%S') if teacher.created_at else ''
            elif field == 'updated_at':
                value = teacher.updated_at.strftime('%Y-%m-%d %H:%M:%S') if teacher.updated_at else ''
            else:
                # extra_data字段
                value = teacher.extra_data.get(field, '') if teacher.extra_data else ''
            
            # 处理None值
            if value is None:
                value = ''
            row.append(str(value))
        writer.writerow(row)
    
    # 生成响应
    csv_content = output.getvalue()
    output.close()
    
    from datetime import datetime
    filename = f"teachers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content.encode('utf-8-sig'),  # 使用utf-8-sig以支持Excel正确显示中文
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
