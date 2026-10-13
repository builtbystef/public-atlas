"""Hand-made mutation probes: inject one fault, run the tests that should catch it, restore.

Run from apps/server; arguments are id prefixes (`Q`, `B3`) that limit the run to those probes.
Each probe names the source file, the exact text to replace, the replacement, and the test paths
to run. A probe is KILLED when the tests fail, SURVIVED when they pass (the suite did not notice
the fault), NO-MATCH when the text is no longer in the source."""

import subprocess
import sys
from pathlib import Path

SRC = Path("src/public_atlas")
T = Path("tests")

PROBES = [
    # --- evidence/quote_checks.py: the evidence invariant ---
    (
        "Q1 short quotes accepted (MIN_QUOTE_CHARS 12 -> 1)",
        SRC / "modules/evidence/quote_checks.py",
        "MIN_QUOTE_CHARS = 12",
        "MIN_QUOTE_CHARS = 1",
        [T / "unit/evidence"],
    ),
    (
        "Q2 whitespace-squash fallback removed from _contains",
        SRC / "modules/evidence/quote_checks.py",
        "return needle in normalize_text(haystack) or _squash(needle) in _squash(haystack)",
        "return needle in normalize_text(haystack)",
        [T / "unit/evidence"],
    ),
    (
        "Q3 same_address no longer ignores www.",
        SRC / "modules/evidence/quote_checks.py",
        'host = (parts.netloc or "").removeprefix("www.")',
        'host = (parts.netloc or "")',
        [T / "unit/evidence"],
    ),
    (
        "Q4 mentions_any: an empty name matches every text",
        SRC / "modules/evidence/quote_checks.py",
        "return any(key(name) in haystack for name in names if name.strip())",
        "return any(key(name) in haystack for name in names)",
        [T / "unit/evidence"],
    ),
    (
        "Q5 find_quote: multi-page text reports page 1 for every hit",
        SRC / "modules/evidence/quote_checks.py",
        "return Found(page=number)",
        "return Found(page=1)",
        [T / "unit/evidence"],
    ),
    # --- assignments/pricing.py: money ---
    (
        "P1 output tokens also charged as input",
        SRC / "modules/assignments/pricing.py",
        "uncached = max(units - output_units - cached_units, 0)",
        "uncached = max(units - cached_units, 0)",
        [T / "unit/assignments/test_pricing.py"],
    ),
    (
        "P2 cached input charged at the full input price",
        SRC / "modules/assignments/pricing.py",
        "cached_units * model.cached_input",
        "cached_units * model.input",
        [T / "unit/assignments/test_pricing.py"],
    ),
    (
        "P3 search priced per call, not per request unit",
        SRC / "modules/assignments/pricing.py",
        "return None if price is None else price * units",
        "return None if price is None else price",
        [T / "unit/assignments/test_pricing.py"],
    ),
    # --- assignments/lifecycle.py: the status door ---
    (
        "L1 a result may accompany any status",
        SRC / "modules/assignments/lifecycle.py",
        "if (result is not None) != (status is AssignmentStatus.FINISHED):",
        "if False:",
        [T / "unit/assignments/test_lifecycle.py"],
    ),
    (
        "L2 finished may go back to queued",
        SRC / "modules/assignments/lifecycle.py",
        "AssignmentStatus.FINISHED: frozenset(),",
        "AssignmentStatus.FINISHED: frozenset({AssignmentStatus.QUEUED}),",
        [T / "unit/assignments/test_lifecycle.py"],
    ),
    (
        "L3 started_at overwritten on every start",
        SRC / "modules/assignments/lifecycle.py",
        "if assignment.started_at is None:\n        assignment.started_at = utcnow()",
        "assignment.started_at = utcnow()",
        [T / "unit/assignments/test_lifecycle.py"],
    ),
    # --- integrations/browser/policy.py: the security boundary ---
    (
        "B1 suffix match without the dot (evilontario.ca matches ontario.ca)",
        SRC / "integrations/browser/policy.py",
        'return host == domain or host.endswith("." + domain)',
        "return host == domain or host.endswith(domain)",
        [T / "unit/integrations/test_browser_policy.py", T / "unit/integrations/test_browser_fetch.py"],
    ),
    (
        "B2 IPv4-mapped IPv6 loopback not unwrapped",
        SRC / "integrations/browser/policy.py",
        "if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:\n        ip = ip.ipv4_mapped",
        "pass",
        [T / "unit/integrations/test_browser_policy.py"],
    ),
    (
        "B3 link-local addresses allowed",
        SRC / "integrations/browser/policy.py",
        "        or ip.is_link_local\n",
        "",
        [T / "unit/integrations/test_browser_policy.py"],
    ),
    (
        "B4 .localhost subdomains allowed",
        SRC / "integrations/browser/policy.py",
        'if host == "localhost" or host.endswith(".localhost"):',
        'if host == "localhost":',
        [T / "unit/integrations/test_browser_policy.py"],
    ),
    (
        "B5 unresolved host passes instead of refusing",
        SRC / "integrations/browser/policy.py",
        "except TimeoutError, OSError, UnicodeError:\n        return None",
        "except TimeoutError, OSError, UnicodeError:\n        return ()",
        [T / "unit/integrations/test_browser_policy.py"],
    ),
    # --- evals/scorer: the measurements ---
    (
        "S1 recall with no labelled rows reads 0.0 instead of None",
        SRC / "modules/evals/scorer/tally.py",
        "return self.hits / total if total else None\n\n    @property\n    def precision",
        "return self.hits / total if total else 0.0\n\n    @property\n    def precision",
        [T / "unit/evals"],
    ),
    (
        "S2 precision divides by hits+misses",
        SRC / "modules/evals/scorer/tally.py",
        "total = self.hits + self.false_positives\n        return self.hits / total if total else None",
        "total = self.hits + self.misses\n        return self.hits / total if total else None",
        [T / "unit/evals"],
    ),
    (
        "S3 'wrong' no longer counts as a false positive",
        SRC / "modules/evals/scorer/tally.py",
        'return self.kind in ("false_positive", "wrong")',
        'return self.kind in ("false_positive",)',
        [T / "unit/evals"],
    ),
    (
        "S4 homepage path prefix without the slash (/a matches /ab)",
        SRC / "modules/evals/scorer/rules.py",
        'saved_path.startswith(expected_path + "/")',
        "saved_path.startswith(expected_path)",
        [T / "unit/evals"],
    ),
    (
        "S5 same_site true for empty hosts",
        SRC / "modules/evals/scorer/rules.py",
        'return bool(a) and bool(b) and (a == b or a.endswith("." + b) or b.endswith("." + a))',
        'return a == b or a.endswith("." + b) or b.endswith("." + a)',
        [T / "unit/evals"],
    ),
]


def run(probe):
    """Apply one probe, run its tests, and restore the file with `git checkout`: the name, the
    outcome, and the first failing test or the last line of output."""
    name, path, old, new, tests = probe
    text = path.read_text()
    if old not in text:
        return name, "NO-MATCH", ""
    path.write_text(text.replace(old, new, 1))
    try:
        proc = subprocess.run(
            ["uv", "run", "pytest", "-q", "-x", "-p", "no:cacheprovider", *map(str, tests)],
            capture_output=True,
            text=True,
            timeout=900,
        )
    finally:
        subprocess.run(["git", "checkout", "--", str(path)], check=True)
    tail = [line for line in proc.stdout.splitlines() if line.strip()][-1:]
    status = "KILLED" if proc.returncode != 0 else "SURVIVED"
    failing = next((line for line in proc.stdout.splitlines() if line.startswith("FAILED")), "")
    return name, status, (failing or (tail[0] if tail else ""))[:160]


if __name__ == "__main__":
    only = sys.argv[1:]
    results = []
    for probe in PROBES:
        if only and not any(probe[0].startswith(prefix) for prefix in only):
            continue
        result = run(probe)
        print(f"{result[1]:9} {result[0]}  | {result[2]}", flush=True)
        results.append(result)
    killed = sum(r[1] == "KILLED" for r in results)
    print(f"\n{killed}/{len(results)} killed")
