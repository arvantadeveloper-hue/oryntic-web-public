import glob, re

REPL = [
    ("text-white", "text-slate-900"),
    ("text-slate-200", "text-slate-700"),
    ("text-slate-300", "text-slate-600"),
    ("text-slate-400", "text-slate-500"),
    ("bg-[#0e1830]", "bg-slate-50"),
    ("bg-[#1C2D5A]", "bg-slate-100"),
    ("bg-[#111C3A]", "bg-white"),
    ("bg-[#162244]", "bg-slate-50"),
    ("border-slate-600", "border-slate-200"),
    ("border-slate-500", "border-slate-300"),
    ("divide-[rgba(148,163,184,.1)]", "divide-slate-100"),
    ("border-[rgba(148,163,184,.15)]", "border-slate-200"),
    ("border-[rgba(148,163,184,.12)]", "border-slate-200"),
    ("border-[rgba(148,163,184,.1)]", "border-slate-200"),
    ("border-[rgba(0,209,255,.1)]", "border-slate-200"),
    ("border-[rgba(0,209,255,0.1)]", "border-slate-200"),
    ("text-[#00D1FF]", "text-[#2F6BFF]"),
]

# files to migrate (exclude ones we fully rewrite separately)
EXCLUDE = {"Auth.jsx", "Home.jsx"}
files = glob.glob("/app/frontend/src/pages/*.jsx")
for f in files:
    if f.split("/")[-1] in EXCLUDE:
        continue
    s = open(f).read()
    orig = s
    for a, b in REPL:
        s = s.replace(a, b)
    if s != orig:
        open(f, "w").write(s)
        print("migrated", f.split("/")[-1])
print("done")
