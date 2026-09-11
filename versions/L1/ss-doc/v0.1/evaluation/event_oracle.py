"""Evaluator-only independent implementation of the bounded surface grammar.

Does not import the teacher, transducer, learned states, or SS decoder. This is
independent code, NOT independent human annotation or real-world validation.
"""
import re

PEOPLE = ("太郎", "花子", "次郎", "美咲", "健太", "由紀")
PREDICATES = {"助け": "help", "褒め": "praise", "訪ね": "visit", "見つめ": "gaze_at"}
NAME = "(?:" + "|".join(PEOPLE) + ")"
VERB = "(?:" + "|".join(PREDICATES) + ")"
PATTERNS = [
    re.compile(rf"(?P<if>もし)?(?P<a>{NAME})が(?P<b>{NAME})を(?P<v>{VERB})(?P<end>なかったら|なかった|たら|た)。"),
    re.compile(rf"(?P<if>もし)?(?P<b>{NAME})を(?P<a>{NAME})が(?P<v>{VERB})(?P<end>なかったら|なかった|たら|た)。"),
]


def interpret(text):
    if type(text) is not str:
        return None
    for pattern in PATTERNS:
        match = pattern.fullmatch(text)
        if not match:
            continue
        row = match.groupdict()
        hypothetical = row["end"].endswith("ら")
        if bool(row["if"]) != hypothetical:
            return None
        return {"subject": "entity:" + row["a"], "object": "entity:" + row["b"],
                "predicate": "predicate:" + PREDICATES[row["v"]],
                "polarity": "polarity:" + ("negative" if row["end"].startswith("な") else "positive"),
                "modality": "modality:" + ("hypothetical" if hypothetical else "asserted")}
    return None


INVALID = (
    "", "太郎", "太郎が花子を助けた", "太郎が花子を助けた。。", "太郎が花子を助けた。花子が太郎を褒めた。",
    "未知が花子を助けた。", "太郎が花子を食べた。", "太郎が花子を助ける。",
    "太郎が花子が助けた。", "太郎を花子を助けた。", "太郎がが花子を助けた。",
    "太郎花子を助けた。", "花子を助けた。", "太郎が助けた。", "助けた。",
    "もし太郎が花子を助けた。", "太郎が花子を助けたら。", "もしもし太郎が花子を助けたら。",
    "もし太郎が花子を助けなかった。", "太郎が花子を助けなかったら。",
    "太郎が花子を助けたなかった。", "太郎が花子を助けなかったた。",
    "「太郎が花子を助けた。」", "太郎は花子を助けた。", "太郎が彼女を助けた。",
    "太郎が花子と次郎を助けた。", "太郎が花子を助けた？", "太郎が花子を助けた。<EOS>",
    "太郎 が花子を助けた。", "太郎\nが花子を助けた。", "太郎が花子を助けた。" * 30,
)
