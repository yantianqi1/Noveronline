"""小说流派插件。"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple


DEFAULT_CHARACTER_STOP_WORDS = frozenset(
    {
        "自己", "众人", "他们", "她们", "我们", "你们", "这里", "那里", "今天", "昨日",
        "此刻", "时候", "事情", "声音", "目光", "灵气", "真相", "命运", "秘密", "夜色",
        "清晨", "午后", "傍晚", "长夜", "少年人", "少女们", "一人", "两人", "三人", "四人",
    }
)

DEFAULT_ORG_SUFFIX_TO_TYPE = {
    "宗门": "sect",
    "宗": "sect",
    "门": "sect",
    "派": "school",
    "阁": "organization",
    "殿": "organization",
    "宫": "organization",
    "司": "bureau",
    "局": "bureau",
    "会": "association",
    "盟": "alliance",
    "团": "group",
    "府": "house",
    "国": "kingdom",
    "朝": "dynasty",
    "城": "city",
    "院": "academy",
    "堂": "hall",
    "坊": "guild",
    "书院": "academy",
    "学宫": "academy",
    "公司": "company",
    "集团": "company",
    "财团": "consortium",
}

DEFAULT_RELATION_KEYWORDS = {
    "family": ("父亲", "母亲", "兄长", "妹妹", "姐姐", "弟弟", "叔父", "族兄", "族妹"),
    "ally": ("联手", "结盟", "合作", "帮助", "救下", "信任", "同行", "庇护"),
    "conflict": ("追杀", "怀疑", "敌视", "争执", "刺杀", "背叛", "对峙", "威胁", "镇压"),
    "affiliation": ("隶属", "出身", "来自", "门下", "弟子", "供职", "归于", "效忠"),
    "command": ("命令", "掌管", "统领", "召见", "调遣", "差遣"),
    "mentor": ("师父", "师徒", "传授", "收徒"),
}


class GenrePlugin:
    genre_id = "default"
    genre_name = "通用"

    def get_character_stop_words(self) -> set[str]:
        return set()

    def get_organization_suffixes(self) -> Dict[str, str]:
        return {}

    def get_relation_keywords(self) -> Dict[str, Tuple[str, ...]]:
        return {}

    def customize_agent_schema(self, registry) -> None:
        return None


class WuxiaPlugin(GenrePlugin):
    genre_id = "wuxia"
    genre_name = "武侠"

    def get_character_stop_words(self) -> set[str]:
        return {"内力", "掌风", "刀气"}

    def get_organization_suffixes(self) -> Dict[str, str]:
        return {"山庄": "estate", "镖局": "bureau", "帮": "gang"}

    def get_relation_keywords(self) -> Dict[str, Tuple[str, ...]]:
        return {"ally": ("结拜", "义结金兰", "并肩", "同闯")}

    def customize_agent_schema(self, registry) -> None:
        registry.register_schema(
            "character",
            {
                "martial_art": {"type": "str", "label": "武学体系", "required": False},
                "jianghu_reputation": {"type": "str", "label": "江湖声望", "required": False},
            },
        )
        registry.register_schema(
            "organization",
            {
                "territory_routes": {"type": "list", "label": "地盘与线路", "required": False},
            },
        )


class XianxiaPlugin(GenrePlugin):
    genre_id = "xianxia"
    genre_name = "仙侠"

    def get_character_stop_words(self) -> set[str]:
        return {"真元", "元神", "仙骨"}

    def get_organization_suffixes(self) -> Dict[str, str]:
        return {"仙门": "sect", "洞天": "realm", "福地": "realm"}

    def get_relation_keywords(self) -> Dict[str, Tuple[str, ...]]:
        return {"mentor": ("收徒", "传功", "点化"), "ally": ("共修", "护道")}

    def customize_agent_schema(self, registry) -> None:
        registry.register_schema(
            "character",
            {
                "cultivation_stage": {"type": "str", "label": "修为境界", "required": False},
                "dao_heart": {"type": "str", "label": "道心状态", "required": False},
            },
        )
        registry.register_schema(
            "organization",
            {
                "spirit_vein": {"type": "str", "label": "灵脉根基", "required": False},
            },
        )


class SciFiPlugin(GenrePlugin):
    genre_id = "scifi"
    genre_name = "科幻"

    def get_character_stop_words(self) -> set[str]:
        return {"算法", "协议", "模块"}

    def get_organization_suffixes(self) -> Dict[str, str]:
        return {"舰队": "fleet", "实验室": "lab", "站": "station"}

    def get_relation_keywords(self) -> Dict[str, Tuple[str, ...]]:
        return {"command": ("下达指令", "远程调度", "授权"), "ally": ("数据共享", "协同接入")}

    def customize_agent_schema(self, registry) -> None:
        registry.register_schema(
            "character",
            {
                "augmentation": {"type": "str", "label": "义体改造", "required": False},
                "clearance": {"type": "str", "label": "权限等级", "required": False},
            },
        )
        registry.register_schema(
            "organization",
            {
                "infrastructure": {"type": "list", "label": "基础设施", "required": False},
                "research_focus": {"type": "str", "label": "研究方向", "required": False},
            },
        )


GENRE_PLUGINS = {
    "default": GenrePlugin(),
    "wuxia": WuxiaPlugin(),
    "xianxia": XianxiaPlugin(),
    "scifi": SciFiPlugin(),
}


def resolve_genre_plugin(genre: str | GenrePlugin | None = None) -> GenrePlugin:
    if isinstance(genre, GenrePlugin):
        return genre
    key = (genre or "default").strip().lower()
    return GENRE_PLUGINS.get(key, GENRE_PLUGINS["default"])


def merge_relation_keywords(*sources: Dict[str, Iterable[str]]) -> Dict[str, Tuple[str, ...]]:
    merged: Dict[str, list[str]] = {}
    for source in sources:
        for relation_type, keywords in source.items():
            bucket = merged.setdefault(relation_type, [])
            for keyword in keywords:
                if keyword not in bucket:
                    bucket.append(keyword)
    return {key: tuple(value) for key, value in merged.items()}
