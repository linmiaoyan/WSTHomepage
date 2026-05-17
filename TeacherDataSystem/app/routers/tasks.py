"""
填报任务API
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from pathlib import Path
from app.database import get_db
from app.models import Task, Template
from app.services.export_service import batch_export
from app.deps import require_admin, require_teacher_id
from app.utils.age_birth import prepare_extra_for_fill

router = APIRouter(prefix="/api/tasks", tags=["填报任务"])


class TaskCreate(BaseModel):
    name: str
    template_id: int
    teacher_ids: List[int]
    created_by: Optional[str] = None


class TaskResponse(BaseModel):
    id: int
    name: str
    template_id: int
    teacher_ids: List[int]
    status: str
    export_path: Optional[str]
    created_by: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("/", response_model=List[TaskResponse], dependencies=[Depends(require_admin)])
def get_tasks(db: Session = Depends(get_db)):
    """获取任务列表"""
    tasks = db.query(Task).all()
    return tasks


class TeacherQuery(BaseModel):
    id_number: str
    phone: str


@router.post("/query")
def query_teacher_tasks(query: TeacherQuery, db: Session = Depends(get_db)):
    """教师查询自己参与的任务（身份证+手机，无需登录）"""
    from app.models import Teacher

    teacher = db.query(Teacher).filter(
        Teacher.id_number == query.id_number,
        Teacher.phone == query.phone
    ).first()

    if not teacher:
        return {"teacher_id": None, "tasks": []}

    all_tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    tasks = []
    for task in all_tasks:
        if task.teacher_ids:
            task_teacher_ids = [int(tid) for tid in task.teacher_ids if tid is not None]
            if teacher.id in task_teacher_ids:
                tasks.append(task)

    return {
        "teacher_id": teacher.id,
        "tasks": [
            {
                "id": task.id,
                "name": task.name,
                "status": task.status,
                "created_at": task.created_at,
                "completed_at": task.completed_at
            }
            for task in tasks
        ]
    }


@router.get("/my-tasks")
def get_my_tasks(
    request: Request,
    db: Session = Depends(get_db)
):
    """获取当前登录教师的任务列表（需要登录）"""
    from app.models import Teacher

    teacher_id = require_teacher_id(request)

    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")

    all_tasks = db.query(Task).order_by(Task.created_at.desc()).all()
    tasks = []
    for task in all_tasks:
        if task.teacher_ids:
            task_teacher_ids = [int(tid) for tid in task.teacher_ids if tid is not None]
            if teacher_id in task_teacher_ids:
                tasks.append(task)

    return {
        "teacher_id": teacher_id,
        "teacher_name": teacher.name,
        "tasks": [
            {
                "id": task.id,
                "name": task.name,
                "status": task.status,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "template_id": task.template_id
            }
            for task in tasks
        ]
    }


@router.get("/{task_id}", response_model=TaskResponse, dependencies=[Depends(require_admin)])
def get_task(task_id: int, db: Session = Depends(get_db)):
    """获取单个任务"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.get("/{task_id}/detail", dependencies=[Depends(require_admin)])
def get_task_detail(task_id: int, db: Session = Depends(get_db)):
    """获取任务详情（包括模板信息和未知字段）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    template = db.query(Template).filter(Template.id == task.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 获取所有可用字段
    from app.routers.templates import get_available_fields
    available_fields_data = get_available_fields()
    available_field_names = set()
    for field in available_fields_data.get("all_fields", []):
        available_field_names.add(field.get("name", ""))
    
    # 获取模板中使用的占位符
    placeholder_positions = template.placeholder_positions or []
    used_field_names = set([pos.get("field_name") for pos in placeholder_positions if pos.get("field_name")])
    
    # 找出额外占位符（标记为is_extra的占位符）
    extra_placeholders = [pos.get("field_name") for pos in placeholder_positions if pos.get("is_extra")]
    
    # 找出未知字段（不在可用字段列表中的字段，且不是额外占位符）
    unknown_fields = used_field_names - available_field_names - set(extra_placeholders)
    
    # 检查是否有关联的问卷（通过任务ID或教师ID匹配）
    from app.models import Questionnaire
    questionnaire = None
    if task.teacher_ids:
        # 确保teacher_ids是整数列表
        task_teacher_ids = [int(tid) for tid in task.teacher_ids if tid is not None]
        
        # 查找包含这些教师的问卷
        questionnaires = db.query(Questionnaire).all()
        for q in questionnaires:
            if q.teacher_ids:
                # 确保问卷的teacher_ids也是整数列表
                q_teacher_ids = [int(tid) for tid in q.teacher_ids if tid is not None]
                # 检查是否有交集
                if set(q_teacher_ids) & set(task_teacher_ids):
                    questionnaire = q
                    break
    
    return {
        "task": {
            "id": task.id,
            "name": task.name,
            "template_id": task.template_id,
            "teacher_ids": task.teacher_ids,
            "status": task.status,
            "created_at": task.created_at,
            "completed_at": task.completed_at
        },
        "template": {
            "id": template.id,
            "name": template.name,
            "file_type": template.file_type,
            "placeholder_positions": template.placeholder_positions or []  # 包含占位符信息，包括is_signature标记
        },
        "unknown_fields": list(unknown_fields),
        "extra_placeholders": extra_placeholders,  # 额外占位符列表
        "has_extra_placeholders": len(extra_placeholders) > 0,  # 是否有额外占位符
        "has_questionnaire": questionnaire is not None,
        "questionnaire_id": questionnaire.id if questionnaire else None
    }


@router.post("/", response_model=TaskResponse, dependencies=[Depends(require_admin)])
def create_task(task: TaskCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """创建填报任务并开始批量导出"""
    # 检查模板是否存在
    template = db.query(Template).filter(Template.id == task.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 检查是否有额外占位符
    placeholder_positions = template.placeholder_positions or []
    extra_placeholders = [pos.get("field_name") for pos in placeholder_positions if pos.get("is_extra")]
    has_extra_placeholders = len(extra_placeholders) > 0
    
    # 创建任务记录
    db_task = Task(
        name=task.name,
        template_id=task.template_id,
        teacher_ids=task.teacher_ids,
        created_by=task.created_by,
        status="pending" if has_extra_placeholders else "processing"  # 有额外占位符时，状态为pending，等待问卷
    )
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    
    # 如果有额外占位符，不直接导出，等待问卷完成
    if has_extra_placeholders:
        # 不执行导出任务，返回任务信息，提示需要发起问卷
        return db_task
    
    # 后台执行导出任务
    def export_task():
        from app.database import SessionLocal
        db_session = SessionLocal()
        try:
            export_path = batch_export(
                template_id=task.template_id,
                teacher_ids=task.teacher_ids,
                db=db_session,
                task_name=task.name
            )
            # 更新任务状态
            task_record = db_session.query(Task).filter(Task.id == db_task.id).first()
            if task_record:
                task_record.export_path = export_path
                task_record.status = "completed"
                task_record.completed_at = datetime.now()
                db_session.commit()
        except Exception as e:
            task_record = db_session.query(Task).filter(Task.id == db_task.id).first()
            if task_record:
                task_record.status = "failed"
                db_session.commit()
            print(f"导出任务失败: {e}")
        finally:
            db_session.close()
    
    background_tasks.add_task(export_task)
    
    return db_task


@router.post("/{task_id}/complete-export", dependencies=[Depends(require_admin)])
def complete_task_export(task_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """完成任务导出（当所有问卷填写完成后，手动触发导出）"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if task.status != "pending":
        raise HTTPException(status_code=400, detail="任务状态不正确，只有pending状态的任务才能完成导出")
    
    # 检查是否所有教师都已填写问卷
    from app.models import Questionnaire, QuestionnaireResponse
    questionnaire = None
    if task.teacher_ids:
        task_teacher_ids = [int(tid) for tid in task.teacher_ids if tid is not None]
        questionnaires = db.query(Questionnaire).all()
        for q in questionnaires:
            if q.teacher_ids:
                q_teacher_ids = [int(tid) for tid in q.teacher_ids if tid is not None]
                if set(q_teacher_ids) & set(task_teacher_ids):
                    questionnaire = q
                    break
    
    # 检查哪些教师已填写或确认（不再强制要求所有教师都填写）
    submitted_teacher_ids = []
    missing_teachers = set()
    
    if questionnaire:
        responses = db.query(QuestionnaireResponse).filter(
            QuestionnaireResponse.questionnaire_id == questionnaire.id
        ).all()
        
        # 已提交或已确认的教师ID
        response_teacher_ids = set([
            r.teacher_id for r in responses 
            if r.submitted_at or r.confirmed_status == 'confirmed'
        ])
        task_teacher_ids_set = set([int(tid) for tid in task.teacher_ids if tid is not None])
        
        # 只导出已填写或已确认教师的文件（如果没有，则导出空文件）
        submitted_teacher_ids = list(response_teacher_ids & task_teacher_ids_set)
        missing_teachers = task_teacher_ids_set - response_teacher_ids
        
        if len(submitted_teacher_ids) == 0:
            print(f"[导出任务] 警告：没有教师完成填写或确认，将导出空的ZIP文件")
            submitted_teacher_ids = []  # 空列表，导出时将生成空的ZIP文件
        
        if missing_teachers and len(submitted_teacher_ids) > 0:
            print(f"[导出任务] 警告：有 {len(missing_teachers)} 位教师未完成填写或确认，将只导出已填写教师的文件")
    else:
        # 如果没有问卷，直接导出空文件
        print(f"[导出任务] 警告：未找到关联的问卷，将导出空的ZIP文件")
        submitted_teacher_ids = []
    
    # 更新任务状态为processing，开始导出
    task.status = "processing"
    db.commit()
    
    # 后台执行导出任务
    def export_task():
        from app.database import SessionLocal
        import traceback
        db_session = SessionLocal()
        try:
            print(f"[导出任务] 开始导出任务 {task.id}: {task.name}")
            if len(submitted_teacher_ids) == 0:
                print(f"[导出任务] 没有教师完成填写，将创建空的ZIP文件")
                # 创建空的ZIP文件
                from datetime import datetime
                import zipfile
                from pathlib import Path
                import config
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                task_name_clean = task.name.replace(" ", "_") if task.name else "export"
                zip_filename = f"{task_name_clean}_{timestamp}.zip"
                zip_path = config.EXPORT_DIR / zip_filename
                
                # 创建空的ZIP文件
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    # 添加一个说明文件
                    zipf.writestr("README.txt", f"此任务没有教师完成填写。\n任务名称: {task.name}\n导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                export_path = str(zip_path)
            else:
                print(f"[导出任务] 将导出 {len(submitted_teacher_ids)} 位已填写教师的文件")
                # 使用已填写教师的ID列表，而不是所有教师
                export_path = batch_export(
                    template_id=task.template_id,
                    teacher_ids=submitted_teacher_ids,  # 只导出已填写教师的文件
                    db=db_session,
                    task_name=task.name
                )
            print(f"[导出任务] 导出完成，文件路径: {export_path}")
            print(f"[导出任务] 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 更新任务状态
            print(f"[导出任务] 准备更新任务状态...")
            task_record = db_session.query(Task).filter(Task.id == task.id).first()
            if task_record:
                task_record.export_path = export_path
                task_record.status = "completed"
                task_record.completed_at = datetime.now()
                db_session.commit()
                print(f"[导出任务] ✓ 任务状态已更新为completed")
                print(f"[导出任务] 导出文件路径: {export_path}")
            else:
                print(f"[导出任务] ⚠ 警告：找不到任务记录 {task.id}")
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"[导出任务] 导出任务失败: {e}\n{error_trace}")
            
            task_record = db_session.query(Task).filter(Task.id == task.id).first()
            if task_record:
                task_record.status = "failed"
                db_session.commit()
                print(f"[导出任务] 任务状态已更新为failed，错误信息: {str(e)}")
                print(f"[导出任务] 错误堆栈: {error_trace}")
        finally:
            db_session.close()
    
    background_tasks.add_task(export_task)
    
    return {"message": "导出任务已启动，正在后台处理中"}


@router.get("/{task_id}/download", dependencies=[Depends(require_admin)])
def download_task_export(task_id: int, db: Session = Depends(get_db)):
    """下载任务导出文件"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    if not task.export_path or task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成或导出文件不存在")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        task.export_path,
        filename=Path(task.export_path).name,
        media_type="application/zip"
    )


@router.delete("/{task_id}", dependencies=[Depends(require_admin)])
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除任务"""
    import os
    
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        
        # 删除导出文件（如果存在）
        if task.export_path:
            export_path = Path(task.export_path)
            if export_path.exists():
                try:
                    os.remove(export_path)
                except Exception as e:
                    # 记录错误但不阻止删除任务记录
                    print(f"删除导出文件失败: {e}")
        
        db.delete(task)
        db.commit()
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除任务失败: {str(e)}")


@router.get("/{task_id}/download-teacher/{teacher_id}")
def download_teacher_file(
    task_id: int,
    teacher_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """下载单个教师的文件（必须登录教师账号，且路径中的教师ID须与登录一致）"""
    from fastapi.responses import FileResponse
    from app.models import Teacher, Template
    from app.services.template_processor import process_template
    import tempfile

    verified_teacher_id = require_teacher_id(request)
    if int(verified_teacher_id) != int(teacher_id):
        raise HTTPException(status_code=403, detail="您无权访问此文件")

    # 获取任务
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查教师是否在任务中
    # 确保teacher_ids是整数列表进行比较
    task_teacher_ids = [int(tid) for tid in task.teacher_ids if tid is not None] if task.teacher_ids else []
    if teacher_id not in task_teacher_ids:
        raise HTTPException(status_code=403, detail="您无权访问此文件")
    
    # 获取教师信息
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="教师不存在")
    
    # 获取模板
    template = db.query(Template).filter(Template.id == task.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    
    # 准备数据
    # 修复手机号格式（如果是浮点数，转换为整数字符串）
    phone = teacher.phone
    if phone and '.' in str(phone):
        try:
            phone = str(int(float(phone)))
        except (ValueError, TypeError):
            pass
    
    refd = datetime.now().date()
    legacy = getattr(teacher, "updated_at", None) or getattr(teacher, "created_at", None)
    teacher_data = {
        'name': teacher.name,
        'sex': teacher.sex,
        'id_number': teacher.id_number,
        'phone': phone,
        'email': teacher.email,
        'department': teacher.department,
        'position': teacher.position,
        'title': teacher.title,
        'extra_data': prepare_extra_for_fill(
            teacher.extra_data or {}, refd, legacy_as_of=legacy
        ),
    }
    
    # 生成临时文件
    temp_dir = Path(tempfile.gettempdir())
    ext = Path(template.file_path).suffix
    output_filename = f"{teacher.name}_{teacher.id}{ext}"
    output_path = temp_dir / output_filename
    
    # 填充模板
    try:
        placeholder_positions = None
        if template.file_type == '.pdf':
            placeholder_positions = template.placeholder_positions or []
        
        process_template(
            template.file_path,
            teacher_data,
            str(output_path),
            placeholder_positions=placeholder_positions
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成文件失败: {str(e)}")
    
    # 返回文件
    return FileResponse(
        output_path,
        filename=output_filename,
        media_type="application/pdf" if ext == '.pdf' else "application/octet-stream"
    )