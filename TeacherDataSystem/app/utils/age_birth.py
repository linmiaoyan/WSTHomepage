"""
年龄与出生日期：按「录入日」由周岁反推出生日期，填表/导出时按「参考日」重算年龄。
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Any, Dict, Optional, Union

RefDate = Union[date, datetime]


def _as_date(ref: RefDate) -> date:
    if isinstance(ref, datetime):
        return ref.date()
    return ref


def subtract_years(d: date, years: int) -> date:
    """从 d 往前推 years 个公历年，处理 2 月 29 日等情况。"""
    y = d.year - int(years)
    m, day = d.month, d.day
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(day, last))


def age_completed_years(birth: date, ref: date) -> int:
    """周岁（实足年龄）：ref 当日是否已过生日。"""
    a = ref.year - birth.year
    if (ref.month, ref.day) < (birth.month, birth.day):
        a -= 1
    return max(a, 0)


def _parse_int_age(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v if 0 <= v <= 150 else None
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        i = int(v)
        return i if 0 <= i <= 150 else None
    s = str(v).strip()
    if not s:
        return None
    m = re.match(r"^(\d{1,3})", s)
    if not m:
        return None
    i = int(m.group(1))
    return i if 0 <= i <= 150 else None


def _parse_iso_date(s: str) -> Optional[date]:
    s = (s or "").strip().replace(".", "-").replace("/", "-")
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    try:
        dt = datetime.strptime(s[:7], "%Y-%m")
        return date(dt.year, dt.month, 1)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(s[:6], "%Y%m")
        return date(dt.year, dt.month, 1)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(s[:8], "%Y%m%d")
        return dt.date()
    except ValueError:
        pass
    m = re.match(r"^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?$", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        d = int(m.group(3)) if m.group(3) else 1
        try:
            last = calendar.monthrange(y, mo)[1]
            return date(y, mo, min(d, last))
        except ValueError:
            return None
    return None


def parse_birth_from_extra(extra: Dict[str, Any]) -> Optional[date]:
    """从扩展字段中解析生日（优先明确日期字段）。"""
    if not extra:
        return None
    keys = ("birth_date", "出生年月日", "出生日期", "出生年月")
    for k in keys:
        if k not in extra or extra[k] is None:
            continue
        raw = extra[k]
        if hasattr(raw, "date") and callable(getattr(raw, "date")):
            try:
                d = raw.date() if not isinstance(raw, date) else raw
                if isinstance(d, date):
                    return d
            except Exception:
                pass
        d = _parse_iso_date(str(raw).strip())
        if d:
            return d
    return None


def parse_age_from_extra(extra: Dict[str, Any]) -> Optional[int]:
    if not extra:
        return None
    for k in ("age", "年龄"):
        if k in extra:
            a = _parse_int_age(extra[k])
            if a is not None:
                return a
    return None


def _parse_age_as_of(extra: Dict[str, Any]) -> Optional[date]:
    v = extra.get("age_as_of")
    if v is None:
        return None
    if hasattr(v, "date") and callable(getattr(v, "date")):
        try:
            return v.date() if isinstance(v, datetime) else v
        except Exception:
            pass
    return _parse_iso_date(str(v).strip())


def normalize_extra_age_birth(extra: Dict[str, Any], ref: RefDate) -> None:
    """
    写入时：根据录入日 ref 统一 birth_date / age / age_as_of / 年龄。
    - 仅有周岁年龄时：按 ref 当日倒推生日（与 ref 同月同日，保证 ref 当日周岁为所填年龄）。
    - 仅有出生日期时：写入当时周岁与 age_as_of。
    - 两者都有时：以出生日期为准，按 ref 重算年龄。
    """
    if not extra:
        return
    refd = _as_date(ref)
    birth = parse_birth_from_extra(extra)
    age_in = parse_age_from_extra(extra)

    if birth:
        extra["birth_date"] = birth.isoformat()
        extra["age_as_of"] = refd.isoformat()
        a = age_completed_years(birth, refd)
        extra["age"] = str(a)
        extra["年龄"] = str(a)
        return

    if age_in is not None:
        b = subtract_years(refd, age_in)
        extra["birth_date"] = b.isoformat()
        extra["age_as_of"] = refd.isoformat()
        extra["age"] = str(age_in)
        extra["年龄"] = str(age_in)
        ym = f"{b.year:04d}-{b.month:02d}"
        if "出生年月" not in extra or not str(extra.get("出生年月") or "").strip():
            extra["出生年月"] = ym


def prepare_extra_for_fill(
    extra: Dict[str, Any],
    ref: RefDate,
    *,
    legacy_as_of: Optional[RefDate] = None,
) -> Dict[str, Any]:
    """
    填表/导出用：在副本上按参考日（通常为今天）重算 age / 年龄；不修改库内原 dict。
    legacy_as_of：旧数据仅有 age、无 birth_date/age_as_of 时，用作「当时录入日」（如教师 updated_at）。
    """
    out = dict(extra) if extra else {}
    refd = _as_date(ref)
    birth = parse_birth_from_extra(out)
    if birth:
        a = age_completed_years(birth, refd)
        out["age"] = str(a)
        out["年龄"] = str(a)
        out["birth_date"] = birth.isoformat()
        return out

    age_snap = parse_age_from_extra(out)
    as_of = _parse_age_as_of(out)
    if age_snap is not None and as_of is None and legacy_as_of is not None:
        as_of = _as_date(legacy_as_of)
    if age_snap is not None and as_of is not None:
        birth2 = subtract_years(as_of, age_snap)
        a = age_completed_years(birth2, refd)
        out["age"] = str(a)
        out["年龄"] = str(a)
        out["birth_date"] = birth2.isoformat()
    return out
