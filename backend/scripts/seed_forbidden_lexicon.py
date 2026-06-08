"""Seed a GLOBAL forbidden-lexicon asset from the 小说梦想家 BANNED_PHRASES.md ruleset.

Creates ONE global `forbidden_lexicon` asset (scope=global, enabled=True) whose
entries are the 小说梦想家 禁词/禁句式 rules. Once seeded, every project's
`scan_forbidden_lexicon` / `lexicon_cleaner` one-click / book_run LEXICON_AUDIT
picks it up automatically (via AssetsService.list_merged merging project + global).

Scope/intent:
- Rules are the source author's hard stylistic preferences (anti-AI-flavor).
- It is opt-out per project: disable the asset in the assets UI if a project
  doesn't want it. Scanning only runs on explicit actions (one-click / book_run
  audit), never silently on every generation.
- The punctuation rules (full-width parens / em-dash) are aggressive and faithful
  to the source author; remove those two entries if undesired.

Idempotent — skips if a global forbidden_lexicon asset with the same title exists.

Run from the backend/ directory:
    .venv/bin/python scripts/seed_forbidden_lexicon.py
    # or
    uv run python scripts/seed_forbidden_lexicon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.asset_types import AssetType  # noqa: E402
from app.services.assets.assets_service import GLOBAL_SCOPE, AssetsService  # noqa: E402

ASSET_TITLE = "小说梦想家·禁词禁句式"
ASSET_SUMMARY = "中文网文反 AI 味禁词/禁句式规则库。来源：小说梦想家 BANNED_PHRASES.md。"

# entry: {pattern, match_type(literal|regex|phrase), category, severity(block|warn), note}
# severity: error -> block（命中必须改写）, warn -> warn（人工复查）
ENTRIES: list[dict] = [
    # ── 句式：对照/转折/递进 八股 ──
    {"pattern": r"不是[^。！？；\n]{0,40}而是", "match_type": "regex", "category": "句式", "severity": "block", "note": "老套对照句式，强八股味"},
    {"pattern": r"不是[^。！？；\n]{0,40}是", "match_type": "regex", "category": "句式", "severity": "block", "note": "不是X是Y解释纠偏句，议论文味"},
    {"pattern": r"与其[^。！？；\n]{0,40}不如", "match_type": "regex", "category": "句式", "severity": "block", "note": "老套对照句式，模板作文"},
    {"pattern": r"没有[^。！？；\n]{0,40}反而", "match_type": "regex", "category": "句式", "severity": "block", "note": "先否定再肯定，句式模板化"},
    # ── 句式：生硬时间/数字外形描写 ──
    {"pattern": r"[0-9一二三四五六七八九十几两]+秒过去了", "match_type": "regex", "category": "句式", "severity": "block", "note": "生硬时间提示，破坏沉浸"},
    {"pattern": r"[0-9一二三四五六七八九十几两]+分钟过去了", "match_type": "regex", "category": "句式", "severity": "block", "note": "生硬时间提示，破坏沉浸"},
    {"pattern": r"[0-9]{2,3}(cm|米|身高)", "match_type": "regex", "category": "句式", "severity": "block", "note": "具体数字硬描写外形，缺小说感"},
    {"pattern": r"[A-Za-z]罩杯", "match_type": "regex", "category": "句式", "severity": "block", "note": "字母/数字硬描写身体"},
    # ── 句式：结尾强行升华 ──（已 generalize 掉源小说人名）
    {"pattern": r"那一刻[^。！？；\n]{0,30}(明白了|终于明白|意识到)", "match_type": "regex", "category": "升华", "severity": "block", "note": "结尾强行升华模板"},
    # ── 套路化身体/表情描写 ──
    {"pattern": r"指节[^。！？；\n]{0,12}泛白", "match_type": "regex", "category": "套路描写", "severity": "block", "note": "指节泛白套路描写"},
    {"pattern": r"喉结[^。！？；\n]{0,20}(滚动|滑动|动了动|上下滚了滚)", "match_type": "regex", "category": "套路描写", "severity": "block", "note": "喉结套路描写"},
    {"pattern": r"(锁骨|肩胛骨|髂骨|耻骨|踝骨|腕骨|肋骨|盆骨)", "match_type": "regex", "category": "解剖术语", "severity": "block", "note": "正文专业术语过硬，要求口语化"},
    {"pattern": r"(一丝|一抹|一声|一个)[^，。！？；\n]{0,10}(笑意|寒意|暖意|杀意|怒意|讥诮|嘲弄|复杂|情绪|波动|意味)", "match_type": "regex", "category": "句式", "severity": "block", "note": "抽象名词前挂量词，空泛八股"},
    # ── 词汇：套板/油腻 ──
    {"pattern": "如蒙大赦", "match_type": "literal", "category": "词汇", "severity": "block", "note": "套板词，太旧"},
    {"pattern": "沙哑", "match_type": "literal", "category": "词汇", "severity": "block", "note": "高风险套路词（描述嗓音），换更自然表达"},
    {"pattern": "勾勒", "match_type": "literal", "category": "词汇", "severity": "block", "note": "高风险套板描写词"},
    {"pattern": "饱满的弧度", "match_type": "literal", "category": "词汇", "severity": "block", "note": "套路化身体描写"},
    {"pattern": "嘴角的弧度", "match_type": "literal", "category": "词汇", "severity": "block", "note": "套路化表情描写"},
    {"pattern": "充血肿胀", "match_type": "literal", "category": "词汇", "severity": "block", "note": "性描写专业腔，生硬出戏"},
    {"pattern": "猪肝色", "match_type": "literal", "category": "词汇", "severity": "block", "note": "套路化脸色描写"},
    {"pattern": "铁锈味", "match_type": "literal", "category": "词汇", "severity": "block", "note": "套路化气味描写"},
    {"pattern": "逼仄", "match_type": "literal", "category": "词汇", "severity": "block", "note": "过熟套词，易显做作"},
    {"pattern": "浮木", "match_type": "literal", "category": "词汇", "severity": "block", "note": "高风险万能意象词"},
    # ── 词汇：作者替读者下结论 ──
    {"pattern": "不容置疑", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "抽象判断，应用行动体现"},
    {"pattern": "不容置喙", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "抽象判断，应用行动体现"},
    {"pattern": "不可置信", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "套路化震惊表达"},
    {"pattern": "某种意义上", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "套话，削弱判断力"},
    {"pattern": "毫无疑问", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "作者替读者下结论"},
    {"pattern": "归根结底", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "总结腔，像分析文"},
    {"pattern": "不难看出", "match_type": "literal", "category": "判断腔", "severity": "block", "note": "作者讲解腔，破坏沉浸"},
    # ── 词汇：空泛指代 ──
    {"pattern": "那种", "match_type": "literal", "category": "空泛", "severity": "block", "note": "空泛指代，削弱具体性"},
    {"pattern": "那层", "match_type": "literal", "category": "空泛", "severity": "block", "note": "空泛指代，削弱具体性"},
    {"pattern": "这般", "match_type": "literal", "category": "空泛", "severity": "block", "note": "古早书面味，易出戏"},
    {"pattern": "如此", "match_type": "literal", "category": "空泛", "severity": "block", "note": "空泛判断，优先具体化"},
    # ── 标点：括号注释 / 破折号（源作者硬偏好，可按需删除这三条）──
    {"pattern": "（", "match_type": "literal", "category": "标点", "severity": "block", "note": "禁止括号注释，信息融入正文"},
    {"pattern": "）", "match_type": "literal", "category": "标点", "severity": "block", "note": "禁止括号注释，信息融入正文"},
    {"pattern": "——", "match_type": "literal", "category": "标点", "severity": "block", "note": "禁破折号旁白，改逗号或直接断句"},
    # ── warn 级：机械过渡/模糊/讲解腔（人工复查）──
    {"pattern": "后来", "match_type": "literal", "category": "过渡", "severity": "warn", "note": "机械过渡词，易写成流水账"},
    {"pattern": "接着", "match_type": "literal", "category": "过渡", "severity": "warn", "note": "机械过渡词，节奏生硬"},
    {"pattern": "随着", "match_type": "literal", "category": "过渡", "severity": "warn", "note": "空泛过渡，削弱现场感"},
    {"pattern": "仿佛", "match_type": "literal", "category": "模糊", "severity": "warn", "note": "空泛比喻高风险词，易偷懒"},
    {"pattern": "可以说", "match_type": "literal", "category": "判断腔", "severity": "warn", "note": "总结腔，脱离现场"},
    {"pattern": "显然", "match_type": "literal", "category": "判断腔", "severity": "warn", "note": "作者替读者判断"},
    {"pattern": "事实上", "match_type": "literal", "category": "判断腔", "severity": "warn", "note": "讲解腔，易出戏"},
    {"pattern": "某种感觉", "match_type": "literal", "category": "模糊", "severity": "warn", "note": "空泛情绪表达，信息量低"},
    {"pattern": "难以言喻", "match_type": "literal", "category": "模糊", "severity": "warn", "note": "空泛情绪标签，缺具象反应"},
]


def main() -> int:
    svc = AssetsService()

    existing = [
        a
        for a in svc.list_merged(
            project_id="__seed_probe__",
            asset_type=AssetType.FORBIDDEN_LEXICON.value,
            enabled_only=False,
            limit=50,
        )
        if (a.get("scope") == GLOBAL_SCOPE and a.get("title") == ASSET_TITLE)
    ]
    if existing:
        print(f"[skip] 全局禁词资产已存在：{ASSET_TITLE} ({existing[0].get('asset_id')})")
        return 0

    created = svc.create(
        scope=GLOBAL_SCOPE,
        asset_type=AssetType.FORBIDDEN_LEXICON.value,
        title=ASSET_TITLE,
        summary=ASSET_SUMMARY,
        payload={"entries": ENTRIES},
        source_kind="seed_methodology",
        enabled=True,
    )
    block = sum(1 for e in ENTRIES if e["severity"] == "block")
    warn = sum(1 for e in ENTRIES if e["severity"] == "warn")
    print(f"[ok] 已创建全局禁词资产：{ASSET_TITLE} ({created.get('asset_id')})")
    print(f"     共 {len(ENTRIES)} 条规则（block={block}，warn={warn}）。")
    print("     所有项目的 scan_forbidden_lexicon / 一键扫禁词 / book_run 禁词审计将自动比对。")
    print("     如某项目不想用，在资产库里禁用该资产即可（opt-out）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
