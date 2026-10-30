"""把 i18n/*.json 合成 static/i18n.js：python3 tools/build_i18n.py"""
import json, pathlib, re
R = pathlib.Path(__file__).resolve().parents[1]
en = json.loads((R / "i18n/en.json").read_text("utf-8"))
ph = lambda s: sorted(re.findall(r"\{\w+\}", s))
D = {}
for f in sorted((R / "i18n").glob("*.json")):
    d = json.loads(f.read_text("utf-8"))
    D[f.stem] = {k: v for k, v in d.items() if k in en and isinstance(v, str) and ph(v) == ph(en[k])}
    miss = [k for k in en if k not in D[f.stem]]
    print(f.stem, len(D[f.stem]), "missing->en:", miss)
core = (R / "tools/i18n_core.js").read_text("utf-8")
(R / "static/i18n.js").write_text("// 由 tools/build_i18n.py 生成，请改 i18n/*.json\nconst I18N = " + json.dumps(D, ensure_ascii=False, indent=0) + ";\n" + core, "utf-8")
