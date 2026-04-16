"""统一资产库（Asset Library）— 全局 + 项目双层存储，FTS5 全文检索，
可被任意 agent 通过工具调用。承载文风/世界观/角色原型/提示词模板/manuscript 等。"""

from .assets_service import AssetsService, GLOBAL_SCOPE, PROJECT_SCOPE

__all__ = ["AssetsService", "GLOBAL_SCOPE", "PROJECT_SCOPE"]
