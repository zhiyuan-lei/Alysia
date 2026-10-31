from __future__ import annotations

import re


def normalize_narration(
    text: str,
    *,
    code_policy: str = "replace",
    url_replacement: str = "链接",
) -> str:
    """执行安全、可追溯的轻量口播规范化，不擅自扩写数字或缩写。"""
    if code_policy not in {"replace", "skip"}:
        raise ValueError("code_policy 仅支持 replace 或 skip")
    code_value = " 代码示例 " if code_policy == "replace" else " "
    value = re.sub(r"```.*?```", code_value, text, flags=re.DOTALL)
    value = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", value)
    value = re.sub(r"https?://\S+", f" {url_replacement} ", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"(?m)^\s*>\s?", "", value)
    value = re.sub(r"[*_~]", "", value)
    value = value.translate(str.maketrans({",": "，", "!": "！", "?": "？", ";": "；", ":": "："}))
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r"\s*\n+\s*", "。", value)
    value = re.sub(r"([。！？；，])\1+", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" 。")
