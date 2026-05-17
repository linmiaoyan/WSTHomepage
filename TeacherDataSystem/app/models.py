"""
数据库模型定义
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Teacher(Base):
    """教师信息表"""
    __tablename__ = "teachers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="姓名")
    sex = Column(String(10), comment="性别")
    id_number = Column(String(18), unique=True, comment="身份证号")
    phone = Column(String(20), comment="手机号")
    email = Column(String(100), comment="邮箱")
    department = Column(String(100), comment="部门")
    position = Column(String(100), comment="职位")
    title = Column(String(100), comment="职称")
    # 使用JSON字段存储其他动态字段
    extra_data = Column(JSON, default={}, comment="扩展数据（JSON格式）")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # 关联关系
    # 注意：Task和Teacher之间通过teacher_ids JSON字段关联，不是外键关系
    questionnaire_responses = relationship("QuestionnaireResponse", back_populates="teacher")
    seal_requests = relationship("SealRequest", back_populates="teacher")


class Template(Base):
    """模板表"""
    __tablename__ = "templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="模板名称")
    description = Column(Text, comment="模板描述")
    file_path = Column(String(500), nullable=False, comment="文件路径")
    file_type = Column(String(20), comment="文件类型（pdf）")
    placeholders = Column(JSON, default=[], comment="占位符列表（如['name', 'sex']）")
    placeholder_positions = Column(JSON, default=[], comment="占位符位置信息（[{field_name, page, x, y, font_size}]）")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.now)
    
    # 关联关系
    tasks = relationship("Task", back_populates="template")


class Task(Base):
    """填报任务表"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="任务名称")
    template_id = Column(Integer, ForeignKey("templates.id"), nullable=False)
    teacher_ids = Column(JSON, default=[], comment="需要填写的教师ID列表")
    status = Column(String(20), default="pending", comment="状态：pending/completed")
    export_path = Column(String(500), comment="导出文件路径（ZIP）")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, comment="完成时间")
    
    # 关联关系
    template = relationship("Template", back_populates="tasks")
    # 注意：Task和Teacher之间通过teacher_ids JSON字段关联，不是外键关系


class Questionnaire(Base):
    """问卷表"""
    __tablename__ = "questionnaires"
    
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, comment="问卷标题")
    description = Column(Text, comment="问卷描述")
    fields = Column(JSON, nullable=False, comment="字段定义（[{name, type, required, options}]）")
    teacher_ids = Column(JSON, default=[], comment="需要填写的教师ID列表")
    status = Column(String(20), default="active", comment="状态：active/completed/closed")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.now)
    deadline = Column(DateTime, comment="截止时间")
    share_token = Column(String(100), unique=True, index=True, comment="分享链接token")
    
    # 关联关系
    responses = relationship("QuestionnaireResponse", back_populates="questionnaire")


class QuestionnaireResponse(Base):
    """问卷回答表"""
    __tablename__ = "questionnaire_responses"
    
    id = Column(Integer, primary_key=True, index=True)
    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)
    answers = Column(JSON, nullable=False, comment="回答内容（JSON格式）")
    status = Column(String(20), default="pending", comment="审核状态：pending/approved/rejected")
    confirmed_status = Column(String(20), default="pending", comment="确认状态：pending/confirmed/rejected")
    confirmed_at = Column(DateTime, comment="确认时间")
    reviewed_by = Column(String(100), comment="审核人")
    reviewed_at = Column(DateTime, comment="审核时间")
    review_comment = Column(Text, comment="审核意见")
    submitted_at = Column(DateTime, default=datetime.now)
    
    # 关联关系
    questionnaire = relationship("Questionnaire", back_populates="responses")
    teacher = relationship("Teacher", back_populates="questionnaire_responses")


class SealRequest(Base):
    """公章审批申请表（教师发起，管理员审批）"""
    __tablename__ = "seal_requests"

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False, index=True)
    pdf_path = Column(String(500), nullable=False, comment="上传的PDF文件路径")
    stamp_positions = Column(JSON, default=[], nullable=False, comment="盖章位置列表 [{page,x,y}]，坐标为PDF点坐标")
    remark = Column(Text, nullable=True, comment="教师备注/说明")
    status = Column(String(20), default="pending", comment="状态：pending/approved/rejected")
    created_at = Column(DateTime, default=datetime.now)

    reviewed_by = Column(String(100), nullable=True, comment="审批人（管理员token或名称）")
    reviewed_at = Column(DateTime, nullable=True)
    review_comment = Column(Text, nullable=True, comment="审批意见")

    teacher = relationship("Teacher", back_populates="seal_requests")

