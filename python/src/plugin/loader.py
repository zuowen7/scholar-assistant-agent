"""Plugin Loader — 动态发现和加载自定义插件。

支持两种加载方式：
1. **目录扫描**：扫描 `plugins/` 目录，自动发现并注册所有插件
2. **配置文件**：通过 `plugins.yaml` 声明要加载的插件和参数

目录结构约定：

    plugins/
    ├── my_tool.py          # 单文件插件（提供 ToolSpec 列表）
    ├── my_server/           # 目录插件
    │   ├── __init__.py     # 必须导出 get_server() 函数
    │   └── config.yaml      # 可选配置文件
    └── disabled_server.py  # 以 disabled_ 前缀开头则跳过

每个插件必须提供：
- `get_server() -> PluginServer` 函数，或
- `PLUGIN_SERVER: PluginServer` 变量

用 YAML 配置加载（可选）：

    plugins:
      - name: my_arxiv
        path: plugins/my_arxiv.py
        enabled: true
        config:
          max_results: 10
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 插件发现目录（相对于 RUNTIME_DIR）
DEFAULT_PLUGIN_DIR = "plugins"


def _load_plugin_from_file(file_path: Path) -> PluginServer | None:
    """从 Python 文件加载插件。

    支持两种导出方式：
    1. get_server() -> PluginServer 函数
    2. PLUGIN_SERVER: PluginServer 变量
    """
    try:
        spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
        if spec is None or spec.loader is None:
            logger.warning("无法加载插件文件: %s", file_path)
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 优先查找 get_server 函数
        if hasattr(module, "get_server"):
            server = module.get_server()
            if not isinstance(server, PluginServer):
                logger.error("插件 %s 的 get_server() 返回值不是 PluginServer", file_path)
                return None
            return server

        # 其次查找 PLUGIN_SERVER 变量
        if hasattr(module, "PLUGIN_SERVER"):
            server = module.PLUGIN_SERVER
            if not isinstance(server, PluginServer):
                logger.error("插件 %s 的 PLUGIN_SERVER 不是 PluginServer", file_path)
                return None
            return server

        logger.warning("插件文件 %s 未导出 get_server() 或 PLUGIN_SERVER", file_path)
        return None

    except Exception as e:
        logger.exception("加载插件 %s 失败: %s", file_path, e)
        return None


def _load_plugin_from_dir(dir_path: Path) -> PluginServer | None:
    """从目录加载插件（目录需有 __init__.py）。"""
    init_file = dir_path / "__init__.py"
    if not init_file.exists():
        logger.warning("插件目录 %s 缺少 __init__.py", dir_path)
        return None
    return _load_plugin_from_file(init_file)


def discover_plugins(plugin_dir: Path) -> list[PluginServer]:
    """扫描目录，发现并加载所有插件。

    Args:
        plugin_dir: 插件目录路径

    Returns:
        已成功加载的 PluginServer 列表
    """
    if not plugin_dir.exists():
        logger.info("插件目录不存在，跳过扫描: %s", plugin_dir)
        return []

    servers = []
    loaded_names: set[str] = set()

    for entry in sorted(plugin_dir.iterdir()):
        name = entry.name

        # 跳过禁用/隐藏文件
        if name.startswith("disabled_") or name.startswith("."):
            logger.debug("跳过禁用插件: %s", name)
            continue

        if not (name.endswith(".py") or entry.is_dir()):
            continue

        # 跳过 __pycache__ 等
        if name.startswith("__"):
            continue

        server: PluginServer | None = None

        if entry.is_dir():
            server = _load_plugin_from_dir(entry)
        elif entry.suffix == ".py":
            server = _load_plugin_from_file(entry)

        if server is not None:
            if server.name in loaded_names:
                logger.warning("插件名 %s 重复（来自 %s），跳过", server.name, entry)
                continue
            servers.append(server)
            loaded_names.add(server.name)
            logger.info("插件已发现: %s v%s (%s)", server.name, server.version, entry)

    return servers


def load_from_config(config_path: Path) -> list[dict[str, Any]]:
    """从 YAML 配置文件加载插件声明。

    配置文件格式：
        plugins:
          - name: arxiv
            path: plugins/arxiv.py
            enabled: true
          - name: custom
            path: plugins/custom_server/
            enabled: false
    """
    if not config_path.exists():
        return []

    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        plugins = config.get("plugins", [])
        return [p for p in plugins if p.get("enabled", True)]
    except Exception as e:
        logger.warning("加载插件配置 %s 失败: %s", config_path, e)
        return []


def load_plugins(registry: PluginRegistry, plugin_dir: Path | None = None) -> None:
    """自动发现并注册所有插件到注册表。

    加载顺序：
    1. 扫描 plugin_dir 下所有 .py 文件和子目录
    2. 配置文件 plugins.yaml 控制的插件
    3. 内置插件（builtin.py）

    Args:
        registry: 目标注册表
        plugin_dir: 插件目录，默认 RUNTIME_DIR/plugins
    """
    if plugin_dir is None:
        # 尝试使用 RUNTIME_DIR
        try:
            from api_factory import RUNTIME_DIR
            plugin_dir = RUNTIME_DIR / DEFAULT_PLUGIN_DIR
        except ImportError:
            logger.warning("无法导入 RUNTIME_DIR，插件目录扫描跳过")
            return

    # 步骤 1：自动发现
    discovered = discover_plugins(plugin_dir)
    for server in discovered:
        registry.register(server)

    # 步骤 2：配置文件控制（可选）
    config_path = plugin_dir.parent / "plugins.yaml"
    if config_path.exists():
        declarations = load_from_config(config_path)
        for decl in declarations:
            path = decl.get("path", "")
            if not path:
                continue
            server_path = (plugin_dir.parent / path).resolve()
            if not server_path.exists():
                logger.warning("配置文件声明的插件不存在: %s", server_path)
                continue
            server: PluginServer | None = None
            if server_path.is_dir():
                server = _load_plugin_from_dir(server_path)
            else:
                server = _load_plugin_from_file(server_path)
            if server and decl.get("enabled", True):
                registry.register(server)
                logger.info("配置加载: %s (%s)", server.name, path)

    logger.info("插件扫描完成: %s", registry.get_stats())
