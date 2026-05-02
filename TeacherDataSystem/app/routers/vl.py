"""
VL 辅助：方案B（优化人机协同的数据选择）
说明：
- 不做“自动定位占位符坐标”
- 而是在用户点击某个空白位置后，裁剪附近区域图像
- 调用 QuickJudge 的视觉接口，让模型输出“最可能对应的字段名候选”
"""

from __future__ import annotations

import json
import re
import uuid
import urllib.request
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Template

import config


router = APIRouter(prefix="/api/vl", tags=["VL辅助（方案B）"], dependencies=[Depends(require_admin)])


class SuggestFieldsRequest(BaseModel):
    template_id: int
    page: int  # 0-based
    x: float  # pdf坐标（point），原点左下，y向上
    y: float  # pdf坐标（point），原点左下，y向上


class SuggestFieldsResponse(BaseModel):
    suggestions: List[Dict[str, Any]]  # [{field_name, confidence}, ...]


def _json_from_text_loose(text: str) -> Optional[dict]:
    """
    从模型输出文本中提取第一个 JSON 对象（尽量让模型只输出 JSON）。
    """
    if not text:
        return None
    text = text.strip()
    if not text:
        return None

    # 优先：整个文本就是 JSON
    if text.startswith("{") and text.endswith("}"):
        try:
            return json.loads(text)
        except Exception:
            pass

    # 次优：找最大括号对
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = text[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


def _get_available_field_names() -> List[str]:
    """
    TeacherDataSystem 内置可插入字段集合：给 VL 做候选约束。
    """
    from app.routers.templates import get_available_fields

    data = get_available_fields()
    all_fields = data.get("all_fields", [])
    names: List[str] = []
    for f in all_fields:
        n = f.get("name")
        if n:
            names.append(str(n))
    # 去重但保持顺序
    seen = set()
    out: List[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _render_pdf_page_crop_to_png(
    pdf_path: str,
    page_index: int,
    x_pdf: float,
    y_pdf: float,
    crop_w_pt: float = 180.0,
    crop_h_pt: float = 90.0,
    render_scale: float = 2.0,
) -> bytes:
    """
    将 PDF 页渲染成图片，并在 (x_pdf, y_pdf) 附近裁剪出一个小区域。
    - 输入坐标：PDF 点坐标（左下为原点，y向上）
    - 输出：PNG bytes（像素空间）
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise HTTPException(status_code=500, detail="缺少 PyMuPDF：pip install pymupdf") from e

    doc = fitz.open(pdf_path)
    try:
        if page_index < 0 or page_index >= len(doc):
            raise ValueError("page 越界")
        page = doc.load_page(page_index)

        page_rect = page.rect
        page_w_pt = float(page_rect.width)
        page_h_pt = float(page_rect.height)

        # PDF->fitz clip：fitz 使用 y 向下（顶部为 0），而我们的 y_pdf 是向上
        y_top = page_h_pt - float(y_pdf)

        x_pdf = float(x_pdf)
        crop_w_pt = float(crop_w_pt)
        crop_h_pt = float(crop_h_pt)

        x0 = max(0.0, x_pdf - crop_w_pt / 2.0)
        x1 = min(page_w_pt, x_pdf + crop_w_pt / 2.0)
        y0 = max(0.0, y_top - crop_h_pt / 2.0)
        y1 = min(page_h_pt, y_top + crop_h_pt / 2.0)

        clip = fitz.Rect(x0, y0, x1, y1)
        matrix = fitz.Matrix(render_scale, render_scale)
        pix = page.get_pixmap(matrix=matrix, clip=clip, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def _call_quickjudge_for_field_suggestions(
    quickjudge_files: List[str],
    field_names: List[str],
) -> List[Dict[str, Any]]:
    """
    调用 QuickJudge：让模型“看图->输出字段名候选”。
    """
    # 让模型输出 JSON（尽量纯 JSON，便于解析）
    # 注意：QuickJudge vision_grade 的提示词结构固定包含【识别文本】与【批阅报告】两段。
    # 我们把真正的结构化输出放在【批阅报告】里，并让【识别文本】尽量不干扰解析（只输出占位符）。
    field_list_str = ", ".join(field_names)
    prompt_template = (
        "你是字段映射助手。"
        "现在用户点击了一个模板中需要填值的位置（附近截图）。"
        "请识别该位置对应的“字段含义”（例如：姓名/身份证号/手机号/部门/职称...），"
        "并从候选字段列表中选择最匹配的 3-5 个 field_name。"
        "候选 field_name 只能从下面列表选择：[" + field_list_str + "]。"
        "输出要求：\n"
        "【识别文本】输出：{ \"hint\": \"ok\" }\n"
        "【批阅报告】只输出合法 JSON，格式："
        "{ \"candidates\": [ {\"field_name\": \"name\", \"confidence\": 0.9}, ... ] }\n"
        "不要输出 markdown，不要输出额外文字。"
    )

    url = f"{config.QUICKJUDGE_BASE_URL}/api/vision_grade"
    payload = {
        "files": quickjudge_files,
        "prompt_template": prompt_template,
        "save_to_class_center": False,
    }

    req_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"调用 QuickJudge 失败: {str(e)}") from e

    individual_reports = (data.get("individual_reports") or {}) if isinstance(data, dict) else {}
    if not individual_reports:
        return []

    # vision_grade 会用原文件路径作为 key；我们取第一个
    first_key = next(iter(individual_reports.keys()))
    report_text = individual_reports[first_key].get("report") or ""

    parsed = _json_from_text_loose(report_text)
    if not parsed:
        return []

    candidates = parsed.get("candidates") or []
    out: List[Dict[str, Any]] = []
    for c in candidates:
        if not isinstance(c, dict):
            continue
        fn = c.get("field_name")
        if not fn:
            continue
        conf = c.get("confidence")
        out.append({"field_name": str(fn), "confidence": conf})
    return out[:5]


@router.post("/suggest-fields", response_model=SuggestFieldsResponse)
def suggest_fields(req: SuggestFieldsRequest, db: Session = Depends(get_db)) -> SuggestFieldsResponse:
    template = db.query(Template).filter(Template.id == req.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    if template.file_type != ".pdf":
        raise HTTPException(status_code=400, detail="VL 方案B 当前仅支持 PDF 模板（需要 PDF.js/渲染几何一致）")

    pdf_path = template.file_path
    if not pdf_path:
        raise HTTPException(status_code=404, detail="模板文件路径为空")

    try:
        crop_png = _render_pdf_page_crop_to_png(
            pdf_path=pdf_path,
            page_index=req.page,
            x_pdf=req.x,
            y_pdf=req.y,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"裁剪失败: {str(e)}") from e

    # 写入 QuickJudge 本地可读目录，然后用它的 relative path 调用
    filename = f"{uuid.uuid4().hex}.png"
    crop_path = config.QUICKJUDGE_VL_CROPS_DIR / filename
    try:
        crop_path.write_bytes(crop_png)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入裁剪图片失败: {str(e)}") from e

    quickjudge_files = [f"vl_crops/{filename}"]

    field_names = _get_available_field_names()
    suggestions = _call_quickjudge_for_field_suggestions(quickjudge_files, field_names)

    return SuggestFieldsResponse(suggestions=suggestions)

