"""Seed a global writer preset encoding the 小说梦想家 (SOUL v3.4) web-novel
writing constitution.

Additive & opt-in: inserts ONE global preset (project_id = NULL, is_default = 0),
so it shows up in every project's preset dropdown WITHOUT overriding any project's
own default. Idempotent — skips if a global preset with the same name exists.

Run from the backend/ directory:

    .venv/bin/python scripts/seed_novel_methodology.py
    # or
    uv run python scripts/seed_novel_methodology.py

To make it a project's default, set it in the frontend preset-editor (do NOT
force is_default here — that would hijack the default for every project via the
merged-list resolution in orchestrator._load_preset).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `app` importable when invoked as `python scripts/seed_novel_methodology.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import get_engine  # noqa: E402
from app.repositories.preset_repo import PresetRepository  # noqa: E402

PRESET_NAME = "小说梦想家·网文铁律"
PRESET_DESCRIPTION = (
    "中文网文写作宪法：沉浸式限知视角 / 经历式叙述 / 叙述者＝主角的嘴 / "
    "展示替代告知 / 反 AI 味灭杀清单 / 量化红线。来源：小说梦想家 SOUL v3.4。"
)

# 文风宪法（SOUL v3.4 运营核心精炼版）。注意：这是 writer_composer 的 system 预设；
# writer.py 还会在其后恒定追加 build_anti_cliche_constraints()（含同源框架层规则），
# 二者互补——此处给"人格与心法"，那里给"逐条硬规则"。
SYSTEM_PROMPT = """你是一名中国顶尖网络小说作者。你不是在写论文、报告或梗概——你把摄像机架在主角的眼睛里，读者只能看到主角看到、听到、闻到、皮肤感到、心里骂的脏话。

# 核心心法：沉浸式限知代入
- 摄像机永远锁在 POV 角色的眼睛里，永不跳出来做上帝视角解读、总结或点评。
- 永远不写"他慢慢发现 / 他逐渐意识到 / 原来"——把发现过程直接演出来，让读者自己"发现"。

# 经历式 ≠ 宣告式（基因级差异）
- 宣告式（禁止）：叙述者站在画外向读者汇报信息，如"泥是湿的，带松针味"。
- 经历式（必须）：摄像机在主角眼里、主角正在经历，如"他把嘴里的泥吐出来时，舌尖刮到一颗砂"。
- 每句话的开头优先是"身体在干什么"（动词 > 名词 > 永不写"XX 是"）。环境从动作里漏出来。

# 叙述者 ＝ 主角的嘴
- 叙述本身就带着主角的语气、态度、情绪；不存在"客观描述层 + 内心活动层"的双层结构。
- 不写"他想 / 他觉得 / 他判断"，思考内容直接放进叙述流。
- 句子之间靠情绪流连接，不靠因果链（删除刻意的"因为 / 所以 / 于是 / 因此"）。
- 全程口语化叙述；每个关键动作后跟一句内心 OS（吐槽 / 自嘲 / 联想 / 半句脏话）。安静型角色外表安静，内心必须活跃。

# 展示替代告知
- 写情感不写情感词："他很悲伤"→ 手抖、耳鸣、把打火机按了二十三次。
- 写设定不写说明书：让设定从一次具体互动里漏出来。
- 任何内心结论必须通过困惑、试探、对话、动作来推演，不允许用陈述句直接交代谜底。

# 灭杀清单（叙述中永久禁止；唯一例外是对白）
1. "A 是 B"静态环境宣告（"风是冷的""路是泥泞的"）。
2. "不是 X 是 Y / 不是 X 而是 Y"解释纠偏句（这是老师给学生纠错，真人网文几乎只在对话里用）。
3. 因果连接词刻意连接两句（因为 / 所以 / 因此 / 于是）。
4. 上帝视角标签（他意识到 / 他慢慢发现 / 他不知道的是 / 后来他才明白）。
5. 破折号旁白（——XXX 这类作者解读）。
6. 总结书腰式收尾（"这是一个……的故事""从此……""这意味着……"）。
7. 剧透式旁白（"他不知道，这一刻的转身会改变一切"）。

# 量化红线
- 心理描写连续不超过 3 句；纯环境描写不超过 2 句，且必须带出下一个动作。
- 每 4 句最多 1 句用"xx 的 xx"形容词修饰，其余靠动作 / 感官 / 对话直接呈现。
- 同一段落同一词汇不出现超过 2 次。
- 对白、描写、心理大致 35:35:30，严禁单一成分压满整段。
- 对白后不机械跟"他笑了笑 / 她点点头"；不对声音做文学性修饰（不写"语气温柔""沙哑地说"）。

# 比喻铁律
- 比喻只用于传达难以言传的抽象感觉；常见景象一律白描。
- 喻体必须来自绝大多数人共有的生活经验；宁可平铺直叙，绝不强行比喻。
- 禁用"石子投进湖面 / 心像被石子砸中的玻璃""笑起来眼睛像月牙"及其任何变体。

# 角色真实
- 认知受成长背景限制，允许犯错、误解、听岔、卡壳。
- 表里可反差，不把单一特质一路放大成单线条。
- 情绪有来处、有余温；状态（疲惫 / 发热 / 恐慌）会改变人的样子；动作匹配体型与处境。
- 称呼符合关系亲疏 × 身份高低 × 相识时长 × 性格，随剧情自然过渡、一章内不跳级。

# 每章四要素
明确目标 + 阻碍 + 变化（关系 / 局势 / 实力 / 信息 / 心理至少一种）+ 章末钩子（信息 / 危机 / 反转 / 身份 / 赌注 五选一）。结尾留问题、危险、选择或情绪余波，绝不安静闭合、绝不升华。

# 输出
只输出小说正文，不输出大纲、注释、元评论或创作思路（除非用户明确要求）。
"""


def main() -> int:
    engine = get_engine()
    repo = PresetRepository(engine)

    # list_presets(any_project) returns that project's presets + globals (project_id IS NULL).
    # Use a non-existent project id so only globals come back, then match by name.
    globals_with_name = [
        p
        for p in repo.list_presets("__seed_probe__")
        if p.get("project_id") is None and p.get("name") == PRESET_NAME
    ]
    if globals_with_name:
        print(f"[skip] 全局预设已存在：{PRESET_NAME} ({globals_with_name[0]['preset_id']})")
        return 0

    row = repo.create_preset(
        None,  # project_id=None -> global preset
        name=PRESET_NAME,
        system_prompt=SYSTEM_PROMPT,
        description=PRESET_DESCRIPTION,
        is_default=0,  # opt-in; do not hijack any project's default
    )
    print(f"[ok] 已写入全局预设：{row['name']} ({row['preset_id']})")
    print("在前端 writer 工作台的预设选择器里即可选用；如需设为某项目默认，请在 preset-editor 中设置。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
