# Writing Prompt 模块化与文风基底完善设计

> Date: 2026-04-06
> Status: Draft
> Scope: `backend/app/services/agents/draft/` — Writer & Reviewer prompt 系统

## Context

当前系统的写作 prompt 存在两个结构性问题：

1. **文风质量不足**：`WRITER_SYSTEM_PROMPT` 虽有"反总结升华""反回声复述"等条目，但缺少对 LLM 最高频文风毒瘤的系统性覆盖——声音/语气/眼神的解读性描写、程度副词泛滥、油腻词汇、并列对比句式、模糊推测词等。
2. **所有规则堆在一个巨型字符串中**：难以维护、无法按需启用/禁用、不为后续"文风自适应"预留接口。

本次改动基于对 5 个成品 SillyTavern 预设（V2.2、Kemini Aether 3.72、Dream 4.6.3.1、双人成行 PrismFox V3.0、夏瑾 Pro 1.90）的系统性提取，将其中经过验证的文风技法融入本项目的 Writer/Reviewer prompt 体系。

## Design Goals

- 建立**分层模块化**的 prompt 架构，每个模块聚焦一个维度，可独立维护
- 全面覆盖 LLM 高频文风问题，执行强度为**死令级**
- Reviewer 评审维度与 Writer 规则一一对应，形成闭环
- 为后续"文风自适应选择池"预留架构接口（本次不实现）

## Architecture

### 文件结构

在 `backend/app/services/agents/draft/` 下新建 `prompts/` 子包：

```
agents/draft/
  ├── prompts/
  │   ├── __init__.py          # 导出 assemble_writer_prompt(), assemble_reviewer_prompt()
  │   ├── base.py              # WRITER_BASE_PROMPT — 角色定位 + 总则
  │   ├── prose_quality.py     # PROSE_QUALITY_RULES — 白描/感官规范/环境参与叙事
  │   ├── anti_cliche.py       # ANTI_CLICHE_RULES — 反八股死令
  │   ├── dialogue.py          # DIALOGUE_RULES — 对白准则
  │   ├── pacing.py            # PACING_RULES — 节奏 + 场景收束 + 反套路
  │   └── reviewer.py          # REVIEWER_PROMPT — 审校 prompt（维度与 Writer 模块对应）
  ├── writer_agent.py          # 改为调用 prompts.assemble_writer_prompt()
  ├── review_support.py        # 改为从 prompts.reviewer 导入
  └── ...
```

### 拼装逻辑

```python
# prompts/__init__.py

from .base import WRITER_BASE_PROMPT
from .prose_quality import PROSE_QUALITY_RULES
from .anti_cliche import ANTI_CLICHE_RULES
from .dialogue import DIALOGUE_RULES
from .pacing import PACING_RULES
from .reviewer import REVIEWER_PROMPT

def assemble_writer_prompt() -> str:
    """按固定顺序拼接所有 Writer prompt 模块。"""
    return "\n\n".join([
        WRITER_BASE_PROMPT,
        PROSE_QUALITY_RULES,
        ANTI_CLICHE_RULES,
        DIALOGUE_RULES,
        PACING_RULES,
    ])

def assemble_reviewer_prompt() -> str:
    """返回 Reviewer prompt。"""
    return REVIEWER_PROMPT
```

`writer_agent.py` 的 `_build_system_prompt()` 调用 `assemble_writer_prompt()` 替代原来的 `WRITER_SYSTEM_PROMPT` 常量。其余动态拼装（style hints、continuity、history recall、context pack、memory）逻辑不变。

`review_support.py` 从 `prompts.reviewer` 导入 `REVIEWER_PROMPT` 替代原来的 `REVIEWER_SYSTEM_PROMPT` 常量。

## Module Content

### Module 1: `base.py` — WRITER_BASE_PROMPT

精简的角色定位和总则（~200字）：

```
你是一名资深小说家。你将基于提供的上下文设定、角色记忆和创作者指令，创作小说正文。

要求：
1. 只输出小说正文本身，不要输出任何元信息、注释、标题编号或大纲。
2. 保持与原文一致的叙事风格、句式节奏和人称视角。
3. 严格遵守"必须延续的事实"中的设定，不要与之矛盾。
4. 注意"风险提示"中标记的问题，在写作中主动规避。
5. 推进剧情时，让角色的选择和行动有因果逻辑，避免突兀转折。
6. 如果提供了修订意见，请在保留上一版核心情节的基础上针对性修改。
```

### Module 2: `prose_quality.py` — PROSE_QUALITY_RULES

分为白描准则、感官描写规范、环境参与叙事三部分。

**白描准则**：
- 通过角色的动作、语言、神态本身传递情绪和心理，不要从作者角度对其解释或评论。
  正确：他把杯里最后的酒一饮而尽，没有辞别，转身大步离开，一次也没有回头。
  错误：他的眼神中充满了决绝与不舍，这个动作体现了他内心的挣扎。
- 内心活动以自由间接引语自然融入叙事，无需特殊标注（如"他想"）。
  示例：已经快三点了，那个女孩还会来么？多半是不会了。他一边苦笑，一边不再死死盯着手机。
- 整体笔触：禁止将单一动作拆分为连续的机械步骤。一个动作只作为一个整体呈现，禁止流水账式过程展开。
- 每处描写仅保留一个高权重感官细节（触感/声音/温度/视觉冲击），主动舍弃低价值细节，不要面面俱到。
- 物理锚点投射：内心状态必须投射到物理锚点——袖口的质感、茶底的苦涩、指甲缝的沙砾。用物体显影灵魂，不要直述心理。
- 当一个动作或信息已完成表达功能，必须立即推进叙事。禁止停留在已完成的动作上反复修饰、补充解释。

**感官描写规范**（新增，来源：V2.2 感官描写规范 + Dream 反八股）：
- 禁止人声描写：不描写声音的轻重缓急/高低起伏/大小变化，不写"声音里带着..."、"嗓音听起来..."、"语气中透着..."。只写说话状态（"淡淡地说"）或直接给出对白，无法转化的声音描述直接删除。
- 禁止解读眼神：不描写眼神的内容与情绪（"眼神中流露出..."、"眼底闪过一丝..."）。只写视线轨迹或眼部动作（"他眯起眼笑了"、"目光停滞在某处"、"垂下眼睫"）。
- 禁止状态介词外挂：严禁用"带着/透着/夹杂着/显得"外挂人物状态（"眼中透着讥讽"、"语气夹杂着傲慢"）。改用状态副词前置（"讥讽地看"、"傲慢地开口"）。

**环境参与叙事**（新增，来源：V2.2 去八股2.0 质感重构）：
- 不要写"心情阴郁"，写"影子被夕阳拉到墙角，盖住了那堆积满灰尘的旧报纸"。
- 用环境的噪点传递氛围：墙皮剥落的脆响、冰箱运作的嗡鸣、指甲刮过木刺的阻力。
- 用动作的停顿或错位表达情绪；通过衣服的褶皱、袖口的拉扯来体现心理张力。
- 删掉所有"像"、"好似"、"仿佛"——直接叙述客观存在的状态。

### Module 3: `anti_cliche.py` — ANTI_CLICHE_RULES

死令级反八股规则，融合 V2.2、Dream、夏瑾的精华。

**审美红线**（来源：V2.2 去八股2.0、Dream 反八股(克)）：
- 禁止空洞类比：禁止将心脏/心境比作水面（涟漪、石子、湖泊、古井、击碎、泛起）
- 封杀"不是/而是"、"与其说……不如说……"、"仿佛……又……"等否定定义句式
- 封杀"不是...而是"、"没有...也没有..."、"与其...不如"等并列对比句式
- 严禁正文中使用括号（）进行逻辑补丁或状态说明
- 删除"一种"、"某种"、"那种"、"属于……特有的"、"带着……地"等指向不明的形容词

**程度副词与强调词死刑**（来源：V2.2 去八股2.0 + Dream 反八股(必要)(弱)）：
- 严禁"极其"、"甚至"、"非常"、"异常"、"十分"、"万分"
- 严禁"一丝"、"一抹"、"一些"、"一种"等量词修饰情绪/神态
- 严禁"不易察觉"、"难以察觉"、"带着xx意味"、"充满了某种"
- 必须将其转化为具体的物理细节——通过气味、温度、动作来呈现

**禁解释性描写**（已有，保留）：
- 禁止解释性比喻——不用比喻来解释角色状态
- 禁止对角色的动作/语气做作者视角的二次阐释
- 禁止描写不存在或无法感知的细节

**禁油腻词汇**（新增，来源：V2.2 文风去油）：
- 禁止"深情地"、"宠溺地"、"邪魅地"、"疯狂地"等廉价情感副词
- 禁止"不容置疑"、"不容反驳"、"不容拒绝"、"霸道"、"邪魅"、"猎物"、"猎手"、"信徒"
- 禁止"眼神拉丝"及"三分X三分Y"式浮夸描写
- 禁止"若有若无的叹息"、"不易察觉的颤抖"

**禁模糊推测词**（新增，来源：Dream 反八股(克)/(弱)）：
- 禁止"似乎"、"仿佛"、"可能"、"大概"、"近乎"、"几乎"——必须直接、确切肯定
- 禁自我纠正：封杀"不，不对"、"或者说"等虚假思绪词，意图须一次到位

**禁外貌复读**（已有，保留）：
- 禁止在叙事中机械复读角色外貌设定
- 外貌特征仅允许在产生实际物理交互时自然显影

**禁解剖学标签**（新增，来源：V2.2 去八股2.0）：
- 禁止出现锁骨、腕骨、踝骨、肩胛、脊椎、肌腱等解剖学名词
- 禁止"肌肤纤维"、"四肢百骸"、"指节泛白"、"生理性反应"

### Module 4: `dialogue.py` — DIALOGUE_RULES

**对白质感**（已有，保留）：
- 对话要生活化、有真实感。角色可以语塞、词不达意、口是心非、答非所问。
- 不同角色的台词应有辨识度——语气、用词习惯、句式长短应反映其性格和阅历。
- 对话要有潜台词：角色说出口的和内心想的不必一致。
- 对话中不要直接倾倒背景信息或设定解释。

**对白格式**（已有，保留）：
- 对话与叙述描写应分离交织，对话段落独立成行。
- 台词-动作咬合：每句关键台词必须与一个具体的物理动作或环境细节咬合。
- 允许打断：角色的话可以没说完就被他人截断。

**对白禁令（死令级）**（强化，来源：Dream 反八股(克)/(gemini)、Kemini 无八股）：
- 禁止语气描述：不描写声音的音质、音量、语气、速度。"声音里带着..."、"嗓音听起来..."全禁。对白的影响只由角色的后续行为呈现。
- 反回声复述：角色回应时严禁复述对方刚说过的内容。
- 反学术对白：对话中禁止出现学术化、精准分类式的用语。
- 对白须符合中文母语日常习惯，去除翻译腔。

### Module 5: `pacing.py` — PACING_RULES

**段落节奏**（已有，保留）：
- 段落长短交替，制造阅读节奏感
- 五感交织描写
- 只描写 POV 角色能感知到的事物
- 场景内的情绪应有起伏变化

**场景收束（反完结感）**（已实现，来源：夏瑾 Pro + Kemini + PrismFox + V2.2）：
- 场景结尾没有任何收尾感，是自然暂停在某一章途中的进行时
- 以具体物理动作、未完的对白、或环境细节收尾
- 结尾必须保持开放：留下未回应的话语、未完成的动作、刚出现的新信息
- 严禁情感回顾/未来展望/抒情升华/索要反馈/对称回扣五种收束模式

**反总结升华**（已实现+强化）：
- 角色最后一个动作完成，必须立即停止
- 结尾以具体的物理事实定格，像电影镜头突然切走

**反套路**（已有，保留）：
- 地道中文表达，杜绝欧化句式和名词化表达
- 角色情感变化应是渐进的
- 不要让角色方便地忽略重要事件

### Module 6: `reviewer.py` — REVIEWER_PROMPT

Reviewer 的 6 个评审维度保持不变，但维度 5（描写质量）和维度 6（叙事节奏）大幅强化检测项：

**维度 5（描写质量）新增检测项**：
- 感官描写三禁区（人声描写/解读眼神/状态介词外挂）
- 油腻词汇检测（"深情地""邪魅""不容置疑"等）
- 解剖学标签检测
- 并列对比句式检测（"不是...而是"）
- 模糊推测词检测（"似乎""仿佛"）
- 空洞量词修饰检测（"一丝""一抹""一种"）

**维度 6（叙事节奏）新增检测项**：
- 场景结尾开放性（是否以动作/对话/信息收束 vs 总结/升华/展望收束）
- 进行时感（暂停 vs 完结）
- 完结性语句（"他终于明白""从此以后""前方的路"）

**Severity 调整**：
现有规则 `review_support.py:80` 限制描写质量和叙事节奏维度最高为 medium。改为：
- 违反"死令级"规则（禁词命中、禁句式命中）的 issue → severity **high**，可触发强制修订
- 其他描写质量/节奏问题 → 保持 medium

具体实现：在 Reviewer prompt 中明确区分"死令级违规"和"一般建议"，引导 LLM 正确标注 severity。

## Integration Points

### writer_agent.py 改动

```python
# 原来
from .review_support import REVIEWER_SYSTEM_PROMPT
WRITER_SYSTEM_PROMPT = """..."""
# _build_system_prompt 中:
sections = [WRITER_SYSTEM_PROMPT.strip()]

# 改为
from .prompts import assemble_writer_prompt
# _build_system_prompt 中:
sections = [assemble_writer_prompt()]
```

删除原有的 `WRITER_SYSTEM_PROMPT` 常量。

### review_support.py 改动

```python
# 原来
REVIEWER_SYSTEM_PROMPT = """..."""

# 改为
from .prompts import assemble_reviewer_prompt
REVIEWER_SYSTEM_PROMPT = assemble_reviewer_prompt()
```

保持向后兼容：`review_support.py` 中仍导出 `REVIEWER_SYSTEM_PROMPT` 这个名称（赋值为 `assemble_reviewer_prompt()` 的返回值），因为 `reviewer_agent.py:10` 从它导入该名称。

### reviewer_agent.py 改动

无需改动。它已经从 `review_support.py` 导入 `REVIEWER_SYSTEM_PROMPT`，该名称继续存在。

### Severity 门控调整

`review_support.py:80` 的注释/规则需要更新：
```python
# 原来: 描写质量和叙事节奏维度的问题最高为 medium，不单独触发强制修订
# 改为: 描写质量和叙事节奏维度中违反死令级规则的 issue 可以为 high
```

这一调整同时体现在 Reviewer prompt 文本中（引导 LLM 对死令级违规标注 high severity）和 `review_support.py` 的注释中。

## Verification

1. **单元验证**：`assemble_writer_prompt()` 返回的字符串包含所有模块关键词
2. **集成验证**：启动后端，在 Writer Workbench 执行 `write_scene` 任务，检查：
   - 生成正文中不含禁词（"极其""似乎""声音里带着"等）
   - 场景结尾以具体动作/对话/环境细节收束
   - 对白段落独立成行，无语气描写
3. **Reviewer 验证**：检查审校 JSON 报告：
   - 死令级违规的 issue severity 为 high
   - 一般描写质量 issue 为 medium
   - 场景结尾完结感被正确识别
4. **回归验证**：运行现有测试 `pytest tests/test_writer_agent.py`

## Out of Scope

- 文风自适应选择池（后续单独特性）
- 外部化 prompt 到配置文件
- 前端 UI 对 prompt 模块的可视化/开关控制
- 非 draft agent 的其他 prompt（worldline、archive 等）
