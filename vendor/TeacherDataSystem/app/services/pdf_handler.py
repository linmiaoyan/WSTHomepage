"""
PDF 处理：在指定位置叠加文本或签名图。

优先使用 PyMuPDF（fitz），与 PDF.js 在 scale=1 下的用户坐标（左下角为原点、Y 向上）一致；
未安装时回退到 ReportLab + PyPDF2 合并（对带 /Rotate 的页面可能偏差较大）。
"""
from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    from PyPDF2 import PdfReader, PdfWriter
    REPORTLAB_PYPDF2_AVAILABLE = True
except ImportError:
    REPORTLAB_PYPDF2_AVAILABLE = False


def get_pdf_page_size(pdf_path: str, page_num: int = 0) -> Tuple[float, float]:
    """返回 (width, height)，单位 pt，与 PDF.js getViewport({scale:1}) 一致优先用 PyMuPDF。"""
    if PYMUPDF_AVAILABLE:
        try:
            doc = fitz.open(pdf_path)
            if page_num < len(doc):
                r = doc[page_num].rect
                doc.close()
                return float(r.width), float(r.height)
            doc.close()
        except Exception:
            pass
    if REPORTLAB_PYPDF2_AVAILABLE:
        try:
            reader = PdfReader(pdf_path)
            if page_num < len(reader.pages):
                page = reader.pages[page_num]
                return float(page.mediabox.width), float(page.mediabox.height)
        except Exception:
            pass
    return (595.0, 842.0)


def _resolve_field_value(pos: Dict[str, Any], data: Dict[str, Any]) -> Any:
    if pos.get("is_constant") and pos.get("constant_value"):
        return pos.get("constant_value", "")
    field_name = pos.get("field_name", "")
    value = data.get(field_name, "")
    if not value and isinstance(data.get("extra_data"), dict):
        value = data["extra_data"].get(field_name, "")
    return value if value is not None else ""


def _add_text_to_pdf_fitz(
    template_path: str,
    output_path: str,
    text_positions: List[Dict[str, Any]],
    data: Dict[str, Any],
) -> None:
    import fitz

    doc = fitz.open(template_path)
    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for pos in text_positions:
        p = int(pos.get("page", 0))
        by_page.setdefault(p, []).append(pos)

    for page_index, positions in by_page.items():
        if page_index < 0 or page_index >= len(doc):
            continue
        page = doc[page_index]
        rect = page.rect
        h_pt = float(rect.height)

        for pos in positions:
            field_name = pos.get("field_name", "")
            value = _resolve_field_value(pos, data)
            value_str = str(value) if value else ""
            font_size = float(pos.get("font_size", 12))
            x = float(pos.get("x", 0))
            y_pdf = float(pos.get("y", 0))

            if isinstance(value, str) and value.startswith("data:image"):
                try:
                    header, encoded = value.split(",", 1)
                    raw = base64.b64decode(encoded)
                except Exception as e:
                    print(f"[PDF/fitz] 解码签名失败 {field_name}: {e}")
                    continue
                try:
                    from PIL import Image as PILImage
                except ImportError:
                    print("[PDF/fitz] 需要 Pillow 以插入签名图")
                    continue
                try:
                    img = PILImage.open(BytesIO(raw))
                    tw = max(font_size * 2.5, 24.0)
                    th = max(font_size * 1.0, 12.0)
                    iw, ih = img.size
                    ratio = min(tw / iw, th / ih, 1.0)
                    nw, nh = int(iw * ratio), int(ih * ratio)
                    if ratio < 1.0:
                        img = img.resize((nw, nh), PILImage.Resampling.LANCZOS)
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    img_h_pt = float(nh)
                    y_top = h_pt - y_pdf
                    x0, y0 = x, y_top - img_h_pt
                    ir = fitz.Rect(x0, y0, x0 + float(nw), y_top)
                    page.insert_image(ir, stream=buf.getvalue())
                except Exception as e:
                    print(f"[PDF/fitz] 插入图片失败 {field_name}: {e}")
                continue

            if not value_str:
                continue

            y_top = h_pt - y_pdf
            wrote = False
            for fname in ("china-s", "china-ts", "helv"):
                try:
                    page.insert_text(
                        (x, y_top),
                        value_str,
                        fontsize=font_size,
                        fontname=fname,
                        render_mode=0,
                    )
                    wrote = True
                    break
                except Exception:
                    continue
            if not wrote:
                print(f"[PDF/fitz] 写入文本失败 {field_name}")

    doc.save(output_path, incremental=False, deflate=True, garbage=4)
    doc.close()


def _add_text_to_pdf_reportlab(
    template_path: str,
    output_path: str,
    text_positions: List[Dict[str, Any]],
    data: Dict[str, Any],
) -> None:
    import os
    import platform
    import shutil
    from io import BytesIO

    shutil.copy(template_path, output_path)
    reader = PdfReader(output_path)
    writer = PdfWriter()

    by_page: Dict[int, List[Dict[str, Any]]] = {}
    for pos in text_positions:
        p = int(pos.get("page", 0))
        by_page.setdefault(p, []).append(pos)

    for page_num in range(len(reader.pages)):
        page = reader.pages[page_num]
        page_width = float(page.mediabox.width)
        page_height = float(page.mediabox.height)

        if page_num in by_page:
            try:
                from PIL import Image as PILImage
                PIL_AVAILABLE = True
            except ImportError:
                PIL_AVAILABLE = False

            packet = BytesIO()
            can = canvas.Canvas(packet, pagesize=(page_width, page_height))
            font_name = "Helvetica"
            try:
                if platform.system() == "Windows":
                    font_dirs = [
                        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
                        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
                    ]
                    for font_dir in font_dirs:
                        if not os.path.isdir(font_dir):
                            continue
                        for font_file in ("msyh.ttf", "simsun.ttc", "simhei.ttf"):
                            fp = os.path.join(font_dir, font_file)
                            if os.path.isfile(fp):
                                pdfmetrics.registerFont(TTFont("ZhFont", fp))
                                font_name = "ZhFont"
                                break
                        if font_name != "Helvetica":
                            break
            except Exception as e:
                print(f"[PDF/reportlab] 字体注册失败: {e}")

            for pos in by_page[page_num]:
                value = _resolve_field_value(pos, data)
                x = float(pos.get("x", 0))
                y = float(pos.get("y", 0))
                fs = float(pos.get("font_size", 12))

                if isinstance(value, str) and value.startswith("data:image") and PIL_AVAILABLE:
                    try:
                        header, encoded = value.split(",", 1)
                        raw = base64.b64decode(encoded)
                        img = PILImage.open(BytesIO(raw))
                        tw, th = fs * 2.5, fs * 1.0
                        iw, ih = img.size
                        ratio = min(tw / iw, th / ih, 1.0)
                        nw, nh = int(iw * ratio), int(ih * ratio)
                        if ratio < 1.0:
                            img = img.resize((nw, nh), PILImage.Resampling.LANCZOS)
                        b2 = BytesIO()
                        img.save(b2, format="PNG")
                        b2.seek(0)
                        can.drawImage(ImageReader(b2), x, y - nh, width=nw, height=nh)
                    except Exception as e:
                        print(f"[PDF/reportlab] 图片失败: {e}")
                    continue

                vs = str(value) if value is not None else ""
                if not vs:
                    continue
                try:
                    can.setFont(font_name, fs)
                    can.drawString(x, y, vs)
                except Exception:
                    can.setFont("Helvetica", fs)
                    can.drawString(x, y, vs)

            can.save()
            packet.seek(0)
            overlay = PdfReader(packet)
            page.merge_page(overlay.pages[0])

        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)


def add_text_to_pdf(
    template_path: str,
    output_path: str,
    text_positions: List[Dict[str, Any]],
    data: Dict[str, Any],
) -> None:
    if not text_positions:
        raise ValueError("未提供占位符位置")

    if PYMUPDF_AVAILABLE:
        print("[PDF处理] 使用 PyMuPDF 写入（推荐，与 PDF.js 坐标更一致）")
        _add_text_to_pdf_fitz(template_path, output_path, text_positions, data)
        return

    if not REPORTLAB_PYPDF2_AVAILABLE:
        raise ImportError("请安装 PDF 依赖: pip install pymupdf  或  pip install reportlab PyPDF2 Pillow")

    print("[PDF处理] 使用 ReportLab + PyPDF2（建议安装 pymupdf 以提高定位准确度）")
    _add_text_to_pdf_reportlab(template_path, output_path, text_positions, data)


def extract_placeholders_from_pdf(pdf_path: str) -> List[str]:
    return []


def get_pdf_preview(pdf_path: str, page_num: int = 0) -> bytes:
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, first_page=page_num + 1, last_page=page_num + 1)
        if images:
            buf = BytesIO()
            images[0].save(buf, format="PNG")
            return buf.getvalue()
        raise RuntimeError("无法生成预览图片")
    except ImportError:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (595, 842), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 400), "请安装 pdf2image 与 poppler，或使用 PDF.js 预览", fill="black")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (595, 842), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((50, 400), f"预览失败: {e}", fill="red")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
