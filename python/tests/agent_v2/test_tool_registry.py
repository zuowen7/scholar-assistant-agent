"""ToolRegistry 测试 — TR-001 ~ TR-053。"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from src.agent_v2.tools.registry import (
    ToolRegistry,
    ToolResult,
    create_default_registry,
)
from src.agent_v2.types import ToolError


@pytest.fixture
def registry(temp_workspace: Path) -> ToolRegistry:
    return create_default_registry(workspace_root=temp_workspace)


# ============================================================================
# 3.1 注册与发现
# ============================================================================

class TestRegistrationAndDiscovery:

    def test_tr001_register_builtin_tools(self, registry: ToolRegistry):
        """TR-001: 内置工具已注册"""
        assert registry.get("read_file") is not None
        assert registry.get("write_file") is not None
        assert registry.get("str_replace") is not None
        assert registry.get("grep_files") is not None
        assert registry.get("glob_files") is not None

    def test_tr002_list_all_tools(self, registry: ToolRegistry):
        """TR-002: definitions() 返回完整列表"""
        defs = registry.definitions()
        names = {d.name for d in defs}
        expected = {"read_file", "write_file", "str_replace", "grep_files", "glob_files", "list_dir", "run_command"}
        assert expected.issubset(names), f"Missing: {expected - names}"

    def test_tr003_find_by_name(self, registry: ToolRegistry):
        """TR-003: get("read_file") 返回正确 ToolDefinition"""
        spec = registry.get("read_file")
        assert spec is not None
        assert spec.definition.name == "read_file"
        assert "read" in spec.definition.description.lower()

    def test_tr004_nonexistent_tool(self, registry: ToolRegistry):
        """TR-004: 不存在的工具返回 None"""
        assert registry.get("nonexistent") is None

    def test_tr005_name_conflict(self, temp_workspace: Path):
        """TR-005: 重复注册同名工具报错"""
        reg = create_default_registry(workspace_root=temp_workspace)
        with pytest.raises(ToolError, match="already registered"):
            reg.register("read_file", "dup", {}, func=lambda args: ToolResult("ok"))

    def test_tr006_case_insensitive_lookup(self, registry: ToolRegistry):
        """TR-006: 大小写不敏感查找"""
        assert registry.get("Read_File") is not None
        assert registry.get("READ_FILE") is not None


# ============================================================================
# 3.2 工具执行
# ============================================================================

class TestToolExecution:

    @pytest.mark.asyncio
    async def test_tr010_read_file(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-010: 正确读取文件"""
        result = await registry.execute("read_file", {"file_path": "main.md"})
        assert not result.is_error
        assert "Hello" in result.output

    @pytest.mark.asyncio
    async def test_tr011_write_file(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-011: 正确写入文件"""
        result = await registry.execute("write_file", {"file_path": "new.txt", "content": "hello world"})
        assert not result.is_error
        assert (temp_workspace / "new.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_tr012_grep(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-012: grep 返回匹配行"""
        result = await registry.execute("grep_files", {"pattern": "hello", "path": "main.py"})
        assert not result.is_error
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_tr013_glob(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-013: glob 返回匹配路径"""
        result = await registry.execute("glob_files", {"pattern": "*.md", "path": "."})
        assert not result.is_error
        assert "main.md" in result.output

    @pytest.mark.asyncio
    async def test_tr014_str_replace(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-014: str_replace 替换文件内容"""
        result = await registry.execute("str_replace", {
            "file_path": "main.py",
            "old_string": "# TODO: fix",
            "new_string": "# fixed",
        })
        assert not result.is_error
        content = (temp_workspace / "main.py").read_text()
        assert "# fixed" in content
        assert "# TODO: fix" not in content

    @pytest.mark.asyncio
    async def test_tr015_missing_params(self, registry: ToolRegistry):
        """TR-015: 缺少必要参数时返回错误"""
        result = await registry.execute("read_file", {})
        assert result.is_error
        assert "file_path" in result.output

    @pytest.mark.asyncio
    async def test_tr016_result_format(self, registry: ToolRegistry):
        """TR-016: 工具返回值格式统一 ToolResult"""
        result = await registry.execute("read_file", {"file_path": "main.md"})
        assert isinstance(result, ToolResult)
        assert isinstance(result.output, str)
        assert isinstance(result.is_error, bool)


# ============================================================================
# 3.3 边缘测试
# ============================================================================

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_tr020_read_nonexistent(self, registry: ToolRegistry):
        """TR-020: 读取不存在的文件"""
        result = await registry.execute("read_file", {"file_path": "no_such_file.txt"})
        assert result.is_error
        assert "not found" in result.output

    @pytest.mark.asyncio
    async def test_tr021_read_binary(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-021: 读取二进制文件"""
        bin_file = temp_workspace / "data.bin"
        bin_file.write_bytes(bytes(range(256)))
        result = await registry.execute("read_file", {"file_path": "data.bin"})
        assert result.is_error

    @pytest.mark.asyncio
    async def test_tr022_write_empty(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-022: 写入空文件"""
        result = await registry.execute("write_file", {"file_path": "empty.txt", "content": ""})
        assert not result.is_error
        assert (temp_workspace / "empty.txt").read_text() == ""

    @pytest.mark.asyncio
    async def test_tr023_grep_empty_dir(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-023: grep 空目录"""
        empty_dir = temp_workspace / "empty"
        empty_dir.mkdir()
        result = await registry.execute("grep_files", {"pattern": "test", "path": "empty"})
        assert not result.is_error
        assert "no matches" in result.output

    @pytest.mark.asyncio
    async def test_tr025_str_replace_no_match(self, registry: ToolRegistry):
        """TR-025: old_string 不存在"""
        result = await registry.execute("str_replace", {
            "file_path": "main.py",
            "old_string": "NONEXISTENT_STRING_XYZ",
            "new_string": "replaced",
        })
        assert result.is_error
        assert "not found" in result.output

    @pytest.mark.asyncio
    async def test_tr026_str_replace_multiple_match(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-026: old_string 有多个匹配"""
        multi = temp_workspace / "multi.txt"
        multi.write_text("aaa\nbbb\naaa\n", encoding="utf-8")
        result = await registry.execute("str_replace", {
            "file_path": "multi.txt",
            "old_string": "aaa",
            "new_string": "ccc",
        })
        assert result.is_error
        assert "2 times" in result.output

    @pytest.mark.asyncio
    async def test_tr027_read_large_file(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-027: 读取超大文件不 OOM"""
        big = temp_workspace / "big.txt"
        big.write_text("x" * (300 * 1024), encoding="utf-8")
        result = await registry.execute("read_file", {"file_path": "big.txt"})
        assert not result.is_error
        assert "truncated" in result.output

    @pytest.mark.asyncio
    async def test_tr028_path_traversal(self, registry: ToolRegistry):
        """TR-028: 路径穿越被拒绝"""
        result = await registry.execute("read_file", {"file_path": "../../etc/passwd"})
        assert result.is_error
        assert "outside workspace" in result.output

    @pytest.mark.asyncio
    async def test_tr029_windows_reserved(self, registry: ToolRegistry):
        """TR-029: Windows 保留名被拒绝"""
        result = await registry.execute("write_file", {"file_path": "CON.txt", "content": "test"})
        assert result.is_error
        assert "reserved" in result.output.lower()

    @pytest.mark.asyncio
    async def test_tr029b_windows_reserved_aux(self, registry: ToolRegistry):
        """TR-029b: AUX 被拒绝"""
        result = await registry.execute("write_file", {"file_path": "AUX", "content": "test"})
        assert result.is_error


# ============================================================================
# 3.4 极限测试
# ============================================================================

class TestStress:

    @pytest.mark.asyncio
    async def test_tr040_many_tools(self):
        """TR-040: 100 个工具同时注册"""
        reg = ToolRegistry()
        for i in range(100):
            reg.register(f"tool_{i:03d}", f"Tool {i}", {}, func=lambda args: ToolResult("ok"))
        assert len(reg.definitions()) == 100
        assert reg.get("tool_050") is not None

    @pytest.mark.asyncio
    async def test_tr041_concurrent_execution(self, registry: ToolRegistry):
        """TR-041: 并发工具执行"""
        results = await asyncio.gather(*[
            registry.execute("read_file", {"file_path": "main.md"})
            for _ in range(10)
        ])
        for r in results:
            assert not r.is_error

    @pytest.mark.asyncio
    async def test_tr042_grep_truncation(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-042: grep 返回截断"""
        big = temp_workspace / "many_lines.txt"
        big.write_text("\n".join(f"match_line_{i}" for i in range(300)), encoding="utf-8")
        result = await registry.execute("grep_files", {"pattern": "match", "path": "many_lines.txt"})
        assert not result.is_error
        assert "truncated" in result.output

    @pytest.mark.asyncio
    async def test_tr042b_grep_truncation_large(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-042b: grep 10000 行截断"""
        big = temp_workspace / "huge.txt"
        lines = [f"match_line_{i}" for i in range(10000)]
        big.write_text("\n".join(lines), encoding="utf-8")
        result = await registry.execute("grep_files", {"pattern": "match", "path": "."})
        assert not result.is_error
        assert "truncated" in result.output


# ============================================================================
# 3.5 故障注入
# ============================================================================

class TestFaultInjection:

    @pytest.mark.asyncio
    async def test_tr050_file_deleted_mid_op(self, registry: ToolRegistry, temp_workspace: Path):
        """TR-050: 文件读取中途被删 — 不崩溃"""
        (temp_workspace / "ephemeral.txt").write_text("data", encoding="utf-8")
        (temp_workspace / "ephemeral.txt").unlink()
        result = await registry.execute("read_file", {"file_path": "ephemeral.txt"})
        assert result.is_error

    @pytest.mark.asyncio
    async def test_tr053_tool_throws_unexpected(self):
        """TR-053: 工具抛出未预期异常"""
        reg = ToolRegistry()
        async def boom(args):
            raise RuntimeError("unexpected boom")
        reg.register("boom", "Explodes", {}, func=boom)
        result = await reg.execute("boom", {})
        assert result.is_error
        assert "boom" in result.output
