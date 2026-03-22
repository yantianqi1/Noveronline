"""组织候选名称过滤规则。"""

MAX_ORG_NAME_LENGTH = 6
ORG_INVALID_CHARS = "在的了他她我你只为来自每个都前后里们也"
AMBIGUOUS_MEETING_PREFIXES = tuple("不也怎偶可会一有如机学教感")
DYNASTY_LEADING_CHARS = set("大前后新北南东中西天皇王武宋唐汉周梁楚晋燕魏吴秦隋元明清夏辽金靖")


def is_valid_org_candidate(name: str) -> bool:
    if len(name) < 2 or len(name) > MAX_ORG_NAME_LENGTH:
        return False
    if any(char in name for char in ORG_INVALID_CHARS):
        return False
    if name.endswith("会") and name[0] in AMBIGUOUS_MEETING_PREFIXES:
        return False
    if name.endswith("朝") and name[0] not in DYNASTY_LEADING_CHARS:
        return False
    return True
