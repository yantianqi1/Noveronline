# Writing Prompt 模块化与文风基底完善 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Modularize the Writer/Reviewer prompt system into focused modules and add comprehensive anti-cliché / prose quality rules based on proven SillyTavern presets.

**Architecture:** Split the monolithic `WRITER_SYSTEM_PROMPT` string into 5 focused modules under a new `prompts/` subpackage, wire them through an `assemble_writer_prompt()` function, and replace the `REVIEWER_SYSTEM_PROMPT` with a strengthened version whose dimensions match the writer modules 1:1.

**Tech Stack:** Python 3.11, plain string constants (no templating), pytest

**Spec:** `docs/superpowers/specs/2026-04-06-writing-prompt-modularization-design.md`

---

### Task 1: Create `prompts/base.py` — Writer base prompt

**Files:**
- Create: `backend/app/services/agents/draft/prompts/__init__.py`
- Create: `backend/app/services/agents/draft/prompts/base.py`
- Create: `backend/tests/test_draft_prompts.py`

- [ ] **Step 1: Create the prompts package with `__init__.py`**

```python
# backend/app/services/agents/draft/prompts/__init__.py
"""Writer / Reviewer prompt 模块化拼装。"""

from .base import WRITER_BASE_PROMPT


def assemble_writer_prompt() -> str:
    """按固定顺序拼接所有 Writer prompt 模块。"""
    return WRITER_BASE_PROMPT


def assemble_reviewer_prompt() -> str:
    """返回 Reviewer prompt（后续 Task 补充）。"""
    return ""
```

- [ ] **Step 2: Create `base.py`**

```python
# backend/app/services/agents/draft/prompts/base.py
"""Writer 基础角色定位与总则。"""

WRITER_BASE_PROMPT = """你是一名资深小说家。你将基于提供的上下文设定、角色记忆和创作者指令，创作小说正文。

要求：
1. 只输出小说正文本身，不要输出任何元信息、注释、标题编号或大纲。
2. 保持与原文一致的叙事风格、句式节奏和人称视角。
3. 严格遵守"必须延续的事实"中的设定，不要与之矛盾。
4. 注意"风险提示"中标记的问题，在写作中主动规避。
5. 推进剧情时，让角色的选择和行动有因果逻辑，避免突兀转折。
6. 如果提供了修订意见，请在保留上一版核心情节的基础上针对性修改。""".strip()
```

- [ ] **Step 3: Write the first test**

```python
# backend/tests/test_draft_prompts.py
"""Tests for the modularized draft prompt system."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.agents.draft.prompts import assemble_writer_prompt
from app.services.agents.draft.prompts.base import WRITER_BASE_PROMPT


class TestBasePrompt:
    def test_base_prompt_is_nonempty_string(self):
        assert isinstance(WRITER_BASE_PROMPT, str)
        assert len(WRITER_BASE_PROMPT) > 100

    def test_base_prompt_contains_role(self):
        assert "资深小说家" in WRITER_BASE_PROMPT

    def test_assemble_includes_base(self):
        full = assemble_writer_prompt()
        assert "资深小说家" in full
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/draft/prompts/__init__.py \
       backend/app/services/agents/draft/prompts/base.py \
       backend/tests/test_draft_prompts.py
git commit -m "feat: create prompts/ subpackage with base writer prompt module"
```

---

### Task 2: Create `prompts/prose_quality.py`

**Files:**
- Create: `backend/app/services/agents/draft/prompts/prose_quality.py`
- Modify: `backend/app/services/agents/draft/prompts/__init__.py`
- Modify: `backend/tests/test_draft_prompts.py`

- [ ] **Step 1: Create `prose_quality.py`**

```python
# backend/app/services/agents/draft/prompts/prose_quality.py
"""描写质量规则：白描准则、感官描写规范、环境参与叙事。"""

PROSE_QUALITY_RULES = """## 描写质量

### 白描准则
- 通过角色的动作、语言、神态本身传递情绪和心理，不要从作者角度对其解释或评论。
  正确：他把杯里最后的酒一饮而尽，没有辞别，转身大步离开，一次也没有回头。
  错误：他的眼神中充满了决绝与不舍，这个动作体现了他内心的挣扎。
- 内心活动以自由间接引语自然融入叙事，无需特殊标注（如"他想"）。
  示例：已经快三点了，那个女孩还会来么？多半是不会了。他一边苦笑，一边不再死死盯着手机。
- 整体笔触：禁止将单一动作拆分为连续的机械步骤。一个动作只作为一个整体呈现，禁止流水账式过程展开。
- 每处描写仅保留一个高权重感官细节（触感/声音/温度/视觉冲击），主动舍弃低价值细节，不要面面俱到。
- 物理锚点投射：内心状态必须投射到物理锚点——袖口的质感、茶底的苦涩、指甲缝的沙砾。用物体显影灵魂，不要直述心理。
- 当一个动作或信息已完成表达功能，必须立即推进叙事。禁止停留在已完成的动作上反复修饰、补充解释。

### 感官描写规范
- 禁止人声描写：不描写声音的轻重缓急/高低起伏/大小变化，不写"声音里带着..."、"嗓音听起来..."、"语气中透着..."。只写说话状态（"淡淡地说"）或直接给出对白，无法转化的声音描述直接删除。
- 禁止解读眼神：不描写眼神的内容与情绪（"眼神中流露出..."、"眼底闪过一丝..."）。只写视线轨迹或眼部动作（"他眯起眼笑了"、"目光停滞在某处"、"垂下眼睫"）。
- 禁止状态介词外挂：严禁用"带着/透着/夹杂着/显得"外挂人物状态（"眼中透着讥讽"、"语气夹杂着傲慢"）。改用状态副词前置（"讥讽地看"、"傲慢地开口"）。

### 环境参与叙事
- 不要写"心情阴郁"，写"影子被夕阳拉到墙角，盖住了那堆积满灰尘的旧报纸"。
- 用环境的噪点传递氛围：墙皮剥落的脆响、冰箱运作的嗡鸣、指甲刮过木刺的阻力。
- 用动作的停顿或错位表达情绪；通过衣服的褶皱、袖口的拉扯来体现心理张力。
- 删掉所有"像"、"好似"、"仿佛"——直接叙述客观存在的状态。""".strip()
```

- [ ] **Step 2: Update `__init__.py` to include prose_quality**

```python
# backend/app/services/agents/draft/prompts/__init__.py
"""Writer / Reviewer prompt 模块化拼装。"""

from .base import WRITER_BASE_PROMPT
from .prose_quality import PROSE_QUALITY_RULES


def assemble_writer_prompt() -> str:
    """按固定顺序拼接所有 Writer prompt 模块。"""
    return "\n\n".join([
        WRITER_BASE_PROMPT,
        PROSE_QUALITY_RULES,
    ])


def assemble_reviewer_prompt() -> str:
    """返回 Reviewer prompt（后续 Task 补充）。"""
    return ""
```

- [ ] **Step 3: Add test**

Append to `backend/tests/test_draft_prompts.py`:

```python
from app.services.agents.draft.prompts.prose_quality import PROSE_QUALITY_RULES


class TestProseQualityRules:
    def test_contains_sensory_rules(self):
        assert "禁止人声描写" in PROSE_QUALITY_RULES
        assert "禁止解读眼神" in PROSE_QUALITY_RULES
        assert "禁止状态介词外挂" in PROSE_QUALITY_RULES

    def test_contains_environment_rules(self):
        assert "环境参与叙事" in PROSE_QUALITY_RULES

    def test_assembled_prompt_includes_prose_quality(self):
        full = assemble_writer_prompt()
        assert "白描准则" in full
        assert "感官描写规范" in full
```

- [ ] **Step 4: Run tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/draft/prompts/prose_quality.py \
       backend/app/services/agents/draft/prompts/__init__.py \
       backend/tests/test_draft_prompts.py
git commit -m "feat: add prose_quality prompt module (sensory rules, environment narration)"
```

---

### Task 3: Create `prompts/anti_cliche.py`

**Files:**
- Create: `backend/app/services/agents/draft/prompts/anti_cliche.py`
- Modify: `backend/app/services/agents/draft/prompts/__init__.py`
- Modify: `backend/tests/test_draft_prompts.py`

- [ ] **Step 1: Create `anti_cliche.py`**

```python
# backend/app/services/agents/draft/prompts/anti_cliche.py
"""反八股死令规则（最高优先级）。"""

ANTI_CLICHE_RULES = """## 反八股死令（最高优先级，违反即重写）

### 一、审美红线
- 禁止空洞类比与假性修辞：
  · 禁止将心脏/心境比作水面（涟漪、石子、湖泊、古井、击碎、泛起）
  · 封杀"不是/而是"、"与其说……不如说……"、"仿佛……又……"等否定定义句式
  · 封杀"不是...而是"、"没有...也没有..."、"与其...不如"等并列对比句式
  · 严禁正文中使用括号（）进行逻辑补丁或状态说明
  · 删除"一种"、"某种"、"那种"、"属于……特有的"、"带着……地"等指向不明的形容词

### 二、程度副词与强调词死刑
- 严禁出现"极其"、"甚至"、"非常"、"异常"、"十分"、"万分"。
- 严禁"一丝"、"一抹"、"一些"、"一种"等量词修饰情绪/神态。
- 严禁"不易察觉"、"难以察觉"、"带着xx意味"、"充满了某种"等模糊修饰。
- 必须将其转化为具体的物理细节——通过气味、温度、动作来呈现，而非使用程度堆砌。

### 三、禁解释性描写
- 禁止解释性比喻——不用比喻来解释角色状态（错误："这句话像一道闪电击中了他脆弱的心房"）。
- 禁止对角色的动作/语气做作者视角的二次阐释（错误："他微微挑眉，带着一种不容置疑的自信，仿佛一切都了然于胸"→应只写"他微微挑眉"）。
- 禁止描写不存在或无法感知的细节（"推了推并不存在的眼镜""掸去并不存在的灰尘"）。

### 四、禁油腻词汇
- 禁止"深情地"、"宠溺地"、"邪魅地"、"疯狂地"等廉价情感副词。情绪必须通过客观动作折射。
- 禁止"不容置疑"、"不容反驳"、"不容拒绝"、"霸道"、"邪魅"、"猎物"、"猎手"、"信徒"。
- 禁止"眼神拉丝"及"三分X三分Y"式浮夸描写。
- 禁止"若有若无的叹息"、"不易察觉的颤抖"。

### 五、禁模糊推测词
- 禁止"似乎"、"仿佛"、"可能"、"大概"、"近乎"、"几乎"——必须直接、确切肯定。
- 禁自我纠正：封杀"不，不对"、"或者说"等虚假思绪词，意图须一次到位。

### 六、禁外貌复读
- 禁止在叙事中机械复读角色外貌设定。严禁"那双……的眼睛"、"那张……的脸"等劣质定语结构。
- 外貌特征仅允许在产生实际物理交互时自然显影，绝不允许作为独立修饰语。

### 七、禁解剖学标签
- 禁止出现锁骨、腕骨、踝骨、肩胛、脊椎、肌腱等解剖学名词。
- 禁止"肌肤纤维"、"四肢百骸"、"指节泛白"、"生理性反应"。""".strip()
```

- [ ] **Step 2: Update `__init__.py`**

Add import `from .anti_cliche import ANTI_CLICHE_RULES` and add `ANTI_CLICHE_RULES` to the list in `assemble_writer_prompt()`:

```python
from .base import WRITER_BASE_PROMPT
from .prose_quality import PROSE_QUALITY_RULES
from .anti_cliche import ANTI_CLICHE_RULES


def assemble_writer_prompt() -> str:
    """按固定顺序拼接所有 Writer prompt 模块。"""
    return "\n\n".join([
        WRITER_BASE_PROMPT,
        PROSE_QUALITY_RULES,
        ANTI_CLICHE_RULES,
    ])
```

- [ ] **Step 3: Add test**

Append to `backend/tests/test_draft_prompts.py`:

```python
from app.services.agents.draft.prompts.anti_cliche import ANTI_CLICHE_RULES


class TestAntiClicheRules:
    def test_contains_banned_words_section(self):
        assert "程度副词" in ANTI_CLICHE_RULES
        assert "极其" in ANTI_CLICHE_RULES

    def test_contains_oily_words_section(self):
        assert "禁油腻词汇" in ANTI_CLICHE_RULES
        assert "邪魅" in ANTI_CLICHE_RULES

    def test_contains_anatomy_ban(self):
        assert "解剖学标签" in ANTI_CLICHE_RULES

    def test_assembled_includes_anti_cliche(self):
        full = assemble_writer_prompt()
        assert "反八股死令" in full
```

- [ ] **Step 4: Run tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/draft/prompts/anti_cliche.py \
       backend/app/services/agents/draft/prompts/__init__.py \
       backend/tests/test_draft_prompts.py
git commit -m "feat: add anti_cliche prompt module (banned words, oily vocab, anatomy labels)"
```

---

### Task 4: Create `prompts/dialogue.py`

**Files:**
- Create: `backend/app/services/agents/draft/prompts/dialogue.py`
- Modify: `backend/app/services/agents/draft/prompts/__init__.py`
- Modify: `backend/tests/test_draft_prompts.py`

- [ ] **Step 1: Create `dialogue.py`**

```python
# backend/app/services/agents/draft/prompts/dialogue.py
"""对白准则。"""

DIALOGUE_RULES = """## 对白准则

### 对白质感
- 对话要生活化、有真实感。角色可以语塞、词不达意、口是心非、答非所问。
- 不同角色的台词应有辨识度——语气、用词习惯、句式长短应反映其性格和阅历，避免所有人说话一个味道。
- 对话要有潜台词：角色说出口的和内心想的不必一致，让读者自己体会言外之意。
- 对话中不要直接倾倒背景信息或设定解释，世界观和设定应通过角色互动、片段式侧写自然流露。

### 对白格式
- 对话与叙述描写应分离交织，对话段落独立成行。
- 台词-动作咬合：每句关键台词必须与一个具体的物理动作或环境细节咬合，对话不能悬浮在真空中。
- 允许打断：角色的话可以没说完就被他人截断，这比每个人都说完整句子更真实。

### 对白禁令（死令级）
- 禁止语气描述：不描写声音的音质、音量、语气、速度或来源。"声音里带着..."、"嗓音听起来..."全禁。对白的影响只由角色的后续对白或行为呈现。
- 反回声复述：角色回应时严禁复述对方刚说过的内容。正确公式：[A说信息]→[B产生新反应/提供新信息]；错误公式：[A说信息]→[B复述A的话+评价]。
- 反学术对白：对话中禁止出现学术化、精准分类式的用语，角色不是在作报告。
- 对白须符合中文母语日常习惯，去除翻译腔、术语、数据与分析报告感。""".strip()
```

- [ ] **Step 2: Update `__init__.py`**

Add import `from .dialogue import DIALOGUE_RULES` and append to the list:

```python
from .base import WRITER_BASE_PROMPT
from .prose_quality import PROSE_QUALITY_RULES
from .anti_cliche import ANTI_CLICHE_RULES
from .dialogue import DIALOGUE_RULES


def assemble_writer_prompt() -> str:
    """按固定顺序拼接所有 Writer prompt 模块。"""
    return "\n\n".join([
        WRITER_BASE_PROMPT,
        PROSE_QUALITY_RULES,
        ANTI_CLICHE_RULES,
        DIALOGUE_RULES,
    ])
```

- [ ] **Step 3: Add test**

Append to `backend/tests/test_draft_prompts.py`:

```python
from app.services.agents.draft.prompts.dialogue import DIALOGUE_RULES


class TestDialogueRules:
    def test_contains_voice_ban(self):
        assert "禁止语气描述" in DIALOGUE_RULES

    def test_contains_echo_ban(self):
        assert "反回声复述" in DIALOGUE_RULES

    def test_assembled_includes_dialogue(self):
        full = assemble_writer_prompt()
        assert "对白准则" in full
```

- [ ] **Step 4: Run tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 13 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/draft/prompts/dialogue.py \
       backend/app/services/agents/draft/prompts/__init__.py \
       backend/tests/test_draft_prompts.py
git commit -m "feat: add dialogue prompt module (voice ban, echo ban, academic ban)"
```

---

### Task 5: Create `prompts/pacing.py`

**Files:**
- Create: `backend/app/services/agents/draft/prompts/pacing.py`
- Modify: `backend/app/services/agents/draft/prompts/__init__.py`
- Modify: `backend/tests/test_draft_prompts.py`

- [ ] **Step 1: Create `pacing.py`**

```python
# backend/app/services/agents/draft/prompts/pacing.py
"""叙事节奏、场景收束、反套路规则。"""

PACING_RULES = """## 叙事节奏

### 段落节奏
- 段落长短交替，制造阅读节奏感。紧张段落用短句密集推进，抒情或日常段落可以用长句铺陈。
- 五感交织描写（不只视觉，还有听觉、触觉、嗅觉、味觉），营造身临其境的沉浸感。
- 只描写 POV 角色能感知到的事物，不要突破视角限制进行全知叙述。
- 场景内的情绪应有起伏变化，避免从头到尾一个调子的平铺直叙。

### 场景收束（反完结感）
- 场景结尾没有任何收尾感。它不是一个故事的结局，而是自然暂停在某一章途中的进行时。
- 以角色的具体物理动作、一句未完的对白、或一个环境细节收尾——不进行任何总结、评价、情感升华或展望。
- 结尾必须保持开放：留下一个未回应的话语、一个未完成的动作、一个刚出现的新信息，让叙事有天然的"接话入口"。
- 严禁以下收束模式：
  · 情感回顾式："他终于明白了……"
  · 未来展望式："从此以后……""前方的路还很长"
  · 抒情升华式：用景色/天气隐喻角色心境作为结尾段
  · 索要反馈式："他期待着""他等待着"等暗示读者回应的表述
  · 对称回扣式：结尾刻意呼应开头意象形成"完美闭环"
- 正确示例：场景在一个角色打开门的动作中停住；在另一个角色开口说了半句话时切断；在一声突然响起的电话铃中中止。

### 反总结升华
- 当角色的最后一个动作完成，必须立即停止。严禁在画面定格后追加"这意味着……""从此以后……"式的总结段。结尾应以一个具体的物理事实（动作/声音/环境细节）定格，像电影镜头突然切走，而非缓缓淡出。

### 反套路
- 地道的中文本土化表达，杜绝欧化句式，严格避免"这个动作""这个认知""这种感觉"这类名词化表达。
- 角色的情感变化应是渐进的，不要在一段内完成巨大的情感跳跃。
- 不要让角色方便地忽略重要事件，不要用推理套路让角色过于轻易地想通一切。""".strip()
```

- [ ] **Step 2: Update `__init__.py` — final writer assembly**

```python
# backend/app/services/agents/draft/prompts/__init__.py
"""Writer / Reviewer prompt 模块化拼装。"""

from .base import WRITER_BASE_PROMPT
from .prose_quality import PROSE_QUALITY_RULES
from .anti_cliche import ANTI_CLICHE_RULES
from .dialogue import DIALOGUE_RULES
from .pacing import PACING_RULES


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
    """返回 Reviewer prompt（Task 6 补充）。"""
    return ""
```

- [ ] **Step 3: Add test**

Append to `backend/tests/test_draft_prompts.py`:

```python
from app.services.agents.draft.prompts.pacing import PACING_RULES


class TestPacingRules:
    def test_contains_scene_closure(self):
        assert "场景收束" in PACING_RULES
        assert "反完结感" in PACING_RULES

    def test_contains_anti_summary(self):
        assert "反总结升华" in PACING_RULES

    def test_assembled_includes_all_modules(self):
        full = assemble_writer_prompt()
        # Verify all 5 modules are present
        assert "资深小说家" in full          # base
        assert "白描准则" in full             # prose_quality
        assert "反八股死令" in full           # anti_cliche
        assert "对白准则" in full             # dialogue
        assert "场景收束" in full             # pacing
```

- [ ] **Step 4: Run tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 16 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/draft/prompts/pacing.py \
       backend/app/services/agents/draft/prompts/__init__.py \
       backend/tests/test_draft_prompts.py
git commit -m "feat: add pacing prompt module (scene closure, anti-summary, anti-cliché)"
```

---

### Task 6: Create `prompts/reviewer.py`

**Files:**
- Create: `backend/app/services/agents/draft/prompts/reviewer.py`
- Modify: `backend/app/services/agents/draft/prompts/__init__.py`
- Modify: `backend/tests/test_draft_prompts.py`

- [ ] **Step 1: Create `reviewer.py`**

```python
# backend/app/services/agents/draft/prompts/reviewer.py
"""Reviewer 审校 prompt — 6 维度结构化审核。"""

REVIEWER_PROMPT = """你是一名专业的小说审校编辑。

你的工作是检查一段新生成的小说正文，从以下六个维度做结构化审核，并给出整体判断。

## 审核维度

### 1. 连续性（continuity）
- 本章开头与上章结尾是否自然衔接（场景、情绪、时间）
- 角色在上章末尾的状态与本章描述是否矛盾

### 2. 角色一致性（character_consistency）
- POV 角色的行为动机是否符合当前设定中的性格
- 非 POV 角色的行为是否合理

### 3. 悬念与伏笔（thread_management）
- 未解决线索是否有被推进或呼应
- 是否意外"提前解决"了不该解决的悬念

### 4. 风格一致性（style_consistency）
- 叙事视角是否稳定（不在第三人称中混入第一人称感受）
- 节奏是否与前文风格相符
- 是否出现超出 POV 角色认知范围的叙述（如"实际上""真相是""殊不知"等上帝视角用语）
- 角色的判断和推理是否严格基于其主观认知，还是意外呈现了全知视角

### 5. 描写质量（prose_quality）
检查以下问题，分为【死令级】和【一般级】：

【死令级——命中即标注 severity: high】
- 是否出现程度副词堆砌（"极其""甚至""非常""异常""一丝""一抹"）
- 是否出现空洞类比（心如湖面、涟漪、石子击碎等心水比喻族）
- 是否出现并列对比句式（"不是...而是""与其说...不如说"）
- 是否出现模糊推测词（"似乎""仿佛""可能""大概""近乎"）
- 是否出现油腻词汇（"深情地""宠溺地""邪魅""不容置疑""猎物""信徒"）
- 是否出现解剖学标签（锁骨、腕骨、肩胛、肌肤纤维、四肢百骸、指节泛白）
- 是否出现人声解读（"声音里带着...""嗓音听起来...""语气中透着..."）
- 是否出现眼神解读（"眼神中流露出...""眼底闪过一丝..."）
- 是否出现状态介词外挂（"带着/透着/夹杂着/显得"+人物状态）
- 是否出现自我纠正句式（"不，不对""或者说"等虚假思绪词）
- 是否在动作完成后追加总结性升华段落（"这意味着……""从此以后……"）
- 对话中是否存在回声式复述（角色B重复角色A刚说过的话而非产生新反应）
- 对话中是否存在语气描述（描写声音的音质、音量、语气、速度）

【一般级——标注 severity: medium 或 low】
- 是否存在作者视角的解释性描写（如"他的眼神中充满了坚定"而非通过行为展示）
- 对话是否有角色辨识度，还是所有人说话一个语气
- 是否有冗余重复的描写或用词
- 感官描写是否单调（是否只有视觉，缺少听觉、触觉等）
- 是否使用了欧化句式或名词化表达（如"这个动作""这种感觉"）
- 是否机械复读角色外貌设定（"那双……的眼睛""那张……的脸"）
- 对话是否存在学术化、报告式用语（角色不应像在作报告）

### 6. 叙事节奏（pacing）
检查以下问题，分为【死令级】和【一般级】：

【死令级——命中即标注 severity: high】
- 场景结尾是否以总结、升华、抒情或展望收束（而非以角色动作、未完对话或新信息收束）
- 是否使用了"他终于明白""从此以后""前方的路"等完结性语句

【一般级——标注 severity: medium 或 low】
- 段落长短是否过于单调（全是长段落或全是短段落）
- 场景内的情绪是否有起伏变化，还是平铺直叙

## 输出要求
只输出 JSON 对象，格式如下：
{
  "pass": true 或 false,
  "score": 0-100 的整数,
  "issues": [
    {
      "dimension": "连续性 | 角色一致性 | 悬念与伏笔 | 风格一致性 | 描写质量 | 叙事节奏",
      "severity": "high | medium | low",
      "description": "问题描述",
      "quote": "引用正文中的问题原文片段（20字以内）",
      "suggestion": "修改建议"
    }
  ],
  "keep": ["值得保留的段落或特点描述"],
  "overall_assessment": "一句话总评"
}

评判标准：
- 如果没有 high 级别问题且 score >= 70，pass 为 true
- severity 为 high 的问题必须修改（包括描写质量和叙事节奏维度中命中死令级规则的问题）
- severity 为 medium 的问题建议修改
- severity 为 low 的问题可忽略
- keep 列表中应标注写得好的、不应在修改中丢失的部分""".strip()
```

- [ ] **Step 2: Update `__init__.py`**

Add `from .reviewer import REVIEWER_PROMPT` and update `assemble_reviewer_prompt()`:

```python
# backend/app/services/agents/draft/prompts/__init__.py
"""Writer / Reviewer prompt 模块化拼装。"""

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

- [ ] **Step 3: Add test**

Append to `backend/tests/test_draft_prompts.py`:

```python
from app.services.agents.draft.prompts import assemble_reviewer_prompt
from app.services.agents.draft.prompts.reviewer import REVIEWER_PROMPT


class TestReviewerPrompt:
    def test_contains_six_dimensions(self):
        assert "连续性" in REVIEWER_PROMPT
        assert "角色一致性" in REVIEWER_PROMPT
        assert "悬念与伏笔" in REVIEWER_PROMPT
        assert "风格一致性" in REVIEWER_PROMPT
        assert "描写质量" in REVIEWER_PROMPT
        assert "叙事节奏" in REVIEWER_PROMPT

    def test_contains_death_order_markers(self):
        assert "死令级" in REVIEWER_PROMPT
        assert "severity: high" in REVIEWER_PROMPT

    def test_assemble_reviewer(self):
        result = assemble_reviewer_prompt()
        assert result == REVIEWER_PROMPT
        assert len(result) > 500
```

- [ ] **Step 4: Run tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 19 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/agents/draft/prompts/reviewer.py \
       backend/app/services/agents/draft/prompts/__init__.py \
       backend/tests/test_draft_prompts.py
git commit -m "feat: add reviewer prompt module with death-order severity for prose/pacing"
```

---

### Task 7: Wire `writer_agent.py` to use new prompt modules

**Files:**
- Modify: `backend/app/services/agents/draft/writer_agent.py:1-175`

- [ ] **Step 1: Replace the monolithic prompt constant with the modular import**

In `backend/app/services/agents/draft/writer_agent.py`:

1. Remove the entire `WRITER_SYSTEM_PROMPT = """..."""` block (lines 18–83).
2. Add import at the top (after existing imports):

```python
from .prompts import assemble_writer_prompt
```

3. In `_build_system_prompt()` (around line 175), change:

```python
# OLD
sections = [WRITER_SYSTEM_PROMPT.strip()]

# NEW
sections = [assemble_writer_prompt()]
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_writer_agent.py -v`
Expected: All existing tests PASS (these tests cover NovelDB/tools/orchestrator, not prompt content directly)

- [ ] **Step 3: Run the new prompt tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py -v`
Expected: 19 PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agents/draft/writer_agent.py
git commit -m "refactor: wire writer_agent to use modular prompt assembly"
```

---

### Task 8: Wire `review_support.py` to use new reviewer prompt

**Files:**
- Modify: `backend/app/services/agents/draft/review_support.py:1-84`

- [ ] **Step 1: Replace the inline REVIEWER_SYSTEM_PROMPT**

In `backend/app/services/agents/draft/review_support.py`:

1. Remove the entire `REVIEWER_SYSTEM_PROMPT = """..."""` block (lines 14–84).
2. Add import and re-export:

```python
from .prompts import assemble_reviewer_prompt

REVIEWER_SYSTEM_PROMPT = assemble_reviewer_prompt()
```

This preserves the `REVIEWER_SYSTEM_PROMPT` name that `reviewer_agent.py:10` imports.

3. Also remove the old severity cap comment (was line 82):

```python
# OLD: 描写质量和叙事节奏维度的问题最高为 medium，不单独触发强制修订
# (This line is inside the deleted prompt string — it's gone now. The new reviewer
#  prompt in prompts/reviewer.py handles severity guidance inline.)
```

- [ ] **Step 2: Add integration test**

Append to `backend/tests/test_draft_prompts.py`:

```python
class TestIntegration:
    def test_review_support_exports_reviewer_prompt(self):
        """Ensure review_support.py still exports the expected name."""
        from app.services.agents.draft.review_support import REVIEWER_SYSTEM_PROMPT
        assert "描写质量" in REVIEWER_SYSTEM_PROMPT
        assert "死令级" in REVIEWER_SYSTEM_PROMPT

    def test_reviewer_agent_can_import(self):
        """Ensure ReviewerAgent can still import and use the prompt."""
        from app.services.agents.draft.reviewer_agent import ReviewerAgent
        agent = ReviewerAgent()
        assert "描写质量" in agent.system_prompt
```

- [ ] **Step 3: Run all tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_draft_prompts.py tests/test_writer_agent.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agents/draft/review_support.py \
       backend/tests/test_draft_prompts.py
git commit -m "refactor: wire review_support to use modular reviewer prompt"
```

---

### Task 9: Cleanup and final verification

**Files:**
- Review: all modified files

- [ ] **Step 1: Verify the old prompt strings are fully removed**

Run: `cd /root/novelwork/backend && grep -n "WRITER_SYSTEM_PROMPT\s*=" app/services/agents/draft/writer_agent.py`
Expected: No output (the old constant definition is gone)

Run: `cd /root/novelwork/backend && grep -c "反总结升华" app/services/agents/draft/writer_agent.py`
Expected: `0` (old prompt content is gone from this file)

Run: `cd /root/novelwork/backend && grep -c "反总结升华" app/services/agents/draft/prompts/pacing.py`
Expected: `1` (lives in the new module)

- [ ] **Step 2: Run the full test suite**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Verify prompt assembly produces expected content**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) python3 -c "
from app.services.agents.draft.prompts import assemble_writer_prompt, assemble_reviewer_prompt
wp = assemble_writer_prompt()
rp = assemble_reviewer_prompt()
print(f'Writer prompt: {len(wp)} chars')
print(f'Reviewer prompt: {len(rp)} chars')
# Spot-check key sections
for kw in ['资深小说家', '白描准则', '感官描写规范', '反八股死令', '对白准则', '场景收束', '反总结升华']:
    assert kw in wp, f'MISSING in writer: {kw}'
    print(f'  ✓ Writer contains: {kw}')
for kw in ['死令级', 'severity: high', '描写质量', '叙事节奏', '场景结尾']:
    assert kw in rp, f'MISSING in reviewer: {kw}'
    print(f'  ✓ Reviewer contains: {kw}')
print('All checks passed.')
"`
Expected: All checks passed, writer prompt ~3500-4500 chars, reviewer prompt ~2500-3500 chars.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: verify prompt modularization — all modules wired and tested"
```
