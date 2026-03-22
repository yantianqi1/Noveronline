"""
剧情灵感生成服务
基于项目种子、世界线状态与创作者提示，输出可继续写作的剧情推进建议。
"""

from typing import Any, Dict, List


class PlotInspirationEngine:
    def generate(
        self,
        focus_question: str,
        branch_summary: Dict[str, Any],
        creator_prompt: str,
        variables: List[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
        actors: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        lead_characters = list(actors.keys())[:4]
        variable_names = [item.get("name", "") for item in variables[:3] if item.get("name")]
        event_titles = [item.get("title", "") for item in recent_events[:3] if item.get("title")]

        overview = (
            f"这条世界线当前围绕“{focus_question or branch_summary.get('core_change', '主线冲突')}”推进。"
            f"创作者新注入的灵感是“{creator_prompt.strip()}”。"
        )

        next_beats = [
            f"让{lead_characters[0] if lead_characters else '主角'}先做出一个不可逆的选择，把灵感落到行动层。",
            f"把“{branch_summary.get('core_change', '核心偏移')}”转成一次公开冲突，迫使各方表态。",
            f"利用{lead_characters[1] if len(lead_characters) > 1 else '关键配角'}制造误判，让关系网络出现新的裂痕。",
            f"在一个看似平静的场景里揭露隐藏代价，把故事拉入下一幕。",
        ]

        conflict_upgrades = [
            f"把变量 {name} 推到极端后，观察阵营是否重新洗牌。"
            for name in variable_names
        ] or ["扩大信息差，让角色在错误认知下做出关键决策。"]

        parallel_hooks = [
            f"如果沿着“{title}”继续推进，可额外分出一条更黑暗的支线。"
            for title in event_titles
        ] or ["把当前分支再切出一条“主角主动暴露底牌”的世界线。"]

        character_pressure_points = []
        for name, state in list(actors.items())[:4]:
            character_pressure_points.append({
                "character": name,
                "pressure": state.get("tension") or state.get("drive") or "局势迫使其重新选择站位",
            })

        return {
            "overview": overview,
            "next_beats": next_beats[:4],
            "conflict_upgrades": conflict_upgrades[:4],
            "parallel_world_hooks": parallel_hooks[:4],
            "character_pressure_points": character_pressure_points,
            "recommended_pov": lead_characters[:2] or ["主角"],
        }
