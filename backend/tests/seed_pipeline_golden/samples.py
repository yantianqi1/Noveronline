"""Golden samples for seed pipeline prompt evaluation.

Each sample is a (id, text, context) triple. ``text`` is the segment body the
LLM should analyse; ``context`` is the prior-segment summary string that would
normally come from ReadingNotesManager.assemble_context() — leave empty to
simulate the first segment in a project.

Five samples cover the prompt's stress points:
    DIALOGUE_HEAVY     — multi-character dialogue, alliance forms.
    NARRATIVE_DENSE    — action sequence, single protagonist + brief antagonist.
    WORLD_BUILDING     — organisation rules introduced, minimal characters.
    RELATIONSHIP_SHIFT — major betrayal reveal, two characters.
    SPARSE             — internal monologue, only one named character present.
                          Used to test that the prompt does NOT hallucinate
                          relationships or extra characters when none exist.
"""
from __future__ import annotations

from typing import Dict, List


SAMPLE_DIALOGUE_HEAVY: Dict[str, str] = {
    "id": "DIALOGUE_HEAVY",
    "context": "",
    "text": (
        "【第七章 茶肆夜会】\n\n"
        "深夜的\"听风楼\"二楼雅间，林策推开窗，望了眼楼下街市，转身落座。\n\n"
        "\"你确定他不会跟来？\"\n\n"
        "对面的女子摘下兜帽，露出一张冷峻的脸。她叫沈无双，原是青衫剑派的弟子，三年前因事退出师门。\n\n"
        "\"不会。我特意绕了三条街。\"沈无双将一卷竹简推过来，"
        "\"这是你要的东西，名册上一共三十七人。\"\n\n"
        "林策展开竹简，眉头渐渐皱起。\n\n"
        "\"果然有他。\"\n\n"
        "\"陆君言确实在名单里。\"沈无双低声道，"
        "\"从今夜起，我们就是同路人了。这件事一旦露馅，谁都活不下来。\"\n\n"
        "林策点点头，将竹简收入怀中：\"你放心。我会保你周全。\"\n\n"
        "\"我不需要你保。\"沈无双站起身，"
        "\"我只需要你说话算话——三个月内，铲除陆君言。\"\n\n"
        "\"成交。\""
    ),
}


SAMPLE_NARRATIVE_DENSE: Dict[str, str] = {
    "id": "NARRATIVE_DENSE",
    "context": "",
    "text": (
        "【第十二章 玄霜阁夜袭】\n\n"
        "子时三刻，玄霜阁后院寂静无人。\n\n"
        "楚轻寒翻过最后一道墙头，足尖一点便落入院中。她在屋檐下静伏片刻，"
        "确认守卫巡逻路线后，便如猫一般贴墙而行。\n\n"
        "第三进的偏厅果然如情报所言，烛火未熄。她从腰间取出银针，挑开窗扣，纵身入内。"
        "书架第三层的暗格里，那枚刻着\"霜\"字的玉牌静静躺在锦盒中。\n\n"
        "得手的瞬间，门外传来脚步声。\n\n"
        "\"何人在内！\"\n\n"
        "楚轻寒来不及思索，反手将玉牌抛上房梁，自己则一翻身钻入桌下。"
        "守卫推门而入，正是阁主之子周怀瑾。他举烛环顾，目光在桌下停留了一瞬。\n\n"
        "\"狸猫吗？\"周怀瑾轻笑一声，转身离开。\n\n"
        "楚轻寒长舒一口气，从梁上取下玉牌，循原路退出。"
        "她不知道的是，周怀瑾在转身那一刻，唇角已勾起一丝玩味的笑。"
    ),
}


SAMPLE_WORLD_BUILDING: Dict[str, str] = {
    "id": "WORLD_BUILDING",
    "context": "",
    "text": (
        "【第三章 五行宗的规矩】\n\n"
        "五行宗立宗已逾八百年，传承不衰，靠的不是武力，而是规矩。\n\n"
        "宗内分五脉：金、木、水、火、土。每脉设掌门一名，由长老议会推举，任期三十年。"
        "五脉之上设宗主一人，统摄全局，但无权干涉各脉内务，"
        "仅在外敌入侵或宗门大变时方可调动各脉之力。\n\n"
        "这是开宗祖师定下的\"五均制\"——任何一脉都不能独大，任何一位宗主都不能成为暴君。\n\n"
        "弟子入门，须经\"问心\"考验：连续三日三夜不眠不食，于祖师堂中静坐参悟。"
        "能在此期间不起退志者，方可正式入门，分入五脉之一。\n\n"
        "宗内最严的禁令有三：一曰不得欺师；二曰不得叛宗；三曰不得私传五行心法于外人。"
        "三禁皆死罪，无一例外。\n\n"
        "三百年来，违此三禁者共四十六人，皆被剑诀阁的\"清门使\"亲自执行。"
        "剑诀阁不属五脉任何一脉，直接听命于祖师堂——也就是宗主之上的最高权威。\n\n"
        "如今的宗主萧无尘，已是这一代的第十二任。"
    ),
}


SAMPLE_RELATIONSHIP_SHIFT: Dict[str, str] = {
    "id": "RELATIONSHIP_SHIFT",
    "context": (
        "[seg_001] 裴砚一三年前与师父决裂，誓要查清青衫剑派为何追杀师门。\n"
        "[seg_002] 一封匿名密信指引他独自前往镜湖。"
    ),
    "text": (
        "【第二十一章 镜湖背叛】\n\n"
        "镜湖之畔，月色如银。\n\n"
        "裴砚一握紧手中长剑，望着对面缓步而来的人，喉头发紧。\n\n"
        "\"师兄，你为何在此？\"\n\n"
        "陆君言一身白衣，神情温和，仿佛只是来赴一次寻常的茶约。"
        "\"砚一，我等你很久了。\"\n\n"
        "裴砚一退后半步：\"你怎么知道我会来这里？\"\n\n"
        "\"因为是我把消息透给你的。\"陆君言微笑着说，"
        "\"那封'青衫剑派'的密信，是我亲笔写的。\"\n\n"
        "裴砚一如遭雷击。三年来，他一直以为是青衫剑派在追杀师门，"
        "他的愤怒、他的奔波、他与师父的决裂，竟全都是这个温和如玉的师兄一手设计。\n\n"
        "\"你为什么……\"\n\n"
        "\"因为我需要一个能替我执剑的人，砚一。\"陆君言的笑意未减，"
        "但目光已冷如寒冰，\"而你，是我培养了三年的人。从今夜起，你只能是我的人。\"\n\n"
        "裴砚一长剑出鞘，手却在颤抖。"
    ),
}


SAMPLE_SPARSE: Dict[str, str] = {
    "id": "SPARSE",
    "context": "[seg_014] 姜逾白十年后回到故乡，住在城西的一间客栈。",
    "text": (
        "【第十五章 独坐听雨】\n\n"
        "雨已下了三日。\n\n"
        "姜逾白独坐窗前，手边的茶水早已凉透。"
        "他望着檐角不断滴落的水珠，思绪却飞到了千里之外。\n\n"
        "那年也是这样的雨夜。\n\n"
        "他想起母亲临终前的那句话，\"逾白，无论如何，不要回去。\"\n\n"
        "可是他没有听。十年了，他还是回来了，回到了这座让他既熟悉又陌生的城。\n\n"
        "茶汤里映出他自己的脸——比记忆中老了许多。\n\n"
        "雨声渐密，他终于起身，将冷茶倒掉，重新沏了一壶。这一次，他选了最浓的那种。"
    ),
}


ALL_SAMPLES: List[Dict[str, str]] = [
    SAMPLE_DIALOGUE_HEAVY,
    SAMPLE_NARRATIVE_DENSE,
    SAMPLE_WORLD_BUILDING,
    SAMPLE_RELATIONSHIP_SHIFT,
    SAMPLE_SPARSE,
]


SAMPLES_BY_ID: Dict[str, Dict[str, str]] = {s["id"]: s for s in ALL_SAMPLES}
