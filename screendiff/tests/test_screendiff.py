"""screendiff · pytest。

分层：
  TestSpecRules      —— SPEC 条文的直接断言
  TestVectors        —— 黄金向量与实现一致
  TestNotVacuous     —— 元测试：用例不得空转（变异敏感性）
  TestCrossLanguage  —— Python 与 JS 独立实现差分
  TestRealDumps      —— 真机 dump 对回归 + 量化指标
  TestSemantics      —— effect / stuck / loading
  TestDeterminism    —— 幂等与同分顺序
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from screendiff.core import (
    Element, diff, effect_of, is_loading, is_stuck,
)

ROOT = Path(__file__).resolve().parent.parent
VECTORS = ROOT / "vectors"
DUMPS = ROOT / "dumps"

FLAGS = ("clickable", "long_clickable", "scrollable", "editable",
         "checked", "disabled", "password")


def E(ref, role, label, bounds, **kw):
    return Element(ref=ref, role=role, label=label, bounds=tuple(bounds), **kw)


def brief(seq):
    return [(e.ref, e.role, e.label, e.bounds) for e in seq]


# ================================================================ SPEC 条文
class TestSpecRules:
    def test_overlap_ratio_uses_min_area(self):
        """SPEC §4.2：分母是 min(area)。"""
        from screendiff.core import _overlap
        a = E("p", "item", "", (0, 0, 100, 100))
        b = E("c", "item", "", (0, 0, 100, 100))
        assert _overlap(a, b) == 1.0

    def test_overlap_zero_area_is_zero(self):
        """SPEC §4.2：任一面为 0，重叠率定义为 0。"""
        from screendiff.core import _overlap
        a = E("p", "item", "", (5, 5, 5, 5))
        b = E("c", "item", "", (0, 0, 100, 100))
        assert _overlap(a, b) == 0.0

    def test_size_ratio_gate_blocks_container(self):
        """SPEC §4.1：全屏容器不得吞掉小元素（真机案例）。"""
        from screendiff.core import _score, _size_ratio
        small = E("p", "img", "头像", (891, 283, 1017, 409))
        big = E("c", "scroll", "", (0, 74, 1080, 2337))
        assert _size_ratio(small, big) < 0.5
        assert _score(small, big) == 0

    def test_empty_class_name_is_not_a_signal(self):
        """SPEC §4.1：空 class_name 不构成"类名相同"。

        2026-10-27 踩过：两个匿名元素因 class_name 均为空而被判同类，
        进而靠几何匹配上，误报率高。这里断言的是**class tier 不命中**——
        它们仍可能靠纯几何 tier（20 分）匹配，那是另一回事。
        """
        from screendiff.core import _score
        a = E("p", "item", "甲", (0, 0, 100, 100))
        b = E("c", "item", "乙", (0, 0, 100, 100))
        assert _score(a, b) == 20, "应只命中纯几何 tier，不得命中 class tier"

    def test_empty_class_with_different_bounds_scores_zero(self):
        """两个匿名元素 + bounds 不重叠 → 完全不是候选。"""
        from screendiff.core import _score
        a = E("p", "item", "甲", (0, 0, 100, 100))
        b = E("c", "item", "乙", (500, 500, 600, 600))
        assert _score(a, b) == 0

    def test_score_tiers(self):
        """SPEC §4.1：六个 tier 各自命中。"""
        from screendiff.core import _score
        # 100 rid
        assert _score(E("p", "x", "a", (0, 0, 1, 1), resource_id="r"),
                      E("c", "y", "b", (9, 9, 99, 99), resource_id="r")) == 100
        # 70 class+label
        assert _score(E("p", "btn", "确定", (0, 0, 100, 100), class_name="B"),
                      E("c", "btn", "确定", (0, 0, 100, 100), class_name="B")) == 70
        # 50 class + overlap
        assert _score(E("p", "item", "甲", (0, 0, 100, 100), class_name="B"),
                      E("c", "item", "乙", (0, 0, 100, 100), class_name="B")) == 50
        # 35 label + overlap
        assert _score(E("p", "item", "甲", (0, 0, 100, 100)),
                      E("c", "item", "甲", (0, 0, 100, 100))) == 35
        # 20 纯几何 + 面积比
        assert _score(E("p", "item", "", (0, 0, 100, 100)),
                      E("c", "item", "", (0, 0, 100, 100))) == 20

    def test_is_identical_is_semantic_not_hash(self):
        """SPEC §5.1：is_identical 是语义判定。"""
        a = [E("e1", "scroll", "", (0, 0, 1080, 2337), scrollable=True)]
        assert diff(a, a).is_identical is True
        b = [E("e1", "scroll", "", (0, 0, 1080, 2337), scrollable=True),
             E("e2", "item", "新行", (0, 0, 100, 100))]
        assert diff(a, b).is_identical is False

    def test_change_kinds_are_independent(self):
        """SPEC §5：一个元素可同时命中多类变化。"""
        cs = diff(
            [E("e1", "btn", "确定", (0, 0, 200, 100), class_name="B")],
            [E("e1", "btn", "取消", (0, 50, 200, 150), class_name="B", disabled=True)],
        )
        assert cs.matched[0].changes == ("moved", "label_changed", "state_changed")

    def test_added_removed_are_ordered(self):
        """SPEC §4.4：added/removed 按原快照顺序。"""
        cs = diff(
            [E("e1", "item", "甲", (0, 0, 100, 100), resource_id="a"),
             E("e2", "item", "乙", (0, 900, 100, 1000), resource_id="b")],
            [E("e9", "item", "丙", (700, 0, 800, 100), resource_id="c"),
             E("e8", "item", "丁", (700, 900, 800, 1000), resource_id="d")],
        )
        assert [e.ref for e in cs.added] == ["e9", "e8"]
        assert [e.ref for e in cs.removed] == ["e1", "e2"]


# ================================================================ 黄金向量
class TestVectors:
    def test_vectors_match_implementation(self):
        files = sorted(VECTORS.glob("*.json"))
        assert len(files) >= 6, f"向量文件应 ≥6，实为 {len(files)}"
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            for i, c in enumerate(d["cases"]):
                got = diff(c["in"]["prev"], c["in"]["cur"]).to_dict()
                assert got == c["out"], f"{f.name} case#{i} {c['why']}"

    def test_vectors_have_why(self):
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for i, c in enumerate(d["cases"]):
                assert c["why"], f"{f.name} case#{i} 缺 why"

    def test_vector_count(self):
        n = sum(len(json.loads(f.read_text(encoding="utf-8"))["cases"])
                for f in VECTORS.glob("*.json"))
        assert n >= 25, f"用例应 ≥25，实为 {n}"


# ================================================================ 元测试
class TestNotVacuous:
    """元测试：用例不得空转。

    uidref 的教训：向量生成器的属性名泄漏让 12 条用例一条都没测到
    它声称的规则，却全部"通过"——因为期望值是用同一份坏输入生成的。
    这里用**变异敏感性**做通用防线。

    断言分两级：

    * **A 级（每条用例）**：至少一种变异必须改变输出。
      抓"这条用例完全死了"。
    * **B 级（定向）**：声称测某条规则的用例，对该规则的定向变异
      必须改变输出。抓"这条用例测的是别的东西"。
    """

    @staticmethod
    def _mutations(inp):
        """穷举：每个元素的每个布尔标志翻转、bounds 平移、label 改写。"""
        for side in ("prev", "cur"):
            for idx in range(len(inp[side])):
                for f in FLAGS:
                    m = json.loads(json.dumps(inp))
                    m[side][idx][f] = not m[side][idx][f]
                    yield f"{side}[{idx}].{f} 翻转", m
                b = inp[side][idx]["bounds"]
                m = json.loads(json.dumps(inp))
                m[side][idx]["bounds"] = [b[0] + 11, b[1] + 11, b[2] + 11, b[3] + 11]
                yield f"{side}[{idx}].bounds 平移", m
                if inp[side][idx]["label"]:
                    m = json.loads(json.dumps(inp))
                    m[side][idx]["label"] = "变异标签"
                    yield f"{side}[{idx}].label 改写", m

    def test_a_every_case_is_alive(self):
        """A 级：每条用例至少对一种变异敏感。"""
        dead = []
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for i, c in enumerate(d["cases"]):
                if not c["in"]["prev"] and not c["in"]["cur"]:
                    continue  # 两帧皆空，无物可变异，结构性豁免
                alive = False
                for _, mut in self._mutations(c["in"]):
                    if diff(mut["prev"], mut["cur"]).to_dict() != c["out"]:
                        alive = True
                        break
                if not alive:
                    dead.append(f"{f.name}#{i}")
        assert not dead, f"这些用例对任何变异都不敏感（空转）：{dead}"

    def test_b_targeted_sensitivity(self):
        """B 级：声称测某规则的用例，对该规则定向变异必须敏感。

        这是真正能抓住 uidref 那类 bug 的断言——不是因为"没变化"，
        而是因为"该变的没变"。
        """
        # 向量 id → (侧, 元素下标, 变异说明, 构造变异的函数)
        targeted = {
            # 声称"仅 checked 变 → state_changed"：翻 cur 的 checked 必须改变输出
            ("classification-001.json", 2): ("cur", 0, "checked",
                                             lambda m: m["cur"][0].update(
                                                 checked=m["prev"][0]["checked"])),
            # 声称"仅 label 变 → label_changed"：改 cur 的 label 必须改变输出
            ("classification-001.json", 3): ("cur", 0, "label",
                                             lambda m: m["cur"][0].update(
                                                 label=m["prev"][0]["label"])),
            # 声称"仅 bounds 变 → moved"：还原 cur 的 bounds 必须改变输出
            ("classification-001.json", 1): ("cur", 0, "bounds",
                                             lambda m: m["cur"][0].update(
                                                 bounds=m["prev"][0]["bounds"])),
            # 声称"面积比闸门"：把小元素放大到与容器同量级，必须变成匹配
            ("matching-001.json", 2): ("prev", 0, "bounds",
                                       lambda m: m["prev"][0].update(
                                           bounds=[0, 74, 1080, 2337])),
        }
        for (fname, idx), (side, eidx, what, fn) in targeted.items():
            f = VECTORS / fname
            d = json.loads(f.read_text(encoding="utf-8"))
            c = d["cases"][idx]
            mut = json.loads(json.dumps(c["in"]))
            fn(mut)
            got = diff(mut["prev"], mut["cur"]).to_dict()
            assert got != c["out"], (
                f"{fname}#{idx} 声称测 {what}，但把 {what} 改回原状后输出没变——"
                f"这条用例测的是别的东西")

    def test_c_contract_fields_present(self):
        """C 级：契约字段齐全。缺字段会让整个验证对真实分歧失明。

        uidref 踩过：center 取整规则写了必须，但比对契约没这个字段，
        于是向零截断的实现测一致性竟然全绿。
        """
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for i, c in enumerate(d["cases"]):
                out = c["out"]
                for k in ("matched", "added", "removed", "is_identical", "counts"):
                    assert k in out, f"{f.name}#{i} 缺契约字段 {k}"
                for k in ("matched", "added", "removed", "moved",
                          "state_changed", "label_changed"):
                    assert k in out["counts"], f"{f.name}#{i} counts 缺 {k}"


# ================================================================ 跨语言
class TestCrossLanguage:
    @staticmethod
    def _py(xml_pair):
        prev, cur = xml_pair
        return diff(prev, cur).to_dict()

    @staticmethod
    def _js(xml_pair):
        prev, cur = xml_pair
        code = (
            "const {diff}=require('./screendiff.js');"
            f"process.stdout.write(JSON.stringify(diff({json.dumps(prev)},"
            f"{json.dumps(cur)}).to_dict()));"
        )
        r = subprocess.run(["node", "-e", code], capture_output=True,
                           text=True, cwd=ROOT / "js", timeout=60)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    def test_vectors_agree_across_languages(self):
        if not shutil.which("node"):
            pytest.skip("无 node")
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for i, c in enumerate(d["cases"]):
                pair = (c["in"]["prev"], c["in"]["cur"])
                assert self._py(pair) == self._js(pair), f"{f.name}#{i}"

    def test_real_dumps_agree_across_languages(self):
        if not shutil.which("node"):
            pytest.skip("无 node")
        sys_path = str(ROOT.parent / "uidref")
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        from uidref.digest import parse_file
        for a, b in [("c1", "c2"), ("c2", "c3"), ("c3", "d1")]:
            A = parse_file(DUMPS / f"{a}.xml")
            B = parse_file(DUMPS / f"{b}.xml")
            pa = [self._el(e) for e in A]
            pb = [self._el(e) for e in B]
            assert self._py((pa, pb)) == self._js((pa, pb)), f"{a}→{b}"

    @staticmethod
    def _el(e):
        return {
            "ref": e.ref, "role": e.role, "label": e.label,
            "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
            "class_name": e.class_name, "resource_id": e.resource_id,
            **{f: getattr(e, f) for f in FLAGS},
        }

    def test_random_inputs_agree(self):
        if not shutil.which("node"):
            pytest.skip("无 node")
        import random
        rng = random.Random(20261027)
        for t in range(120):
            prev, cur = self._rand(rng), self._rand(rng)
            assert self._py((prev, cur)) == self._js((prev, cur)), f"seed case {t}"

    @staticmethod
    def _rand(rng):
        n = rng.randint(0, 6)
        out = []
        for i in range(n):
            x1 = rng.randint(-20, 900); y1 = rng.randint(-20, 1800)
            out.append({
                "ref": f"e{i+1}",
                "role": rng.choice(["item", "btn", "scroll", "input", "switch", "text"]),
                "label": rng.choice(["", "确定", "取消", "Wi-Fi", "设置"]),
                "bounds": [x1, y1, x1 + rng.randint(0, 700), y1 + rng.randint(0, 500)],
                "class_name": rng.choice(["", "android.widget.Button",
                                          "android.view.View",
                                          "android.widget.LinearLayout"]),
                "resource_id": rng.choice(["", "com.x:id/a", "com.x:id/b"]),
                **{f: rng.random() < 0.3 for f in FLAGS},
            })
        return out


# ================================================================ 真机
class TestRealDumps:
    @staticmethod
    def _load(a, b):
        sys_path = str(ROOT.parent / "uidref")
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)
        from uidref.digest import parse_file
        return parse_file(DUMPS / f"{a}.xml"), parse_file(DUMPS / f"{b}.xml")

    def test_scroll_is_pure_move(self):
        """核心指标：滚动场景下不得有 added/removed/state/label 变化。"""
        A, B = self._load("c3", "d1")
        cs = diff(A, B)
        c = cs.counts
        assert c["added"] == 0, f"滚动误报新增：{[e.label for e in cs.added]}"
        assert c["removed"] == 0, f"滚动误报消失：{[e.label for e in cs.removed]}"
        assert c["state_changed"] == 0
        assert c["label_changed"] == 0
        assert c["moved"] >= 8, f"应识别出大部分平移，实为 {c['moved']}"

    def test_single_change_is_precise(self):
        """单元素状态变化：只报一个元素，且类别正确。"""
        A, B = self._load("c2", "c3")
        cs = diff(A, B)
        c = cs.counts
        assert c["added"] == 0 and c["removed"] == 0
        assert c["label_changed"] == 1
        assert c["state_changed"] == 1
        assert c["moved"] == 0

    def test_match_rate_metric(self):
        """SPEC §7：匹配率 = matched / (matched + removed)。"""
        for a, b in [("c1", "c2"), ("c2", "c3"), ("c3", "d1")]:
            A, B = self._load(a, b)
            cs = diff(A, B)
            denom = cs.counts["matched"] + cs.counts["removed"]
            if denom == 0:
                continue
            rate = cs.counts["matched"] / denom
            assert rate >= 0.8, f"{a}→{b} 匹配率 {rate:.2f} 低于 0.8"

    def test_no_false_match_across_screens(self):
        """跨屏时不得把"头像"匹配到"滚动容器"上（面积比闸门的回归）。"""
        A, B = self._load("c1", "c2")
        cs = diff(A, B)
        for p in cs.matched:
            # 头像在 c1，滚动容器在 c2；二者不得成对
            assert not (p.prev.label.startswith("Profile picture")
                        and p.cur.role == "scroll" and not p.cur.label), \
                f"误匹配：{p.prev.label[:20]} → {p.cur.ref} {p.cur.role}"


# ================================================================ 派生语义
class TestSemantics:
    def test_effect_target_gone(self):
        cs = diff([E("e1", "item", "网络", (0, 0, 1080, 200), resource_id="n",
                     clickable=True)],
                  [E("e1", "btn", "返回", (0, 74, 147, 221), resource_id="u",
                     clickable=True)])
        assert effect_of(cs, "e1").conclusion == "target_gone"

    def test_effect_target_changed(self):
        cs = diff([E("e1", "switch", "Wi-Fi", (0, 0, 200, 100),
                     class_name="android.widget.Switch", clickable=True)],
                  [E("e1", "switch", "Wi-Fi", (0, 0, 200, 100),
                     class_name="android.widget.Switch", clickable=True, checked=True)])
        ef = effect_of(cs, "e1")
        assert ef.conclusion == "target_changed"
        assert ef.changes == ("state_changed",)

    def test_effect_target_unchanged(self):
        e = E("e1", "item", "禁用项", (0, 0, 200, 100), clickable=True, disabled=True)
        assert effect_of(diff([e], [e]), "e1").conclusion == "target_unchanged"

    def test_effect_unknown_target(self):
        e = E("e1", "item", "甲", (0, 0, 100, 100), resource_id="a")
        assert effect_of(diff([e], [e]), "e99").conclusion == "unknown_target"

    def test_effect_detects_covering_layer(self):
        """点击弹出覆盖层：target 没变，但新元素压上来。"""
        cs = diff(
            [E("e1", "item", "打开", (0, 0, 1080, 200), resource_id="o",
               clickable=True)],
            [E("e1", "item", "打开", (0, 0, 1080, 200), resource_id="o",
               clickable=True),
             E("e2", "item", "对话框", (100, 60, 980, 260), resource_id="d",
               clickable=True)],
        )
        ef = effect_of(cs, "e1")
        assert ef.conclusion == "target_unchanged"
        assert [e.ref for e in ef.added_overlapping_target] == ["e2"]

    def test_is_stuck(self):
        e = [E("e1", "item", "甲", (0, 0, 100, 100), resource_id="a")]
        hist = [diff(e, e) for _ in range(4)]
        assert is_stuck(hist, 3) is True
        assert is_stuck(hist[:2], 3) is False, "历史不足 n 帧不得判定卡住"
        assert is_stuck(hist, 1) is False, "n<2 必须返回 false"

    def test_is_stuck_breaks_on_change(self):
        a = [E("e1", "item", "甲", (0, 0, 100, 100), resource_id="a")]
        b = [E("e1", "item", "乙", (0, 0, 100, 100), resource_id="a")]
        hist = [diff(a, a), diff(a, a), diff(a, b)]
        assert is_stuck(hist, 3) is False

    def test_is_loading(self):
        assert is_loading([E("e1", "progress", "", (0, 0, 100, 10))]) is True
        assert is_loading([E("e1", "btn", "确定", (0, 0, 100, 100))]) is False
        assert is_loading([]) is False
        assert is_loading([E("e1", "progress", "", (0, 0, 100, 10)),
                           E("e2", "btn", "取消", (0, 20, 100, 120))]) is False


# ================================================================ 确定性
class TestDeterminism:
    def test_idempotent(self):
        a = [E("e1", "item", "甲", (0, 0, 100, 100), class_name="V"),
             E("e2", "item", "乙", (0, 100, 100, 200), class_name="V")]
        b = [E("e1", "item", "乙", (0, 100, 100, 200), class_name="V"),
             E("e2", "item", "甲", (0, 0, 100, 100), class_name="V")]
        first = diff(a, b).to_dict()
        for _ in range(5):
            assert diff(a, b).to_dict() == first

    def test_tie_broken_by_indices_not_labels(self):
        """SPEC §4.3：同分按 (prev_index, cur_index)，不按标签凑对。

        这里两个候选对都是 50 分（class 同、bounds 全重叠）。
        排序键 (-50, 0, 1) 先于 (-50, 1, 0)，所以 prev[0] 配 cur[1]。
        **注意**：这不是"按标签凑对"——标签不同的两对之所以都候选，
        是因为 class 相同且 bounds 完全重叠。规范要的是确定性，不是语义最优。
        """
        a = [E("e1", "item", "甲", (0, 0, 100, 100), class_name="V"),
             E("e2", "item", "乙", (0, 100, 100, 200), class_name="V")]
        b = [E("e1", "item", "乙", (0, 100, 100, 200), class_name="V"),
             E("e2", "item", "甲", (0, 0, 100, 100), class_name="V")]
        cs = diff(a, b)
        assert [(p.prev.ref, p.cur.ref) for p in cs.matched] == [("e1", "e2"), ("e2", "e1")]

    def test_duplicate_elements_not_mis_sorted(self):
        """两个字段完全相同的元素，配对结果由下标定，不由值定。

        Python 侧曾用 ``list.index()`` 排序，而 Element 是值对象——
        两个字段完全相同的元素会让 index() 指向同一个，排序结果不确定。
        改为显式记录 (prev_index, cur_index) 后修复。此用例是回归。
        """
        e = E("e1", "item", "同", (0, 0, 100, 100), class_name="V")
        e2 = E("e2", "item", "同", (0, 0, 100, 100), class_name="V")
        cs = diff([e, e2], [e2, e])
        # 四个候选对同为 70 分，按 (-70, i, j) 排序 → (0,0) 然后 (1,1)
        assert [(p.prev.ref, p.cur.ref) for p in cs.matched] == [("e1", "e2"), ("e2", "e1")]


import sys  # noqa: E402
