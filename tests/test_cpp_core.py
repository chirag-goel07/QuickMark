"""C++ core vs. the ORIGINAL Python logic: same answers on thousands of random inputs.
Run from the project folder:  python tests/test_cpp_core.py   (builds the C++ library first if needed)"""
import csv, io, math, os, random, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
from services import core

ok = bad = 0
def check(name, cond):
    global ok, bad
    print(("PASS  " if cond else "FAIL  ") + name); ok += cond; bad += (not cond)

random.seed(7)
print("library:", core.version())

# ---- reference versions (the code that used to be in Python)
def ref_pct(p, t): return round(100.0 * p / t, 1) if t else None
def ref_advice(present, total, threshold):
    if total == 0: return None
    if 100 * present >= threshold * total:
        return {"status": "ok", "can_miss": int((100 * present - threshold * total) // threshold if threshold > 0 else 0)}
    if threshold >= 100: return {"status": "below", "classes_needed": None}
    return {"status": "below", "classes_needed": int(-(-(threshold * total - 100 * present) // (100 - threshold)))}
def ref_nat(x): return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", x)]
def ref_safe(c):
    if isinstance(c, str) and c[:1] in ("=", "+", "-", "@", "\t", "\r"): return "'" + c
    return "" if c is None else c

# percentage + advice
pairs = [(random.randint(0, t), t) for t in [random.randint(0, 400) for _ in range(5000)]]
check("percentage identical (incl. .x5 tie cases)", all(core.percent(p, t) == ref_pct(p, t) for p, t in pairs)
      and all(core.percent(1, d) == ref_pct(1, d) for d in range(1, 400)))
check("threshold advice identical", all(core.advice(p, t, th) == ref_advice(p, t, th)
      for (p, t) in pairs[:3000] for th in (random.randint(1, 100),)) and all(core.advice(p, 20, th) == ref_advice(p, 20, th) for p in range(21) for th in range(1, 101)))

# sorting
vals = [{"id": i, "v": random.choice([0, 12.5, 33.3, 50, 75, random.random() * 100])} for i in range(600)]
check("stable sort by percentage identical", core.sorted_by_value(vals, key=lambda x: x["v"]) == sorted(vals, key=lambda x: x["v"]))
alpha = "AaBb01234569- "
rolls = ["".join(random.choice(alpha) for _ in range(random.randint(0, 7))) for _ in range(3000)] + ["007", "7", "21CS2", "21CS10", "a10", "A9", "99999999999999999999", "100000000000000000000"]
rows = [{"roll_no": r} for r in rolls]
check("natural roll-number order identical (incl. leading zeros, huge numbers, mixed case)",
      core.natural_sorted(rows, key=lambda x: x["roll_no"]) == sorted(rows, key=lambda x: ref_nat(x["roll_no"])))
check("empty and one-item lists", core.natural_sorted([]) == [] and core.sorted_by_value([5], key=lambda x: x) == [5])

# streak
def ref_streak(flags):
    n = 0
    for f in flags:
        if not f: break
        n += 1
    return n
fl = [[random.random() < .7 for _ in range(random.randint(0, 30))] for _ in range(1000)]
check("streak identical", all(core.leading_streak(f) == ref_streak(f) for f in fl))

# face
vecs = [[random.uniform(-1, 1) for _ in range(128)] for _ in range(300)]
d_ref = lambda a, b: math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
# Python 3.12 sum() uses compensated summation, so the last bit can differ; the match threshold is 0.5, so 1e-12 is far below anything that matters
check("face distance matches Python to 1e-12", all(abs(core.face_distance(vecs[i], vecs[i + 1]) - d_ref(vecs[i], vecs[i + 1])) < 1e-12 for i in range(299)))
ok1, avg = core.face_enroll(vecs[:3], 99)
check("enroll average identical", ok1 and avg == [sum(v[k] for v in vecs[:3]) / 3 for k in range(128)])
base = [random.uniform(-1, 1) for _ in range(128)]
near = lambda: [x + random.uniform(-.01, .01) for x in base]
check("same-face captures accepted, different faces rejected", core.face_enroll([near() for _ in range(3)], 0.45)[0] and not core.face_enroll([near(), near(), vecs[0]], 0.45)[0])
check("descriptor validation", core.face_is_valid(base) and not core.face_is_valid(base[:127]) and not core.face_is_valid(base[:-1] + [9.0])
      and not core.face_is_valid(base[:-1] + [float("nan")]) and not core.face_is_valid(base[:-1] + [float("inf")]))
core.lockout_reset_all()
for i in range(5): core.lockout_fail(1, 1000 + i)
check("lock-out: 5 failures lock, other student unaffected, wait unlocks, clear resets",
      core.lockout_is_locked(1, 1010, 60, 5) and not core.lockout_is_locked(2, 1010, 60, 5) and not core.lockout_is_locked(1, 1100, 60, 5)
      and (core.lockout_clear(1) or core.lockout_count(1) == 0))

# rate limiter
core.rate_reset()
res = [core.rate_allow("k", 3, 10, t) for t in (0, 1, 2, 3, 11, 11.5)]
check("rate limiter: 3 allowed, 4th refused, window slides", res == [True, True, True, False, True, True])
check("rate limiter: keys independent", core.rate_allow("other", 1, 10, 0) and not core.rate_allow("other", 1, 10, 1))

# csv
cells = ["Asha", "=SUM(A1)", "+1", "-1", "@x", "\tx", "a,b", 'say "hi"', "line\nbreak", "", "é ü 名前", 12, 83.3, -5, None, 0]
tests = [cells, [""], ["x"], [None], [-5, "-5"], ["a"] * 3]
buf = io.StringIO()
writer = csv.writer(buf)
for r in tests:
    writer.writerow([ref_safe(c) for c in r])
check("CSV rows identical to Python's csv module (quoting, newlines, unicode, numbers stay numbers)",
      core.csv_text(tests[0], tests[1:]) == "\ufeff" + buf.getvalue())
check("csv_safe identical", all(core.csv_safe(c) == ref_safe(c) for c in cells))

print(f"\n{ok}/{ok + bad} passed"); sys.exit(1 if bad else 0)
