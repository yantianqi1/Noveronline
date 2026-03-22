"""
平行世界配置生成器
用于把小说种子、角色网络和用户变量，转换为可推演的世界分支配置。
"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter
from .zep_entity_reader import EntityNode


PARALLEL_WORLD_SYSTEM_PROMPT = """你是一位小说策划编辑、叙事导演和平行世界推演设计师。

请根据故事目标、角色网络和变量，生成一个适合做剧情分支模拟的配置。

输出严格 JSON：
{
  "simulation_goal": "中文，一句话说明这次推演要观察什么",
  "world_variables": [
    {
      "name": "变量名",
      "description": "变量描述",
      "impact_axis": "它主要影响哪条剧情轴"
    }
  ],
  "branch_hypotheses": [
    {
      "branch_id": "branch_1",
      "title": "分支标题",
      "core_change": "该世界线和原世界相比最大的变化",
      "key_agents": ["角色A", "组织B"],
      "expected_conflicts": ["冲突1", "冲突2"],
      "narrative_value": "这个分支能带来什么创作价值"
    }
  ],
  "timeline_focus": [
    "最该观察的剧情阶段1",
    "最该观察的剧情阶段2"
  ],
  "agent_behavior_axes": [
    "角色在推演时应围绕什么行为轴行动"
  ]
}
"""


@dataclass
class StoryVariable:
    name: str
    description: str
    impact_axis: str = ""


@dataclass
class WorldBranch:
    branch_id: str
    title: str
    core_change: str
    key_agents: List[str] = field(default_factory=list)
    expected_conflicts: List[str] = field(default_factory=list)
    narrative_value: str = ""


@dataclass
class ParallelWorldConfig:
    simulation_goal: str
    world_variables: List[StoryVariable]
    branch_hypotheses: List[WorldBranch]
    timeline_focus: List[str]
    agent_behavior_axes: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "simulation_goal": self.simulation_goal,
            "world_variables": [asdict(v) for v in self.world_variables],
            "branch_hypotheses": [asdict(b) for b in self.branch_hypotheses],
            "timeline_focus": self.timeline_focus,
            "agent_behavior_axes": self.agent_behavior_axes,
            "generated_at": self.generated_at,
        }


class ParallelWorldConfigGenerator:
    """生成小说平行世界推演配置。"""

    MODULE_KEY = "parallel_world_config"

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()

    def generate(
        self,
        analysis_goal: str,
        entities: List[EntityNode],
        variables: Optional[List[Any]] = None,
        branch_count: Optional[int] = None,
        use_llm: bool = True,
    ) -> ParallelWorldConfig:
        branch_count = branch_count or Config.NARRATIVE_DEFAULT_BRANCH_COUNT
        variables = variables or []

        entity_lines = []
        for entity in entities[:60]:
            entity_type = entity.get_entity_type() or "Unknown"
            entity_lines.append(f"- {entity.name} [{entity_type}]: {entity.summary[:180]}")

        variable_lines = []
        for item in variables:
            if isinstance(item, str):
                text = item.strip()
                if not text:
                    continue
                variable_lines.append(f"- {text}: {text}")
                continue
            variable_lines.append(f"- {item.get('name', '未命名变量')}: {item.get('description', '')}")

        user_message = f"""## 分析目标
{analysis_goal}

## 核心实体
{chr(10).join(entity_lines)}

## 用户注入变量
{chr(10).join(variable_lines) if variable_lines else "暂无，默认按原小说世界线轻微偏移生成分支"}

## 分支数量
{branch_count}
"""

        if not use_llm:
            result = self._build_offline_result(analysis_goal, entities, variables, branch_count)
        else:
            client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
            result = client.chat_json_value(
                messages=[
                    {"role": "system", "content": PARALLEL_WORLD_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.6,
                max_tokens=2200,
            )
            result = normalize_json_object(result, "平行世界配置生成")

        parsed_variables = [
            StoryVariable(
                name=item.get("name", ""),
                description=item.get("description", ""),
                impact_axis=item.get("impact_axis", ""),
            )
            for item in result.get("world_variables", [])
        ]

        parsed_branches = [
            WorldBranch(
                branch_id=item.get("branch_id", f"branch_{idx + 1}"),
                title=item.get("title", f"平行世界 {idx + 1}"),
                core_change=item.get("core_change", ""),
                key_agents=item.get("key_agents", []),
                expected_conflicts=item.get("expected_conflicts", []),
                narrative_value=item.get("narrative_value", ""),
            )
            for idx, item in enumerate(result.get("branch_hypotheses", []))
        ]

        return ParallelWorldConfig(
            simulation_goal=result.get("simulation_goal", analysis_goal),
            world_variables=parsed_variables,
            branch_hypotheses=parsed_branches,
            timeline_focus=result.get("timeline_focus", []),
            agent_behavior_axes=result.get("agent_behavior_axes", []),
        )

    def _build_offline_result(
        self,
        analysis_goal: str,
        entities: List[EntityNode],
        variables: List[Any],
        branch_count: int,
    ) -> Dict[str, Any]:
        normalized_variables = []
        for idx, item in enumerate(variables[:5], start=1):
            if isinstance(item, str):
                normalized_variables.append({
                    "name": item[:24] or f"变量{idx}",
                    "description": item,
                    "impact_axis": "剧情偏移",
                })
            else:
                normalized_variables.append({
                    "name": item.get("name", f"变量{idx}"),
                    "description": item.get("description", ""),
                    "impact_axis": item.get("impact_axis", "剧情偏移"),
                })

        key_agents = [entity.name for entity in entities[:4]]
        branch_hypotheses = []
        for idx in range(branch_count):
            variable_name = normalized_variables[idx % len(normalized_variables)]["name"] if normalized_variables else f"变量{idx + 1}"
            branch_hypotheses.append({
                "branch_id": f"branch_{idx + 1}",
                "title": f"平行世界 {idx + 1}",
                "core_change": f"{variable_name} 在关键节点被放大，引发局势重排",
                "key_agents": key_agents[:3],
                "expected_conflicts": ["关系网络重新洗牌", "组织站位发生变化"],
                "narrative_value": "适合继续推进剧情创作与角色关系推演",
            })

        return {
            "simulation_goal": analysis_goal,
            "world_variables": normalized_variables,
            "branch_hypotheses": branch_hypotheses,
            "timeline_focus": ["起因暴露", "联盟重组", "代价兑现"],
            "agent_behavior_axes": ["角色目标", "关系压力", "组织利益", "信息差"],
        }
