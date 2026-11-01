"""pointparse · 解析器。

支持的真实格式（按命中顺序）：

| 格式名 | 例子 |
|---|---|
| `dict_xy` | ``{"x": 400, "y": 900}`` |
| `dict_point` | ``{"point": [400, 900]}`` |
| `sequence` | ``[400, 900]`` / ``(400, 900)`` |
| `paren_csv` | ``"(400, 900)"`` |
| `bare_csv` | ``"400, 900"`` |
| `kv` | ``"x=400, y=900"`` |
| `prose` | ``"click at (400, 900)"`` / ``"tap 400,900 please"`` |
| `xml_tag` | ``"<point>400 900</point>"`` |
| `space_csv` | ``"400 900"`` |

设计原则
--------
1. **只取第一个匹配**，但如果文本里出现**多个互不相同的指点**，抛
   :class:`Ambiguity`——不替调用方选。
2. **bbox 不当 point 用**。``[x1,y1,x2,y2]`` 四元组抛 :class:`Ambiguity`，
   因为"指哪个角"是语义决策，不是解析决策。
3. **空间只给线索**。像素还是归一化由调用方结合自己声明的空间判定。
4. **拒答不是错误**。返回 :class:`NoPointFound`，调用方应能优雅处理。
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

from .result import Ambiguity, NoPointFound, ParsedPoint, SpaceHint

__all__ = ["parse_point", "parse_points", "infer_space"]


# ---------------------------------------------------------------- 空间线索
def infer_space(x: float, y: float, *, width: int | None = None, height: int | None = None) -> SpaceHint:
    """从数值形态推断空间线索。

    规则（有序，先命中先返回）：

    1. 两个都是 ``[0,1]`` 内的小数 → ``NORMALIZED_UNIT``
    2. 两个都是整数，且都在 ``[0,width]x[0,height]`` 内 → ``PIXEL_INT``
    3. 两个都是整数，且都在 ``[0,1000]`` 内 → ``NORMALIZED_1000``
    4. 其他 → ``UNKNOWN``

    **故意不做的事**：不给概率、不合并线索、不在规则冲突时挑一个。
    调用方拿到了线索，必须自己结合声明的空间校验。
    """
    both_int = float(x).is_integer() and float(y).is_integer()
    in_unit = 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0

    if in_unit and not (both_int and x in (0.0, 1.0) and y in (0.0, 1.0)):
        return SpaceHint.NORMALIZED_UNIT

    if both_int and width and height:
        if 0 <= x <= width and 0 <= y <= height:
            return SpaceHint.PIXEL_INT

    if both_int and 0 <= x <= 1000 and 0 <= y <= 1000:
        return SpaceHint.NORMALIZED_1000

    return SpaceHint.UNKNOWN


# ---------------------------------------------------------------- 各格式提取
_NUM = r"[-+]?\d+(?:\.\d+)?"


def _to_float(s: str) -> float:
    v = float(s)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"非有限数：{s!r}")
    return v


def _mk(x: float, y: float, fmt: str, raw: Any) -> ParsedPoint:
    return ParsedPoint(x=x, y=y, space_hint=infer_space(x, y), source_format=fmt, raw=raw)


def _from_dict(obj: dict, raw: Any) -> ParsedPoint:
    low = {str(k).lower(): v for k, v in obj.items()}

    # 显式给出 x/y 键
    if "x" in low or "y" in low:
        xv, yv = low.get("x"), low.get("y")
        if xv is None or yv is None:
            # 模型明示无法确定 —— 正常输出，不是异常
            reason = low.get("reason") or low.get("error") or "dict 中 x/y 为 null"
            raise NoPointFound(raw, str(reason))
        return _mk(_to_float(str(xv)), _to_float(str(yv)), "dict_xy", raw)

    for key in ("point", "coordinate", "coordinates", "position", "pos"):
        if key in low:
            v = low[key]
            if isinstance(v, (list, tuple)) and len(v) == 2:
                return _mk(_to_float(str(v[0])), _to_float(str(v[1])), "dict_point", raw)
            if isinstance(v, dict):
                return _from_dict(v, raw)

    if "bbox" in low or "box" in low:
        raise Ambiguity(raw, [], "dict 给出的是 bbox，不是 point")

    if "error" in low:
        raise NoPointFound(raw, str(low["error"]))

    raise NoPointFound(raw, "dict 里没有可识别的坐标键")


def _from_sequence(seq: Any, raw: Any) -> ParsedPoint:
    if len(seq) == 2:
        # 统一叫 sequence：JSON 与多数语言无法区分 list/tuple，
        # 把这个区别当成不同格式只会让向量不可移植。
        return _mk(_to_float(str(seq[0])), _to_float(str(seq[1])), "sequence", raw)
    if len(seq) == 4:
        raise Ambiguity(raw, [seq], "四元组是 bbox，不是 point")
    raise NoPointFound(raw, f"序列长度 {len(seq)} 不是 2")


def _find_all_pairs(text: str) -> list[tuple[float, float]]:
    """在自由文本里找出所有 (x, y) 数对。"""
    out: list[tuple[float, float]] = []

    # 括号 / 尖括号包裹
    for m in re.finditer(rf"[\(<\[𝄀\s]({_NUM})[\s,；;]+({_NUM})[\s]*[\)>\]𝄀]", text):
        out.append((_to_float(m.group(1)), _to_float(m.group(2))))

    # 裸 "400, 900" / "400 900"
    for m in re.finditer(rf"(?<![\d.])({_NUM})[\s,；;]+({_NUM})(?![\d.])", text):
        out.append((_to_float(m.group(1)), _to_float(m.group(2))))

    # 去重（保序）
    seen: set[tuple[float, float]] = set()
    uniq: list[tuple[float, float]] = []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


_REFUSAL = re.compile(
    r"(cannot|can't|unable|no visible|not visible|nothing|none|null|nil|n/a|"
    r"无法|看不到|找不到|没有|未找到|不能)",
    re.IGNORECASE,
)


def _try_embedded_json(t: str, raw: Any) -> ParsedPoint | None:
    """从文本任意位置抽出 JSON object/array 并解析。

    覆盖 ```json 包裹、前后有废话、单引号与尾随逗号等真实脏情况。
    返回 None 表示文本里没有可解析的 JSON。
    """
    # 整体就是 JSON
    if t[:1] in "{[":
        try:
            obj = json.loads(t)
        except json.JSONDecodeError:
            obj = None
        if obj is not None:
            if isinstance(obj, dict):
                return _from_dict(obj, raw)
            if isinstance(obj, (list, tuple)):
                return _from_sequence(obj, raw)

    # 嵌在文本里的 JSON object
    for m in re.finditer(r"\{[^{}]*\}", t, re.S):
        frag = m.group(0)
        try:
            obj = json.loads(frag)
        except json.JSONDecodeError:
            fixed = frag.replace("'", '"')
            fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
            try:
                obj = json.loads(fixed)
            except json.JSONDecodeError:
                continue
        if isinstance(obj, dict):
            try:
                return _from_dict(obj, raw)
            except ParseError:
                continue

    # 嵌在文本里的两元素 JSON array
    for m in re.finditer(r"\[[^\[\]]*\]", t):
        frag = m.group(0)
        try:
            obj = json.loads(frag)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, list) and len(obj) == 2:
            return _from_sequence(obj, raw)

    return None


def _from_text(text: str, raw: Any) -> ParsedPoint:
    t = text.strip()
    if not t:
        raise NoPointFound(raw, "空字符串")

    # 先看是不是 JSON（含被 markdown/废话包裹的）
    if t[:1] in "{[" or "{" in t:
        embedded = _try_embedded_json(t, raw)
        if embedded is not None:
            return embedded
        if t[:1] in "{[":
            raise NoPointFound(raw, "疑似 JSON 但解析失败")

    # k=v 形式
    kv = re.search(rf"x\s*[=:]\s*({_NUM})[\s,；;]*y\s*[=:]\s*({_NUM})", t, re.IGNORECASE)
    if kv:
        return _mk(_to_float(kv.group(1)), _to_float(kv.group(2)), "kv", raw)

    # 连续 3 个以上逗号分隔的数字 —— 千分位歧义，无法判定，必须报错
    # "1,400, 900" 可能是 (1400, 900)，也可能是 (1, 400) 加一个游离的 900
    if re.search(rf"(?:{_NUM}\s*,\s*){{2,}}{_NUM}", t):
        raise Ambiguity(raw, [], "连续 3+ 个逗号分隔数字，可能是千分位，无法判定")

    pairs = _find_all_pairs(t)

    if not pairs:
        if _REFUSAL.search(t):
            raise NoPointFound(raw, "文本含拒答语义，且无数对")
        raise NoPointFound(raw, "文本里找不到数对")

    if len(pairs) > 1:
        raise Ambiguity(raw, pairs, f"文本里有 {len(pairs)} 个不同数对")

    x, y = pairs[0]
    fmt = "paren_csv" if re.search(rf"[\(<]{_NUM}[\s,]+{_NUM}[\)>]", t) else "bare_csv"
    return _mk(x, y, fmt, raw)


# ---------------------------------------------------------------- 主入口
def parse_point(raw: Any, *, strict: bool = True) -> ParsedPoint:
    """解析模型返回的单个指点。

    Parameters
    ----------
    raw:
        模型输出。接受 ``dict`` / ``list`` / ``tuple`` / ``str``。
    strict:
        ``True``（默认）时，文本里出现多个不同数对抛 :class:`Ambiguity`。
        ``False`` 时取第一个——**仅用于调试**，生产环境不要关。

    Raises
    ------
    NoPointFound
        模型没给指点（含拒答）。
    Ambiguity
        多个候选，无法唯一确定。
    ParseError
        其他解析失败。
    """
    if raw is None:
        raise NoPointFound(raw, "输入为 None")

    if isinstance(raw, ParsedPoint):
        return raw

    if isinstance(raw, dict):
        return _from_dict(raw, raw)

    if isinstance(raw, (list, tuple)):
        return _from_sequence(raw, raw)

    if isinstance(raw, str):
        return _from_text(raw, raw)

    # 数值型：单个标量不是点
    if isinstance(raw, (int, float)):
        raise NoPointFound(raw, "输入是单个标量，不是点")

    raise NoPointFound(raw, f"不支持的类型 {type(raw).__name__}")


def parse_points(raw: Any) -> list[ParsedPoint]:
    """解析出**所有**候选指点。不做去重抉择，交由调用方。

    与 :func:`parse_point` 的区别：宁可多给，不可猜。
    """
    if isinstance(raw, str):
        return [_mk(x, y, "bare_csv", raw) for x, y in _find_all_pairs(raw)]
    if isinstance(raw, (list, tuple)) and raw and isinstance(raw[0], (list, tuple)):
        return [
            _mk(_to_float(str(p[0])), _to_float(str(p[1])), "list", raw)
            for p in raw
            if len(p) == 2
        ]
    return [parse_point(raw)]
