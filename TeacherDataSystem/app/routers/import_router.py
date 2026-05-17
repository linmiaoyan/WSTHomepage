"""
数据导入API
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
from pathlib import Path
import io
from app.database import get_db
from app.models import Teacher
from app.utils.validators import clean_teacher_data
from app.deps import require_admin
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
import config

router = APIRouter(
    prefix="/api/import",
    tags=["数据导入"],
    dependencies=[Depends(require_admin)],
)


class ImportResult(BaseModel):
    success_count: int
    failed_count: int
    errors: List[str]


# 字段映射表：Excel列名 -> 数据库字段名
FIELD_MAPPING = {
    '姓名': 'name',
    '性别': 'sex',
    '身份证号': 'id_number',
    '联系电话': 'phone',
    '教育网': 'email',  # 可能教育网是邮箱
    '现聘用岗位2': 'position',
    '行政职务': 'title',
    # 其他字段会存储到extra_data中
}

# 需要存储到extra_data的字段
EXTRA_FIELDS = [
    '序号', '年龄', '现专技岗位时间', '现聘用时间', '原岗位类别', '原聘用岗位',
    '原聘用时间', '出生年月', '出生年月日', '参加工作时间', '工龄起算时间', '工龄',
    '教龄', '学历', '学位', '毕业学校', '所学专业', '现从事专业', '专业技术资格',
    '晋升时间', '取得时间', '政治面貌', '入党(团)时间', '进入科高时间', '本单位起薪时间',
    '民族', '籍贯', '原编制', '当前编制', '职务', '教育网'
]


def parse_excel_to_teachers(file_content: bytes) -> List[Dict[str, Any]]:
    """
    解析Excel文件为教师数据列表
    """
    try:
        # 读取Excel文件
        df = pd.read_excel(io.BytesIO(file_content), engine='openpyxl')
        
        # 转换为字典列表
        teachers_data = []
        for index, row in df.iterrows():
            teacher_data = {}
            extra_data = {}
            
            # 处理每一行数据
            for col_name, value in row.items():
                # 跳过空值
                if pd.isna(value):
                    continue
                
                col_name_str = str(col_name).strip()
                
                # 映射到主字段
                if col_name_str in FIELD_MAPPING:
                    db_field = FIELD_MAPPING[col_name_str]
                    # 处理日期类型
                    if isinstance(value, pd.Timestamp):
                        teacher_data[db_field] = value.strftime('%Y-%m-%d')
                    elif isinstance(value, (int, float)) and pd.isna(value):
                        pass  # 跳过NaN数值
                    else:
                        # 特殊处理手机号和身份证号：如果是数字类型，先转为整数再转为字符串，避免浮点数
                        if db_field in ['phone', 'id_number']:
                            if isinstance(value, (int, float)):
                                # 如果是整数或浮点数，先转为整数（去除小数点）再转为字符串
                                teacher_data[db_field] = str(int(value))
                            else:
                                teacher_data[db_field] = str(value).strip()
                        else:
                            teacher_data[db_field] = str(value).strip()
                # 存储到extra_data（所有未映射的字段）
                else:
                    # 处理日期类型
                    if isinstance(value, pd.Timestamp):
                        extra_data[col_name_str] = value.strftime('%Y-%m-%d')
                    elif isinstance(value, (int, float)) and pd.isna(value):
                        pass  # 跳过NaN数值
                    else:
                        extra_data[col_name_str] = str(value).strip()
            
            # 如果没有姓名，跳过这一行
            if not teacher_data.get('name'):
                continue
            
            # 添加extra_data
            if extra_data:
                teacher_data['extra_data'] = extra_data
            
            teachers_data.append(teacher_data)
        
        return teachers_data
    except Exception as e:
        raise ValueError(f"解析Excel文件失败: {str(e)}")


@router.post("/excel", response_model=ImportResult)
async def import_excel(
    file: UploadFile = File(...),
    skip_duplicates: bool = True,
    db: Session = Depends(get_db)
):
    """
    导入Excel文件
    
    Args:
        file: Excel文件
        skip_duplicates: 是否跳过重复记录（根据身份证号判断）
    """
    # 检查文件类型
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="只支持Excel文件（.xlsx, .xls）")
    
    # 读取文件内容
    file_content = await file.read()
    
    try:
        # 解析Excel
        teachers_data = parse_excel_to_teachers(file_content)
        
        if not teachers_data:
            raise HTTPException(status_code=400, detail="Excel文件中没有有效数据")
        
        success_count = 0
        failed_count = 0
        errors = []
        
        # 导入数据
        for idx, teacher_data in enumerate(teachers_data, 1):
            try:
                # 数据清洗
                cleaned_data = clean_teacher_data(teacher_data)
                
                # 检查是否已存在（根据身份证号）
                if skip_duplicates and cleaned_data.get('id_number'):
                    existing = db.query(Teacher).filter(
                        Teacher.id_number == cleaned_data['id_number']
                    ).first()
                    if existing:
                        errors.append(f"第{idx}行：身份证号 {cleaned_data['id_number']} 已存在，已跳过")
                        failed_count += 1
                        continue
                
                # 创建教师记录
                db_teacher = Teacher(**cleaned_data)
                db.add(db_teacher)
                success_count += 1
                
            except Exception as e:
                failed_count += 1
                teacher_name = teacher_data.get('name', '未知')
                errors.append(f"第{idx}行（{teacher_name}）：{str(e)}")
        
        # 提交事务
        db.commit()
        
        return ImportResult(
            success_count=success_count,
            failed_count=failed_count,
            errors=errors[:50]  # 最多返回50个错误
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.get("/template")
async def download_template():
    """
    下载导入模板Excel文件
    """
    # 创建模板DataFrame
    template_data = {
        '序号': [1],
        '姓名': ['示例'],
        '性别': ['男'],
        '身份证号': ['110101199001011234'],
        '年龄': [35],
        '现聘用岗位2': ['高级教师'],
        '现专技岗位时间': ['2020-01-01'],
        '现聘用时间': ['2020-01-01'],
        '原岗位类别': ['专业技术'],
        '原聘用岗位': ['中级教师'],
        '原聘用时间': ['2015-01-01'],
        '出生年月': ['1990-01'],
        '出生年月日': ['1990-01-01'],
        '参加工作时间': ['2012-07-01'],
        '工龄起算时间': ['2012-07-01'],
        '工龄': [12],
        '教龄': [10],
        '学历': ['本科'],
        '学位': ['学士'],
        '毕业学校': ['示例大学'],
        '所学专业': ['教育学'],
        '现从事专业': ['数学'],
        '专业技术资格': ['高级教师'],
        '晋升时间': ['2020-01-01'],
        '行政职务': ['无'],
        '取得时间': ['2020-01-01'],
        '政治面貌': ['中共党员'],
        '入党(团)时间': ['2010-01-01'],
        '进入科高时间': ['2015-01-01'],
        '本单位起薪时间': ['2012-07-01'],
        '联系电话': ['13800138000'],
        '教育网': ['example@edu.cn'],
        '民族': ['汉族'],
        '籍贯': ['北京'],
        '原编制': ['在编'],
        '当前编制': ['在编'],
        '职务': ['教师']
    }
    
    df = pd.DataFrame(template_data)
    
    # 转换为Excel字节流
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='教师信息')
    
    output.seek(0)
    
    from fastapi.responses import Response
    return Response(
        content=output.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=教师信息导入模板.xlsx"
        }
    )

