"""Synthetic, manually specified teaching language. NEVER imported by inference.

The grammar and state/action supervision are supplied, not discovered. Evaluation
uses disjoint compositions; this is not independently collected natural language.
"""
NAMES = ("太郎", "花子", "次郎", "美咲", "健太", "由紀")
VERBS = (("助け", "help"), ("褒め", "praise"), ("訪ね", "visit"), ("見つめ", "gaze_at"))
SUFFIXES = {
    ("positive", "asserted"): ("た", "PAST"),
    ("negative", "asserted"): ("なかった", "NEG_PAST"),
    ("positive", "hypothetical"): ("たら", "COND"),
    ("negative", "hypothetical"): ("なかったら", "NEG_COND"),
}
GOALS = ("subject_first", "object_first")


def lexicon():
    entries = [(name, "ENTITY", "entity:" + name) for name in NAMES]
    entries += [(stem, "PREDICATE", "predicate:" + pred) for stem, pred in VERBS]
    entries += [("が", "GA", "literal:が"), ("を", "WO", "literal:を"),
                ("もし", "IF", "literal:もし"), ("。", "DOT", "literal:。"),
                ("<EOS>", "EOS", "literal:<EOS>")]
    entries += [(surface, category, "literal:" + surface) for surface, category in SUFFIXES.values()]
    return entries


def split_of(ai, bi, pi):
    residue = (ai + 2 * bi + pi) % 5
    return "evaluation" if residue == 0 else "development" if residue == 1 else "train"


def examples(split):
    for ai, actor in enumerate(NAMES):
        for bi, patient in enumerate(NAMES):
            if ai == bi:
                continue
            for pi, (stem, predicate) in enumerate(VERBS):
                if split_of(ai, bi, pi) != split:
                    continue
                for polarity, mode in SUFFIXES:
                    for order in GOALS:
                        slots = {"subject": "entity:" + actor, "object": "entity:" + patient,
                                 "predicate": "predicate:" + predicate,
                                 "polarity": "polarity:" + polarity, "modality": "modality:" + mode}
                        yield {"id": f"{ai}-{bi}-{pi}-{polarity}-{mode}-{order}",
                               "slots": slots, "order": order,
                               "text": surface(actor, patient, stem, polarity, mode, order)}


def surface(actor, patient, stem, polarity, mode, order):
    clauses = actor + "が" + patient + "を" if order == "subject_first" else patient + "を" + actor + "が"
    return ("もし" if mode == "hypothetical" else "") + clauses + stem + SUFFIXES[polarity, mode][0] + "。"


def reader_trace(example):
    """Explicit teacher annotations, not a parser available to the receiver."""
    slots, order = example["slots"], example["order"]
    mode = slots["modality"].split(":", 1)[1]
    polarity = slots["polarity"].split(":", 1)[1]
    actor, patient = slots["subject"].split(":", 1)[1], slots["object"].split(":", 1)[1]
    stem = dict((pred, stem) for stem, pred in VERBS)[slots["predicate"].split(":", 1)[1]]
    rows = []
    q = "A0"

    def step(token, category, action, nxt):
        nonlocal q
        rows.append((q, token, category, action, nxt))
        q = nxt

    prefix = "H" if mode == "hypothetical" else "A"
    if mode == "hypothetical":
        step("もし", "IF", "noop", "H0")
    first, second = (actor, patient) if order == "subject_first" else (patient, actor)
    first_role, second_role = ("subject", "object") if order == "subject_first" else ("object", "subject")
    branch = "S" if order == "subject_first" else "O"
    step(first, "ENTITY", "capture", prefix + "1")
    step("が" if first_role == "subject" else "を", "GA" if first_role == "subject" else "WO", "bind:" + first_role, prefix + branch + "2")
    step(second, "ENTITY", "capture", prefix + branch + "3")
    step("が" if second_role == "subject" else "を", "GA" if second_role == "subject" else "WO", "bind:" + second_role, prefix + "4")
    step(stem, "PREDICATE", "predicate", prefix + "5")
    suffix, category = SUFFIXES[polarity, mode]
    step(suffix, category, "status:" + polarity + ":" + mode, "E0")
    step("。", "DOT", "noop", "E1")
    step("<EOS>", "EOS", "stop", "DONE")
    return rows


def writer_trace(example, goal):
    """Token-level construction supervision. No complete output strings stored."""
    polarity = example["slots"]["polarity"].split(":", 1)[1]
    mode = example["slots"]["modality"].split(":", 1)[1]
    actions = ["emit:literal:もし"] if mode == "hypothetical" else []
    if goal == "subject_first":
        actions += ["slot:subject", "emit:literal:が", "slot:object", "emit:literal:を"]
    else:
        actions += ["slot:object", "emit:literal:を", "slot:subject", "emit:literal:が"]
    actions += ["slot:predicate", "emit:literal:" + SUFFIXES[polarity, mode][0], "emit:literal:。", "stop"]
    return list(enumerate(actions))
