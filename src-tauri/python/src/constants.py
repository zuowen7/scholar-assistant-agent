"""项目级共享常量 — 鶈除 cleaner 与 chunker 间的重复定义"""

from __future__ import annotations

# 引用区标题检测模式 (大小写不敏感)
REFERENCE_SECTION_PATTERNS = [
    r"REFERENCES\s+AND\s+NOTES",
    r"REFERENCES",
    r"BIBLIOGRAPHY",
    r"LITERATURE\s+CITED",
    r"WORKS\s+CITED",
    r"SUPPLEMENTARY\s+MATERIALS",
]
