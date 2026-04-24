"""项目级共享常量 — 鶈除 cleaner 与 chunker 间的重复定义"""

from __future__ import annotations

# 引用区标题检测模式 (大小写不敏感)
# 注意: 不含 \s，因为 line.strip() 已处理首尾空白，re.match 直接匹配原文本
REFERENCE_SECTION_PATTERNS: list[str] = [
    "REFERENCES AND NOTES",
    "REFERENCES",
    "BIBLIOGRAPHY",
    "LITERATURE CITED",
    "WORKS CITED",
    "SUPPLEMENTARY MATERIALS",
]
