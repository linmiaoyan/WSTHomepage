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
import urllib.error
import urllib.request
import base64
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


class DetectPlaceholdersRequest(BaseModel):
    template_id: int
    page: int = 0  # 0-based


class DetectPlaceholdersResponse(BaseModel):
    candidates: List[Dict[str, Any]]
    raw: Optional[str] = None
    model: Optional[str] = None
    page_width: float
    page_height: float


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


def _json_list_from_text_loose(text: str) -> Optional[list]:
    """
    从模型输出中提取 JSON 数组；兼容 ```json 代码块和前后解释文字。
    """
    if not text:
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json|JSON)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict) and isinstance(obj.get("candidates"), list):
            return obj["candidates"]
    except Exception:
        pass
    start = s.find("[")
    end = s.rfind("]")
    if start >= 0 and end > start:
        try:
            obj = json.loads(s[start:end + 1])
            if isinstance(obj, list):
                return obj
        except Exception:
            return None
    obj = _json_from_text_loose(s)
    if isinstance(obj, dict) and isinstance(obj.get("candidates"), list):
        return obj["candidates"]
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


def _get_available_fields() -> List[Dict[str, str]]:
    from app.routers.templates import get_available_fields

    data = get_available_fields()
    return list(data.get("all_fields") or [])


def _field_alias_block(fields: List[Dict[str, str]]) -> str:
    aliases = {
        "name": ["姓名", "教师姓名", "填报人", "本人姓名"],
        "sex": ["性别", "男/女"],
        "id_number": ["身份证号", "身份证号码", "证件号码"],
        "phone": ["手机号", "联系电话", "手机号码"],
        "email": ["邮箱", "电子邮箱"],
        "department": ["部门", "处室", "所在部门", "任职部门"],
        "position": ["职位", "职务", "行政职务"],
        "title": ["职称", "专业技术职务"],
        "age": ["年龄"],
        "birth_date": ["出生日期", "出生年月"],
        "education": ["学历", "最高学历"],
        "degree": ["学位", "最高学位"],
        "school": ["毕业学校", "毕业院校"],
        "major": ["所学专业", "专业"],
        "work_date": ["参加工作时间", "工作时间"],
        "work_years": ["工龄", "工作年限"],
        "teach_years": ["教龄", "任教年限"],
        "political_status": ["政治面貌"],
        "nationality": ["民族"],
        "native_place": ["籍贯", "出生地"],
    }
    lines = []
    known = {str(f.get("name") or ""): str(f.get("label") or "") for f in fields}
    for name, label in known.items():
        if not name:
            continue
        bits = [label] if label else []
        bits.extend(aliases.get(name, []))
        dedup = []
        for x in bits:
            if x and x not in dedup:
                dedup.append(x)
        lines.append(f"- {name}: {'、'.join(dedup) if dedup else name}")
    return "\n".join(lines)


def _render_pdf_page_to_png(pdf_path: str, page_index: int, render_scale: float = 2.0) -> Tuple[bytes, float, float, int, int, float]:
    """渲染整页 PDF 为 PNG，返回 bytes、PDF pt 尺寸、图片像素尺寸、scale。"""
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise HTTPException(status_code=500, detail="缺少 PyMuPDF：pip install pymupdf") from e

    doc = fitz.open(pdf_path)
    try:
        if page_index < 0 or page_index >= len(doc):
            raise HTTPException(status_code=400, detail="page 越界")
        page = doc.load_page(page_index)
        page_w_pt = float(page.rect.width)
        page_h_pt = float(page.rect.height)
        matrix = fitz.Matrix(render_scale, render_scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        return pix.tobytes("png"), page_w_pt, page_h_pt, int(pix.width), int(pix.height), render_scale
    finally:
        doc.close()


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


def _call_siliconflow_vision_for_placeholders(
    png_bytes: bytes,
    fields: List[Dict[str, str]],
    page_w_pt: float,
    page_h_pt: float,
    image_w_px: int,
    image_h_px: int,
) -> Tuple[List[Dict[str, Any]], str, str]:
    """
    调用硅基流动视觉模型，让模型在页面图上标出可能需要填写的位置。
    返回模型 candidates、raw 文本、model 名称。
    """
    api_key = config.SILICONFLOW_API_KEY
    if not api_key:
        raise HTTPException(status_code=503, detail="未配置硅基流动 API Key：请设置 SILICONFLOW_API_KEY 或 CHAT_SERVER_API_TOKEN")

    model = config.TEMPLATE_VISION_MODEL
    image_b64 = base64.b64encode(png_bytes).decode("ascii")
    field_names = [str(f.get("name") or "") for f in fields if f.get("name")]
    field_aliases = _field_alias_block(fields)
    prompt = f"""
你是学校表格模板的“填空位置预标注”助手。请观察这张 PDF 页面截图，找出最可能需要批量填入教师数据的位置。

页面信息：
- 图片尺寸：{image_w_px} x {image_h_px} 像素
- PDF 尺寸：{page_w_pt:.2f} x {page_h_pt:.2f} pt

候选字段只能优先使用这些 field_name：
{', '.join(field_names)}

字段含义参考：
{field_aliases}

识别目标：
1. 找空白单元格、横线、括号后空白、表格中需要填写的格子。
2. 根据空白格左侧/上方/附近文字判断字段。
3. 不要标标题、说明文字、已经填写好的固定文字。
4. 如果无法匹配已有 field_name，可给 field_name 一个简短英文/拼音/中文变量名，并将 is_extra 设为 true。
5. 只输出 JSON 数组，不要 markdown，不要解释。

输出数组元素格式：
{{
  "field_name": "name",
  "label": "姓名",
  "bbox": {{"x": 120, "y": 300, "width": 90, "height": 24}},
  "confidence": 0.86,
  "reason": "左侧文字为姓名"
}}

其中 bbox 是图片像素坐标，原点在图片左上角。
""".strip()

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                ],
            }
        ],
        "max_tokens": config.TEMPLATE_VISION_MAX_TOKENS,
        "temperature": 0,
    }
    req_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        config.SILICONFLOW_API_URL,
        data=req_data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            raw_resp = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw_resp)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:1000]
        raise HTTPException(status_code=502, detail=f"硅基流动视觉模型调用失败: HTTP {e.code} {body}") from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"硅基流动视觉模型调用失败: {str(e)}") from e

    try:
        raw_text = data["choices"][0]["message"]["content"]
    except Exception:
        raw_text = json.dumps(data, ensure_ascii=False)[:2000]
    candidates = _json_list_from_text_loose(str(raw_text)) or []
    return candidates, str(raw_text), model


def _normalize_detected_candidates(
    raw_candidates: List[Dict[str, Any]],
    fields: List[Dict[str, str]],
    page_index: int,
    page_w_pt: float,
    page_h_pt: float,
    render_scale: float,
) -> List[Dict[str, Any]]:
    known = {str(f.get("name") or "") for f in fields if f.get("name")}
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        bbox = item.get("bbox") or {}
        if not isinstance(bbox, dict):
            continue
        try:
            bx = float(bbox.get("x"))
            by = float(bbox.get("y"))
            bw = float(bbox.get("width") or bbox.get("w") or 0)
            bh = float(bbox.get("height") or bbox.get("h") or 0)
        except (TypeError, ValueError):
            continue
        if bw <= 1 or bh <= 1:
            continue
        field_name = str(item.get("field_name") or item.get("field") or item.get("name") or "").strip()
        label = str(item.get("label") or field_name or "待填写").strip()
        if not field_name:
            # 未能识别字段时给一个稳定的额外变量名，管理员可再改/删。
            field_name = re.sub(r"\W+", "_", label).strip("_") or "extra_field"
        # PDF 写入点：放在候选框左侧略内缩、垂直方向靠近文字基线。
        x_pt = max(0.0, min(page_w_pt, (bx + 3.0) / render_scale))
        y_from_top_pt = (by + max(10.0, bh * 0.72)) / render_scale
        y_pdf = max(0.0, min(page_h_pt, page_h_pt - y_from_top_pt))
        font_size = max(8, min(18, round((bh / render_scale) * 0.62)))
        key = (page_index, round(x_pt, 1), round(y_pdf, 1), field_name)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "field_name": field_name,
            "label": label,
            "page": page_index,
            "x": round(x_pt, 2),
            "y": round(y_pdf, 2),
            "font_size": font_size,
            "is_extra": field_name not in known,
            "is_ai_suggested": True,
            "confidence": item.get("confidence"),
            "reason": item.get("reason") or "",
            "bbox": {
                "x": bx,
                "y": by,
                "width": bw,
                "height": bh,
            },
        })
    return out[:80]


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


@router.post("/detect-placeholders", response_model=DetectPlaceholdersResponse)
def detect_placeholders(req: DetectPlaceholdersRequest, db: Session = Depends(get_db)) -> DetectPlaceholdersResponse:
    """
    AI 预识别当前 PDF 页中可能需要填写的位置。
    返回的是候选占位符，不直接保存；管理员需要在前端确认/微调后再保存。
    """
    template = db.query(Template).filter(Template.id == req.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")
    if template.file_type != ".pdf":
        raise HTTPException(status_code=400, detail="AI 预识别当前仅支持 PDF 模板")
    if not template.file_path:
        raise HTTPException(status_code=404, detail="模板文件路径为空")

    png_bytes, page_w_pt, page_h_pt, image_w_px, image_h_px, render_scale = _render_pdf_page_to_png(
        template.file_path,
        req.page,
        render_scale=2.0,
    )
    fields = _get_available_fields()
    raw_candidates, raw_text, model = _call_siliconflow_vision_for_placeholders(
        png_bytes=png_bytes,
        fields=fields,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        image_w_px=image_w_px,
        image_h_px=image_h_px,
    )
    candidates = _normalize_detected_candidates(
        raw_candidates=raw_candidates,
        fields=fields,
        page_index=req.page,
        page_w_pt=page_w_pt,
        page_h_pt=page_h_pt,
        render_scale=render_scale,
    )
    return DetectPlaceholdersResponse(
        candidates=candidates,
        raw=raw_text[:2000],
        model=model,
        page_width=page_w_pt,
        page_height=page_h_pt,
    )

