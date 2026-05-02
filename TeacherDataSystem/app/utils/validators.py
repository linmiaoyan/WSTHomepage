"""
数据验证工具
"""
import re
from datetime import datetime
from typing import Dict, Any, Optional

from app.utils.age_birth import normalize_extra_age_birth


def validate_id_number(id_number: str) -> bool:
    """验证身份证号格式"""
    if not id_number:
        return False
    # 简单的身份证号验证（18位或15位）
    pattern = r'^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$|^[1-9]\d{7}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}$'
    return bool(re.match(pattern, id_number))


def validate_phone(phone: str) -> bool:
    """验证手机号格式"""
    if not phone:
        return False
    pattern = r'^1[3-9]\d{9}$'
    return bool(re.match(pattern, phone))


def validate_email(email: str) -> bool:
    """验证邮箱格式"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def clean_teacher_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    清洗教师数据
    这里可以集成大模型进行智能清洗和验证
    """
    cleaned = {}
    
    # 基础字段清洗
    if 'name' in data:
        cleaned['name'] = data['name'].strip() if data['name'] else None
    
    if 'phone' in data:
        phone = data['phone']
        # 确保手机号始终为字符串
        if phone is not None:
            # 如果是数字类型（int或float），先转为整数再转为字符串，避免浮点数显示
            if isinstance(phone, (int, float)):
                phone = str(int(phone))
            else:
                phone = str(phone).strip()
            # 移除可能的小数点和尾随零
            if '.' in phone:
                phone = phone.split('.')[0]
            if phone and not validate_phone(phone):
                # 可以在这里调用大模型进行智能修正
                # if config.USE_LLM:
                #     phone = llm_correct_phone(phone)
                pass
        cleaned['phone'] = phone if phone else None
    
    if 'email' in data:
        email = data['email'].strip() if data['email'] else None
        if email and not validate_email(email):
            # 可以在这里调用大模型进行智能修正
            pass
        cleaned['email'] = email
    
    if 'id_number' in data:
        id_number = data['id_number'].strip() if data['id_number'] else None
        if id_number and not validate_id_number(id_number):
            # 可以在这里调用大模型进行智能修正
            pass
        cleaned['id_number'] = id_number
    
    # 其他字段
    for key, value in data.items():
        if key not in ['name', 'phone', 'email', 'id_number']:
            if isinstance(value, str):
                cleaned[key] = value.strip()
            else:
                cleaned[key] = value

    ex = cleaned.get("extra_data")
    if isinstance(ex, dict):
        normalize_extra_age_birth(ex, datetime.now())

    return cleaned


# ========== 大模型集成部分（可选） ==========
# 以下函数可以集成大模型API来增强数据验证和清洗能力

def llm_validate_and_correct(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    使用大模型验证和修正数据
    需要配置LLM_API_KEY和LLM_API_URL
    """
    # TODO: 集成大模型API
    # 示例：
    # import openai
    # prompt = f"请验证并修正以下教师数据：{data}"
    # response = openai.ChatCompletion.create(...)
    # return corrected_data
    return data


def llm_extract_placeholders(file_content: bytes, file_type: str) -> list:
    """
    使用大模型自动识别文件中的占位符位置
    需要视觉-语言模型（如GPT-4V）
    """
    # TODO: 集成视觉-语言模型
    # 示例：
    # import openai
    # response = openai.ChatCompletion.create(
    #     model="gpt-4-vision-preview",
    #     messages=[{
    #         "role": "user",
    #         "content": [
    #             {"type": "text", "text": "识别这个文档中需要填充的位置"},
    #             {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_content}"}}
    #         ]
    #     }]
    # )
    return []

