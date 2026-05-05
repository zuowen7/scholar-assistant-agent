"""数据可用性声明 — 借鉴 nature-data 的 FAIR 数据实践。

帮助用户为期刊投稿准备合规的 Data Availability 声明。
支持中→英精确术语转换和 FAIR 元数据检查。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class AccessRoute(str, Enum):
    PUBLIC_REPO = "public_repository"
    CONTROLLED_ACCESS = "controlled_access"
    WITHIN_PAPER = "within_paper_or_supplement"
    REUSED_PUBLIC = "reused_public"
    THIRD_PARTY = "third_party_restricted"
    ON_REQUEST = "available_on_request"
    NOT_APPLICABLE = "not_applicable"


@dataclass
class DatasetInfo:
    """单个数据集信息"""
    name: str = ""
    access_route: AccessRoute = AccessRoute.NOT_APPLICABLE
    repository: str = ""          # 仓库名称
    identifier: str = ""           # DOI / accession / 永久链接
    description: str = ""          # 内容简述
    license_info: str = ""         # 许可信息
    restriction_reason: str = ""   # 限制原因（如有）
    access_contact: str = ""       # 申请联系方式（如有）


@dataclass
class DataAvailabilityResult:
    """数据可用性声明结果"""
    statement: str = ""            # 提交就绪的英文声明
    repository_actions: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    cn_checks: list[str] = field(default_factory=list)   # 中文核对项
    fair_score: int = 0            # FAIR 评分 (0-100)


# ── 中→英术语映射 ─────────────────────────────────────────────────────────────

_CN2EN_TERMS: dict[str, str] = {
    "原始数据": "raw data",
    "处理后数据": "processed data",
    "源数据": "source data",
    "补充材料": "Supplementary Information",
    "受限数据": "restricted data",
    "合理请求": "reasonable request",
    "数据可用性声明": "Data Availability",
    "可向通讯作者索取": "available from the corresponding author upon reasonable request",  # 需要弱化
    "数据获取声明": "Data Availability Statement",
    "公开数据": "publicly available data",
    "数据集": "dataset",
    "仓库": "repository",
    "登录号": "accession number",
    "伦理审批": "ethics approval",
    "知情同意": "informed consent",
    "数据使用协议": "data use agreement",
}

# ── 声明模板 ──────────────────────────────────────────────────────────────────

_STATEMENT_TEMPLATES: dict[AccessRoute, str] = {
    AccessRoute.PUBLIC_REPO: (
        "The {data_type} data supporting the findings of this study are available in "
        "{repository} under accession {identifier}. The deposited record contains "
        "{description}."
    ),
    AccessRoute.CONTROLLED_ACCESS: (
        "The {data_type} data supporting this study are not publicly available due to "
        "{restriction_reason}. A metadata record is available at {repository} under "
        "{identifier}. Qualified researchers may request access from {access_contact}. "
        "Access requires {conditions} and will be reviewed according to {policy}."
    ),
    AccessRoute.WITHIN_PAPER: (
        "All data supporting the findings of this study are included in the paper, "
        "its Supplementary Information, and Source Data files."
    ),
    AccessRoute.REUSED_PUBLIC: (
        "This study used publicly available {data_type} from {repository}, available "
        "under {identifier}. No new primary data were generated for this analysis."
    ),
    AccessRoute.THIRD_PARTY: (
        "The {data_type} data used in this study were obtained from {repository} under "
        "licence and are not publicly redistributable by the authors. Requests for access "
        "should be directed to {access_contact}."
    ),
    AccessRoute.ON_REQUEST: (
        "The data that support the findings of this study are available from "
        "{access_contact} upon reasonable request. {conditions}"
    ),
    AccessRoute.NOT_APPLICABLE: (
        "Data sharing is not applicable to this article as no datasets were generated "
        "or analysed during the current study."
    ),
}


def translate_cn_availability(text: str) -> str:
    """将中文数据可用性描述转换为精确的英文术语。

    Args:
        text: 中文描述文本

    Returns:
        翻译后的英文文本
    """
    result = text
    for cn, en in _CN2EN_TERMS.items():
        result = result.replace(cn, en)
    return result


def generate_statement(datasets: list[DatasetInfo]) -> DataAvailabilityResult:
    """从数据集列表生成 Data Availability 声明。

    Args:
        datasets: 数据集信息列表

    Returns:
        DataAvailabilityResult 包含声明文本和待确认事项
    """
    result = DataAvailabilityResult()
    parts: list[str] = []

    for ds in datasets:
        template = _STATEMENT_TEMPLATES.get(ds.access_route, "")
        if not template:
            continue

        # 填充模板字段
        data_type = ds.description or ds.name or "data"
        statement = template.format(
            data_type=data_type,
            repository=ds.repository or "[repository name required]",
            identifier=ds.identifier or "[DOI/accession required]",
            description=ds.description or "[brief contents description]",
            restriction_reason=ds.restriction_reason or "[reason required]",
            access_contact=ds.access_contact or "[contact or URL required]",
            conditions="[access conditions]",
            policy="[review policy]",
        )
        parts.append(statement)

        # 检查缺失字段
        if not ds.repository and ds.access_route in (
            AccessRoute.PUBLIC_REPO,
            AccessRoute.CONTROLLED_ACCESS,
            AccessRoute.THIRD_PARTY,
        ):
            result.missing_fields.append(
                f"数据集 '{ds.name}' 缺少仓库名称"
            )
        if not ds.identifier and ds.access_route in (
            AccessRoute.PUBLIC_REPO,
            AccessRoute.REUSED_PUBLIC,
        ):
            result.missing_fields.append(
                f"数据集 '{ds.name}' 缺少 DOI/登录号"
            )
        if not ds.restriction_reason and ds.access_route == AccessRoute.CONTROLLED_ACCESS:
            result.missing_fields.append(
                f"数据集 '{ds.name}' 缺少限制原因"
            )
        if not ds.access_contact and ds.access_route in (
            AccessRoute.CONTROLLED_ACCESS,
            AccessRoute.THIRD_PARTY,
            AccessRoute.ON_REQUEST,
        ):
            result.missing_fields.append(
                f"数据集 '{ds.name}' 缺少申请联系方式"
            )

        # 弱表述检测
        if "upon reasonable request" in statement and not ds.restriction_reason:
            result.cn_checks.append(
                f"数据集 '{ds.name}' 使用了 'reasonable request'，"
                "请确认是否因法律/伦理/商业限制而不能公开数据"
            )

    result.statement = "\n\n".join(parts) if parts else "## Data Availability\n\n待填写。"
    result.repository_actions = _generate_repository_actions(datasets)

    # FAIR 评分
    result.fair_score = _calculate_fair_score(datasets)

    return result


def _generate_repository_actions(datasets: list[DatasetInfo]) -> list[str]:
    """生成仓库操作建议"""
    actions: list[str] = []
    for ds in datasets:
        if ds.access_route in (AccessRoute.PUBLIC_REPO, AccessRoute.CONTROLLED_ACCESS):
            actions.append(
                f"上传 {ds.name} 到 {ds.repository or '[待选仓库]'}，获取 DOI/登录号"
            )
        if ds.access_route == AccessRoute.CONTROLLED_ACCESS:
            actions.append(
                f"为 {ds.name} 准备元数据记录（不含敏感数据）"
            )
    return actions


def _calculate_fair_score(datasets: list[DatasetInfo]) -> int:
    """计算简化的 FAIR 评分"""
    if not datasets:
        return 0

    score = 0
    for ds in datasets:
        # Findable: 是否有持久标识符
        if ds.identifier:
            score += 25
        # Accessible: 是否可通过标准协议访问
        if ds.repository:
            score += 25
        # Interoperable: 是否有标准格式描述
        if ds.description:
            score += 15
        # Reusable: 是否有许可信息
        if ds.license_info:
            score += 15
        # 公开可访问加分
        if ds.access_route == AccessRoute.PUBLIC_REPO:
            score += 20

    return min(100, score // max(len(datasets), 1))


def format_data_availability_section(
    statement_text: str = "",
    datasets: list[DatasetInfo] | None = None,
    output_format: str = "nature",
) -> str:
    """生成完整的 Data Availability 章节（含中英双语核对）。

    Args:
        statement_text: 已有的声明文本（可选，用于审核）
        datasets: 数据集列表（可选，用于生成新声明）
        output_format: 输出格式（nature / general）

    Returns:
        格式化的 Data Availability 章节
    """
    lines: list[str] = []
    lines.append("## Data Availability")

    if datasets:
        result = generate_statement(datasets)
        lines.append("")
        lines.append(result.statement)
        lines.append("")

        if result.repository_actions:
            lines.append("### Repository and Citation Actions")
            for action in result.repository_actions:
                lines.append(f"- {action}")
            lines.append("")

        if result.missing_fields:
            lines.append("### Missing Information / Risk Flags")
            for field in result.missing_fields:
                lines.append(f"- [ ] {field}")
            lines.append("")

        if result.cn_checks:
            lines.append("### 中文核对")
            for check in result.cn_checks:
                lines.append(f"- {check}")
            lines.append("")

        lines.append(f"**FAIR Score**: {result.fair_score}/100")
    elif statement_text:
        lines.append("")
        lines.append(statement_text)
    else:
        lines.append("")
        lines.append("Data sharing is not applicable to this article as no datasets "
                     "were generated or analysed during the current study.")

    return "\n".join(lines)
