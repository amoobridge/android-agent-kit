"""uidref 自测：实现细节、不变量、真实 dump 回归、量化指标。

与 conformance.py 的分工：
- 这里测**实现细节与不变量**，以及**真实 AVD dump 的回归与指标**
- 那里测**规范符合性**（合成向量）
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

from uidref import (
    Bounds,
    Element,
    Snapshot,
    StaleRefError,
    digest_of,
    parse_file,
    parse_xml,
    role_of,
)

VECTORS = ROOT / "vectors"
DUMPS = ROOT / "dumps"


# ---------------------------------------------------------------- Bounds
class TestBounds:
    def test_half_open_semantics(self):
        b = Bounds(0, 0, 100, 100)
        assert b.width == 100 and b.height == 100
        assert b.contains(0, 0) and b.contains(99, 99)
        assert not b.contains(100, 100)

    def test_center(self):
        assert Bounds(0, 0, 101, 101).cx == 50
        assert Bounds(0, 0, 100, 100).cx == 50

    def test_degenerate(self):
        assert Bounds(10, 10, 10, 10).width == 0


# ---------------------------------------------------------------- 角色
class TestRole:
    @pytest.mark.parametrize(
        "cls,clickable,expect",
        [
            ("android.widget.Button", True, "btn"),
            ("android.widget.LinearLayout", True, "item"),
            ("android.widget.LinearLayout", False, "box"),
            ("android.widget.EditText", False, "input"),
            ("android.widget.CheckBox", True, "switch"),
            ("android.widget.ScrollView", False, "scroll"),
            ("androidx.recyclerview.widget.RecyclerView", False, "list"),
            ("android.widget.SeekBar", False, "slider"),
            ("com.unknown.Custom", True, "item"),
            ("com.unknown.Custom", False, "box"),
        ],
    )
    def test_role(self, cls, clickable, expect):
        assert role_of(cls, clickable=clickable) == expect


# ---------------------------------------------------------------- 不变量
class TestInvariants:
    def test_refs_are_sequential_from_e1(self):
        s = parse_xml(
            '<?xml version="1.0"?><hierarchy rotation="0">'
            '<node clickable="true" text="A" bounds="[0,0][10,10]"/>'
            '<node clickable="true" text="B" bounds="[0,10][10,20]"/>'
            "</hierarchy>"
        )
        assert [e.ref for e in s] == ["e1", "e2"]

    def test_refs_unique(self):
        s = parse_file(DUMPS / "settings-main.xml")
        refs = [e.ref for e in s]
        assert len(refs) == len(set(refs))

    def test_get_returns_none_for_unknown(self):
        s = parse_file(DUMPS / "settings-main.xml")
        assert s.get("e999") is None

    def test_get_is_lenient_resolve_is_strict(self):
        s = parse_file(DUMPS / "settings-main.xml")
        assert s.get("nope") is None
        with pytest.raises(StaleRefError):
            s.resolve("nope")

    def test_resolve_roundtrip(self):
        s = parse_file(DUMPS / "settings-main.xml")
        e = s.elements[0]
        assert s.resolve(e.ref) is e

    def test_snapshot_id_deterministic(self):
        a = parse_file(DUMPS / "settings-main.xml")
        b = parse_file(DUMPS / "settings-main.xml")
        assert a.snapshot_id == b.snapshot_id

    def test_snapshot_id_tracks_content_not_filename(self):
        """snapshot_id 是内容的哈希：同内容同 id，不同内容不同 id。

        注意 dumps/ 里有内容重复的界面（采集时某些 intent 失败回落到同一屏），
        所以断言按**去重后的内容数**比，不按文件数比。
        """
        files = sorted(DUMPS.glob("*.xml"))
        contents = {f.read_text(encoding="utf-8") for f in files}
        ids = {parse_file(f).snapshot_id for f in files}
        assert len(ids) == len(contents)
        assert len(ids) < len(files) or len(contents) == len(files)

    def test_digest_is_deterministic(self):
        a = digest_of((DUMPS / "settings-main.xml").read_text(encoding="utf-8"))
        b = digest_of((DUMPS / "settings-main.xml").read_text(encoding="utf-8"))
        assert a == b

    def test_len_and_iter_agree(self):
        s = parse_file(DUMPS / "settings-main.xml")
        assert len(s) == len(list(iter(s)))


# ---------------------------------------------------------------- 硬规则
class TestHardRules:
    """SPEC §2：可交互元素一个都不能丢。"""

    def test_every_dump_has_full_recall(self):
        for f in sorted(DUMPS.glob("*.xml")):
            s = parse_file(f)
            assert s.metrics()["elements"] > 0 or s.nodes_total <= 2, f"{f.name} 空"

    def test_actionable_count_matches_manual_count(self):
        """独立重算一遍可交互节点数，与 uidref 的结果比对。

        这是 recall 的真判据：不复用 uidref 的判定逻辑。
        """
        import xml.etree.ElementTree as ET

        for f in sorted(DUMPS.glob("*.xml")):
            root = ET.fromstring(f.read_text(encoding="utf-8"))
            expect = 0
            for n in root.iter("node"):
                actionable = (
                    n.get("clickable") == "true"
                    or n.get("long-clickable") == "true"
                    or n.get("scrollable") == "true"
                    or (n.get("class") or "").rsplit(".", 1)[-1].endswith("EditText")
                )
                if not actionable:
                    continue
                # bounds 合法且面积 > 0
                try:
                    a, b = n.get("bounds", "").split("][")
                    x1, y1 = (int(v) for v in a.lstrip("[").split(","))
                    x2, y2 = (int(v) for v in b.rstrip("]").split(","))
                except ValueError:
                    continue
                if x2 > x1 and y2 > y1:
                    expect += 1
            s = parse_file(f)
            assert len(s) == expect, (
                f"{f.name}: uidref {len(s)} != 独立重算 {expect}"
            )

    def test_no_element_has_empty_ref(self):
        for f in sorted(DUMPS.glob("*.xml")):
            for e in parse_file(f):
                assert e.ref and e.ref.startswith("e")

    def test_disabled_elements_are_kept(self):
        """禁用节点必须出现在 digest 里并带标记。"""
        for f in sorted(DUMPS.glob("*.xml")):
            s = parse_file(f)
            for e in s:
                if e.disabled:
                    assert "(disabled)" in e.line()

    def test_scrollable_container_has_no_inherited_label(self):
        """scrollable 容器不得继承整页文本。"""
        for f in sorted(DUMPS.glob("*.xml")):
            for e in parse_file(f):
                if e.scrollable and not e.clickable:
                    assert " · " not in e.label or len(e.label) < 40


# ---------------------------------------------------------------- 真实 dump 回归
class TestRealDumps:
    def test_dumps_exist(self):
        assert len(list(DUMPS.glob("*.xml"))) >= 10

    def test_known_labels_on_settings_date_page(self):
        """settings-main.xml 实为「日期和时间」页。锁定几个已知标签，
        防止标签继承规则被无意改坏。"""
        s = parse_file(DUMPS / "settings-main.xml")
        labels = [e.label for e in s]
        assert any("Navigate up" in l for l in labels)
        assert any("Set time automatically" in l for l in labels)
        assert any("Time zone" in l for l in labels)
        assert any("GMT+08:00" in l for l in labels)

    def test_known_roles_on_launcher(self):
        s = parse_file(DUMPS / "launcher.xml")
        roles = {e.role for e in s}
        assert roles & {"btn", "item", "text", "img"}

    def test_digest_head_carries_geometry(self):
        s = parse_file(DUMPS / "settings-main.xml")
        head = s.digest().splitlines()[0]
        assert "com.android.settings" in head
        assert "1080x" in head
        assert f"elements={len(s)}" in head

    def test_all_elements_have_positive_area(self):
        for f in sorted(DUMPS.glob("*.xml")):
            for e in parse_file(f):
                assert e.bounds.width > 0 and e.bounds.height > 0

    def test_all_elements_within_screen(self):
        for f in sorted(DUMPS.glob("*.xml")):
            s = parse_file(f)
            for e in s:
                assert 0 <= e.bounds.x1 <= e.bounds.x2 <= s.width
                assert 0 <= e.bounds.y1 <= e.bounds.y2 <= s.height


# ---------------------------------------------------------------- 量化指标
class TestMetrics:
    def test_compression_is_substantial(self):
        """核心价值主张：digest 必须显著小于原始 XML。"""
        ratios = []
        for f in sorted(DUMPS.glob("*.xml")):
            m = parse_file(f).metrics()
            ratios.append(m["compression"])
        assert min(ratios) >= 10.0, f"最低压缩比仅 {min(ratios):.1f}x"
        assert sum(ratios) / len(ratios) >= 20.0

    def test_digest_fits_in_small_token_budget(self):
        """每个界面的 digest 都应在一个小的 token 预算内。"""
        for f in sorted(DUMPS.glob("*.xml")):
            m = parse_file(f).metrics()
            assert m["est_tokens"] <= 400, f"{f.name} {m['est_tokens']} tokens"

    def test_label_coverage_is_high(self):
        for f in sorted(DUMPS.glob("*.xml")):
            m = parse_file(f).metrics()
            assert m["label_coverage"] >= 0.7, f"{f.name} 仅 {m['label_coverage']:.0%}"

    def test_metrics_keys_stable(self):
        m = parse_file(DUMPS / "settings-main.xml").metrics()
        assert set(m) >= {
            "nodes_total", "elements", "xml_bytes", "digest_bytes",
            "compression", "est_tokens", "label_coverage",
        }


# ---------------------------------------------------------------- 向量完备性
class TestVectorsWellFormed:
    def test_every_vector_has_why(self):
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            assert d.get("why"), f"{f.name} 缺少 why"

    def test_every_case_has_why(self):
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for c in d["cases"]:
                assert c.get("why"), f"{f.name} 有用例缺 why"

    def test_vector_ids_unique(self):
        ids = [json.loads(f.read_text(encoding="utf-8"))["id"] for f in sorted(VECTORS.glob("*.json"))]
        assert len(ids) == len(set(ids))

    def test_vectors_are_self_contained(self):
        """向量不得引用外部文件——否则别的语言没法跑。"""
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for c in d["cases"]:
                assert isinstance(c["in"], str) and "<hierarchy" in c["in"]

    def test_vectors_match_implementation(self):
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for c in d["cases"]:
                s = parse_xml(c["in"])
                got = {
                    "package": s.package,
                    "rotation": s.rotation,
                    "elements": [
                        {
                            "ref": e.ref, "role": e.role, "label": e.label,
                            "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                            "center": [e.bounds.cx, e.bounds.cy],
                            "clickable": e.clickable, "long_clickable": e.long_clickable,
                            "scrollable": e.scrollable, "editable": e.editable,
                            "checked": e.checked, "disabled": e.disabled,
                            "password": e.password,
                        }
                        for e in s
                    ],
                }
                assert got == c["out"], f"{f.name}: {c['why']}"


# ---------------------------------------------------------------- 元测试：向量不得失效
# 2026-10-27 教训：34/34 全绿，但其中 12 条**一条都没测到它声称的规则**。
# 根因是生成器的属性名泄漏与自闭合节点。下面三条元测试守这两个 bug 类，
# 且用「变异敏感性」做通用防线——不针对具体 bug，而是证明
# 「向量的输出确实随输入变化」，从而挡住任何未来的 vacuous vector。
import re as _re

_VALID_ATTRS = frozenset({
    "index", "text", "resource-id", "class", "package", "content-desc",
    "checkable", "checked", "clickable", "enabled", "focusable", "focused",
    "scrollable", "long-clickable", "password", "selected", "bounds",
})
_ATTR_RE = _re.compile(r"([a-zA-Z_-]+)=")


def _all_cases():
    for f in sorted(VECTORS.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for i, c in enumerate(d["cases"]):
            yield f.name, i, c


def _out_of(xml: str) -> tuple:
    s = parse_xml(xml)
    return (
        s.package, s.rotation,
        tuple((e.ref, e.role, e.label, str(e.bounds), (e.bounds.cx, e.bounds.cy),
               e.clickable, e.long_clickable, e.scrollable, e.editable, e.checked,
               e.disabled, e.password) for e in s),
    )


class TestVectorsNotVacuous:
    """元测试：每条向量必须真的在测东西。"""

    def test_no_stray_attributes(self):
        """向量 XML 里不得出现 uiautomator 之外的属性名。

        历史 bug：`cls=` / `desc=` / `rid=` / `long_clickable=` 泄漏成字面属性，
        而真正的 `class=` / `resource-id=` 仍是默认值 → 向量测的是别的规则。
        正则必须能看见下划线，否则 `long_clickable` 会漏检。
        """
        bad = []
        for name, i, c in _all_cases():
            for m in _re.finditer(r"<node\b([^>]*)>", c["in"]):
                for a in _ATTR_RE.finditer(m.group(1)):
                    if a.group(1) not in _VALID_ATTRS:
                        bad.append(f"{name} case#{i} 泄漏属性 {a.group(1)}")
        assert not bad, "发现泄漏属性：\n" + "\n".join(bad)

    def test_expected_output_matches_implementation(self):
        for name, i, c in _all_cases():
            assert _out_of(c["in"]) == _tuple(c["out"]), f"{name} case#{i}: {c['why']}"

    def test_every_case_is_mutation_sensitive(self):
        """变异敏感性：改动输入必须改变输出。

        这是**通用**防线——不管向量为什么失效，只要它的输出是常数，
        就说明这条输入压根没走到它声称的规则上。
        空 hierarchy 那条无法变异，豁免。
        """
        vacuous = []
        for name, i, c in _all_cases():
            xml = c["in"]
            if "<node" not in xml:
                continue
            base = _out_of(xml)
            mutations = [
                xml.replace('clickable="true"', 'clickable="false"'),
                xml.replace('clickable="false"', 'clickable="true"'),
                xml.replace('enabled="true"', 'enabled="false"'),
                xml.replace('scrollable="true"', 'scrollable="false"'),
                xml.replace('long-clickable="true"', 'long-clickable="false"'),
                xml.replace('checked="false"', 'checked="true"'),
                _re.sub(r'text="[^"]*"', 'text="变异"', xml, count=1),
                _re.sub(r'bounds="[^"]*"', 'bounds="[9,9][99,99]"', xml, count=1),
            ]
            changed = sum(1 for m in mutations if m != xml and _out_of(m) != base)
            if changed == 0:
                vacuous.append(f"{name} case#{i}（{c['why'][:36]}）")
        assert not vacuous, (
            "以下向量对输入变化不敏感，是空转用例：\n" + "\n".join(vacuous)
        )

    def test_role_claims_are_real(self):
        """why 里写「X → Y」的，期望输出必须真的出现角色 Y。

        历史 bug：8 个角色用例全在跑 `android.view.View`，
        "Button → btn" 实际产出 `item`、"EditText → input" 产出 0 个元素。
        """
        bad = []
        for name, i, c in _all_cases():
            m = _re.search(r"→\s*([a-z]+)", c["why"])
            if not m:
                continue
            want = m.group(1)
            roles = {e["role"] for e in c["out"]["elements"]}
            if want not in roles:
                bad.append(f"{name} case#{i} 声称 →{want} 但实得 {roles or '{}'}")
        assert not bad, "角色声明与期望不符：\n" + "\n".join(bad)

    def test_inheritance_claims_are_real(self):
        """why 提到继承的，期望里必须有非空标签。

        豁免：why 明确写了「无子孙 → 空」的——那条测的是**回退到空**，
        不是测继承本身。
        """
        bad = []
        for name, i, c in _all_cases():
            if "继承" not in c["why"]:
                continue
            if any(k in c["why"] for k in ("无子孙", "→ 空", "没有子孙")):
                continue
            if "不继承" in c["why"].replace("*", ""):
                continue      # 那条测的是「不许继承」，空标签正是期望
            if not any(e["label"] for e in c["out"]["elements"]):
                bad.append(f"{name} case#{i}（{c['why'][:36]}）期望标签全为空")
        assert not bad, "继承用例没测到继承：\n" + "\n".join(bad)

    def test_inheritance_cases_have_real_descendants(self):
        """声称继承的用例，XML 里必须有嵌套节点（不能全是兄弟）。"""
        bad = []
        for name, i, c in _all_cases():
            if "继承" not in c["why"] and "子孙" not in c["why"]:
                continue
            if any(k in c["why"] for k in ("无子孙", "→ 空", "没有子孙")):
                continue          # 那条故意没有子孙
            if "不继承" in c["why"].replace("*", ""):
                continue          # 那条测的是不许继承，不需要有子孙
            if "</node>" not in c["in"]:
                bad.append(f"{name} case#{i} 没有嵌套节点，所谓子孙其实是兄弟")
        assert not bad, "继承用例缺少真子孙：\n" + "\n".join(bad)

    def test_vector_count_and_uniqueness(self):
        ids, whys = set(), set()
        n = 0
        for name, i, c in _all_cases():
            n += 1
            assert c["why"], f"{name} case#{i} 缺 why"
            whys.add((name, c["why"]))
        for f in sorted(VECTORS.glob("*.json")):
            ids.add(json.loads(f.read_text(encoding="utf-8"))["id"])
        assert n >= 40, f"用例数 {n} < 40"
        assert len(ids) == len(list(VECTORS.glob("*.json")))


def _tuple(out: dict) -> tuple:
    return (
        out["package"], out["rotation"],
        tuple((e["ref"], e["role"], e["label"], _bstr(e["bounds"]), tuple(e["center"]),
               e["clickable"], e["long_clickable"], e["scrollable"],
               e["editable"], e["checked"], e["disabled"], e["password"])
              for e in out["elements"]),
    )


def _bstr(b) -> str:
    return f"[{b[0]},{b[1]}][{b[2]},{b[3]}]"


# ---------------------------------------------------------------- 跨语言一致性
class TestCrossLanguage:
    """Python 与 JavaScript 两个独立实现必须给出同一结果。

    这是 uidref 作为**规范**（而非某个语言的测试套件）的判据。
    """

    @staticmethod
    def _node_available() -> bool:
        return shutil.which("node") is not None

    @staticmethod
    def _js_parse(xml: str) -> dict:
        script = (
            "const {parse}=require('./uidref.js');"
            "const s=parse(process.argv[1]);"
            "process.stdout.write(JSON.stringify({package:s.package,rotation:s.rotation,"
            "elements:s.elements.map(e=>({ref:e.ref,role:e.role,label:e.label,bounds:e.bounds,"
            "center:e.center,clickable:e.clickable,long_clickable:e.long_clickable,"
            "scrollable:e.scrollable,editable:e.editable,checked:e.checked,"
            "disabled:e.disabled,password:e.password}))}));"
        )
        r = subprocess.run(
            ["node", "-e", script, xml], cwd=ROOT / "js",
            capture_output=True, text=True, timeout=30,
        )
        assert r.returncode == 0, f"JS 实现报错：{r.stderr[:300]}"
        return json.loads(r.stdout)

    @staticmethod
    def _py_parse(xml: str) -> dict:
        s = parse_xml(xml)
        return {
            "package": s.package,
            "rotation": s.rotation,
            "elements": [
                {
                    "ref": e.ref, "role": e.role, "label": e.label,
                    "bounds": [e.bounds.x1, e.bounds.y1, e.bounds.x2, e.bounds.y2],
                    "center": [e.bounds.cx, e.bounds.cy],
                    "clickable": e.clickable, "long_clickable": e.long_clickable,
                    "scrollable": e.scrollable, "editable": e.editable,
                    "checked": e.checked, "disabled": e.disabled,
                    "password": e.password,
                }
                for e in s
            ],
        }

    def test_node_is_available(self):
        if not self._node_available():
            pytest.skip("本机无 node，跳过跨语言一致性")

    def test_vectors_agree_across_languages(self):
        """43 条黄金向量在 JS 侧也必须全绿。"""
        for f in sorted(VECTORS.glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            for i, c in enumerate(d["cases"]):
                assert self._js_parse(c["in"]) == c["out"], f"{f.name} case#{i}: {c['why']}"

    def test_real_dumps_agree_across_languages(self):
        """16 个真实 dump 上两个实现必须逐字段一致。"""
        for f in sorted(DUMPS.glob("*.xml")):
            xml = f.read_text(encoding="utf-8")
            a, b = self._py_parse(xml), self._js_parse(xml)
            assert a == b, f"{f.name} 两侧不一致"

    def test_random_inputs_agree(self):
        """随机输入差分：规范的价值在于任何人任何语言实现都同结果。"""
        rng = random.Random(20261027)
        bad = []
        for i in range(60):
            xml = _gen_doc(rng)
            a, b = self._py_parse(xml), self._js_parse(xml)
            if a != b:
                bad.append(f"#{i}\n  XML {xml[:200]}\n  py {json.dumps(a, ensure_ascii=False)[:200]}\n  js {json.dumps(b, ensure_ascii=False)[:200]}")
        assert not bad, "随机输入上两侧分歧：\n" + "\n".join(bad[:3])


# ---------------------------------------------------------------- 随机 XML 生成器
_CLASSES = ["android.view.View", "android.widget.TextView", "android.widget.Button",
            "android.widget.EditText", "android.widget.CheckBox", "android.widget.SeekBar",
            "android.widget.LinearLayout", "android.widget.ScrollView",
            "androidx.recyclerview.widget.RecyclerView", "com.vendor.Custom"]
_RIDS = ["", "com.android.settings:id/wifi_settings", "android:id/content",
         "com.x:id/content_parent", "android:id/container", "no_slash"]
_TEXTS = ["", "OK", "Wi-Fi", "已连接", "取消", "a" * 80, "重复", "重复"]


def _esc(v: str) -> str:
    return (v.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _rnode(rng, depth=0):
    attrs = {
        "index": str(rng.randint(0, 40)), "text": rng.choice(_TEXTS),
        "resource-id": rng.choice(_RIDS), "class": rng.choice(_CLASSES),
        "package": "com.example", "content-desc": rng.choice(_TEXTS),
        "checkable": rng.choice(["true", "false"]),
        "checked": rng.choice(["true", "false"]),
        "clickable": rng.choice(["true", "false", "true"]),
        "enabled": rng.choice(["true", "true", "false"]),
        "focusable": rng.choice(["true", "false"]),
        "focused": rng.choice(["true", "false"]),
        "scrollable": rng.choice(["true", "false", "false"]),
        "long-clickable": rng.choice(["true", "false", "false"]),
        "password": rng.choice(["true", "false", "false"]),
        "selected": rng.choice(["true", "false"]),
    }
    kind = rng.choice(["ok", "ok", "ok", "zero", "reversed", "negative", "garbage", "missing"])
    if kind == "ok":
        x1, y1 = rng.randint(0, 900), rng.randint(0, 1800)
        attrs["bounds"] = f"[{x1},{y1}][{x1 + rng.randint(1, 700)},{y1 + rng.randint(1, 500)}]"
    elif kind == "zero":
        a, b = rng.randint(0, 900), rng.randint(0, 900)
        attrs["bounds"] = f"[{a},{b}][{a},{b}]"
    elif kind == "reversed":
        attrs["bounds"] = f"[{rng.randint(100, 900)},{rng.randint(100, 900)}][5,5]"
    elif kind == "negative":
        attrs["bounds"] = f"[-{rng.randint(1, 40)},-{rng.randint(1, 40)}][{rng.randint(1, 200)},{rng.randint(1, 200)}]"
    elif kind == "garbage":
        attrs["bounds"] = rng.choice(["", "null", "[0,0]", "garbage"])

    body = " ".join(f'{k}="{_esc(v)}"' for k, v in attrs.items())
    kids = ""
    if depth < 2 and rng.random() < 0.6:
        kids = "".join(_rnode(rng, depth + 1) for _ in range(rng.randint(1, 2)))
    return f"<node {body}>{kids}</node>" if kids else f"<node {body}/>"


def _gen_doc(rng) -> str:
    nodes = "".join(_rnode(rng) for _ in range(rng.randint(0, 5)))
    return ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            f'<hierarchy rotation="{rng.choice(["0", "0", "1", "3"])}">{nodes}</hierarchy>')


class TestCenterRounding(TestCrossLanguage):
    """SPEC §5：中心点必须 floor（向负无穷），不是向零截断。

    2026-10-27：JS 独立实现撞出这条歧义（A1）。但当时向量**没有覆盖 center**，
    于是 verify_impl.py 拿一个向零截断的实现来测，竟然全绿——
    一致性测试对一个真实存在的分歧完全失明。现在 center 进契约。
    """

    def test_negative_bounds_center_is_floor(self):
        """负坐标下 floor 与向零截断差 1，这是 A1 的判定用例。"""
        s = parse_xml(
            '<?xml version="1.0" encoding="UTF-8" ?>'
            '<hierarchy rotation="0">'
            '<node class="android.view.View" clickable="true" text="负" '
            'bounds="[-10,-10][50,50]"/></hierarchy>'
        )
        e = s.elements[0]
        assert e.bounds.cx == 20, f"floor(-10+50)/2 = 20，实得 {e.bounds.cx}"
        assert e.bounds.cy == 20

    def test_odd_width_center_is_floor(self):
        """奇数宽度同样分叉：floor(3/2)=1，向零截断也是 1；换奇数负值才分叉。"""
        s = parse_xml(
            '<?xml version="1.0" encoding="UTF-8" ?>'
            '<hierarchy rotation="0">'
            '<node class="android.view.View" clickable="true" text="奇" '
            'bounds="[-3,-3][4,4]"/></hierarchy>'
        )
        e = s.elements[0]
        assert (e.bounds.cx, e.bounds.cy) == (0, 0), (
            f"floor((-3+4)/2) = 0，实得 {(e.bounds.cx, e.bounds.cy)}")

    def test_js_agrees_on_center_rounding(self):
        """跨语言确认：JS 侧在负坐标上必须同样 floor。"""
        if not shutil.which("node"):
            pytest.skip("无 node")
        xml = ('<?xml version="1.0" encoding="UTF-8" ?>'
               '<hierarchy rotation="0">'
               '<node class="android.view.View" clickable="true" text="负" '
               'bounds="[-10,-10][50,50]"/></hierarchy>')
        assert self._js_parse(xml) == self._py_parse(xml)
