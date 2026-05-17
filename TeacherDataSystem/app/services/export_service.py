"""
批量导出服务
"""
import os
import shutil
import zipfile
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Teacher, Template
from app.services.template_processor import process_template
from app.utils.age_birth import prepare_extra_for_fill
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config


def batch_export(template_id: int, teacher_ids: List[int], db: Session, task_name: str = None) -> str:
    """
    批量导出填好的表格
    
    Args:
        template_id: 模板ID
        teacher_ids: 教师ID列表
        db: 数据库会话
        task_name: 任务名称（用于生成文件名）
    
    Returns:
        导出文件的ZIP路径
    """
    # 获取模板
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise ValueError("模板不存在")
    
    # 获取教师数据
    teachers = db.query(Teacher).filter(Teacher.id.in_(teacher_ids)).all()
    if not teachers:
        raise ValueError("没有找到教师数据")
    
    # 创建临时目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_name_clean = task_name.replace(" ", "_") if task_name else "export"
    temp_dir = config.EXPORT_DIR / f"{task_name_clean}_{timestamp}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # 处理每个教师的表格
    total_teachers = len(teachers)
    for index, teacher in enumerate(teachers, 1):
        print(f"[批量导出] 处理教师 {index}/{total_teachers}: {teacher.name} (ID: {teacher.id})")
        try:
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
            
            # 检查是否有签名字段（base64图片）
            has_signature = False
            if teacher_data.get('extra_data'):
                for key, value in teacher_data['extra_data'].items():
                    if isinstance(value, str) and value.startswith('data:image'):
                        has_signature = True
                        print(f"[批量导出] 检测到签名字段: {key}, 数据长度: {len(value)}")
                        break
            
            # 生成输出文件名
            ext = Path(template.file_path).suffix
            output_filename = f"{teacher.name}_{teacher.id}{ext}"
            output_path = temp_dir / output_filename
            
            # 填充模板
            print(f"[批量导出] 开始处理模板: {template.file_path}")
            print(f"[批量导出] 教师数据: 姓名={teacher.name}, ID={teacher.id}")
            # 如果是PDF，需要传递占位符位置信息
            placeholder_positions = None
            if template.file_type == '.pdf':
                placeholder_positions = template.placeholder_positions or []
                print(f"[批量导出] PDF模板，占位符数量: {len(placeholder_positions)}")
                if placeholder_positions:
                    print(f"[批量导出] 占位符示例: {placeholder_positions[0] if len(placeholder_positions) > 0 else '无'}")
            
            print(f"[批量导出] 调用 process_template...")
            process_template(
                template.file_path, 
                teacher_data, 
                str(output_path),
                placeholder_positions=placeholder_positions
            )
            print(f"[批量导出] ✓ 教师 {teacher.name} 的表格处理完成: {output_path}")
        except Exception as e:
            print(f"[批量导出] ❌ 处理教师 {teacher.name} (ID: {teacher.id}) 的表格时出错: {e}")
            import traceback
            error_trace = traceback.format_exc()
            print(f"[批量导出] 错误堆栈:\n{error_trace}")
            continue
    
    # 打包成ZIP
    print(f"[批量导出] 开始打包ZIP文件...")
    zip_filename = f"{task_name_clean}_{timestamp}.zip"
    zip_path = config.EXPORT_DIR / zip_filename
    
    file_count = 0
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in temp_dir.iterdir():
            if file_path.is_file():
                zipf.write(file_path, file_path.name)
                file_count += 1
                print(f"[批量导出] 添加到ZIP: {file_path.name}")
    
    print(f"[批量导出] ZIP打包完成: {zip_path}, 包含 {file_count} 个文件")
    
    # 清理临时目录
    print(f"[批量导出] 清理临时目录: {temp_dir}")
    shutil.rmtree(temp_dir)
    print(f"[批量导出] 临时目录已清理")
    
    print(f"[批量导出] ✓ 批量导出完成，ZIP文件: {zip_path}")
    return str(zip_path)

