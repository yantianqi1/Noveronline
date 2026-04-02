"""世界线 Agent 字段结构注册表。"""

from __future__ import annotations

import copy
from typing import Any, Dict, List


BASE_AGENT_SCHEMA = {
    "drive": {"type": "str", "label": "核心驱动力", "required": True},
    "tension": {"type": "str", "label": "内在张力", "required": True},
    "role": {"type": "str", "label": "角色定位", "required": True},
    "status": {"type": "str", "label": "当前状态", "required": True},
}

CHARACTER_EXTENSIONS = {
    "personality": {"type": "str", "label": "性格底色", "required": False},
    "skills": {"type": "list", "label": "关键能力", "required": False},
    "loyalty": {"type": "str", "label": "忠诚指向", "required": False},
    "secrets": {"type": "list", "label": "隐藏秘密", "required": False},
}

ORGANIZATION_EXTENSIONS = {
    "resources": {"type": "list", "label": "核心资源", "required": False},
    "internal_factions": {"type": "list", "label": "内部派系", "required": False},
    "territorial_control": {"type": "str", "label": "势力范围", "required": False},
    "public_stance": {"type": "str", "label": "公开立场", "required": False},
}

RELATIONSHIP_EXTENSIONS = {
    "history": {"type": "str", "label": "关系历史", "required": False},
    "power_dynamic": {"type": "str", "label": "权力动态", "required": False},
    "trust_level": {"type": "str", "label": "信任程度", "required": False},
}

DEFAULT_AGENT_SCHEMAS = {
    "character": {**BASE_AGENT_SCHEMA, **CHARACTER_EXTENSIONS},
    "organization": {**BASE_AGENT_SCHEMA, **ORGANIZATION_EXTENSIONS},
    "relationship": {**BASE_AGENT_SCHEMA, **RELATIONSHIP_EXTENSIONS},
}


class AgentSchemaRegistry:
    """管理不同 Agent 类型的字段结构定义。"""

    def __init__(self, base_schemas: Dict[str, Dict[str, Dict[str, Any]]] | None = None):
        self._schemas = copy.deepcopy(base_schemas or DEFAULT_AGENT_SCHEMAS)

    def register_schema(self, agent_type: str, extensions: Dict[str, Dict[str, Any]]) -> None:
        schema = self._schemas.setdefault(agent_type, copy.deepcopy(BASE_AGENT_SCHEMA))
        schema.update(copy.deepcopy(extensions))

    def get_schema(self, agent_type: str) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(self._schemas.get(agent_type, BASE_AGENT_SCHEMA))

    def validate_state(self, agent_type: str, state: Dict[str, Any]) -> List[str]:
        errors = []
        schema = self.get_schema(agent_type)
        for field_name, config in schema.items():
            if config.get("required") and field_name not in state:
                errors.append(f"{agent_type}.{field_name} 缺失")
                continue
            if field_name not in state:
                continue
            if not self._matches_type(config.get("type", "str"), state[field_name]):
                errors.append(f"{agent_type}.{field_name} 类型无效，应为 {config.get('type', 'str')}")
        return errors

    def _matches_type(self, expected: str, value: Any) -> bool:
        checks = {
            "str": lambda item: isinstance(item, str),
            "list": lambda item: isinstance(item, list),
            "dict": lambda item: isinstance(item, dict),
            "number": lambda item: isinstance(item, (int, float)),
            "float": lambda item: isinstance(item, (int, float)),
            "bool": lambda item: isinstance(item, bool),
        }
        return checks.get(expected, lambda item: True)(value)
