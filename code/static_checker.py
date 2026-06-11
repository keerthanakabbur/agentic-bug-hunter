"""
static_checker.py
-----------------
Rule-based bug detector for RDI C++ API code.
No LLM, no MCP — pure pattern matching.
Catches the most common bug categories reliably and instantly.

Returns: {"bug_line": int, "reason": str, "confidence": "high"/"medium"}
or None if no rule fires.
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class BugResult:
    bug_line: int
    reason: str
    confidence: str  # "high" or "medium"


def check(code: str) -> Optional[BugResult]:
    """
    Run all static rules on the code. Returns first high-confidence
    match, or first medium match, or None.
    """
    lines = code.split("\n")
    results = []

    for rule in RULES:
        r = rule(lines)
        if r:
            results.append(r)

    # Prefer high confidence
    high = [r for r in results if r.confidence == "high"]
    if high:
        return high[0]
    if results:
        return results[0]
    return None


# ─────────────────────────────────────────────────────────────────────────────
#  Rule helpers
# ─────────────────────────────────────────────────────────────────────────────

def strip(line: str) -> str:
    return line.strip()

def contains(line: str, *tokens) -> bool:
    return any(t in line for t in tokens)

def find_line(lines, *tokens) -> int:
    """Return 1-based line number of first line containing all tokens, or 0."""
    for i, l in enumerate(lines):
        if all(t in l for t in tokens):
            return i + 1
    return 0

def find_all(lines, *tokens) -> list[int]:
    return [i+1 for i, l in enumerate(lines) if all(t in l for t in tokens)]


# ─────────────────────────────────────────────────────────────────────────────
#  Rules  (each is a function(lines) -> BugResult | None)
# ─────────────────────────────────────────────────────────────────────────────

def rule_rdi_end_before_begin(lines):
    """RDI_END() appears before RDI_BEGIN() — lifecycle order violation."""
    end_line   = find_line(lines, "RDI_END")
    begin_line = find_line(lines, "RDI_BEGIN")
    if end_line and begin_line and end_line < begin_line:
        return BugResult(
            bug_line=end_line,
            reason="RDI_END() called before RDI_BEGIN(), violating the required lifecycle order",
            confidence="high",
        )

def rule_veceditmode_outside_begin(lines):
    """vecEditMode() must be called OUTSIDE RDI_BEGIN/RDI_END."""
    begin = find_line(lines, "RDI_BEGIN")
    end   = find_line(lines, "RDI_END")
    vec   = find_line(lines, "vecEditMode")
    if vec and begin and end and begin < vec < end:
        return BugResult(
            bug_line=vec,
            reason="vecEditMode() must be called outside RDI_BEGIN/RDI_END, not inside",
            confidence="high",
        )

def rule_veceditmode_wrong_enum(lines):
    """vecEditMode must use TA::VTT, not TA::VECD or other wrong values."""
    wrong_enums = ["TA::VECD", "TA::VEC", "TA::EDIT"]
    for i, l in enumerate(lines):
        if "vecEditMode" in l:
            for bad in wrong_enums:
                if bad in l:
                    return BugResult(
                        bug_line=i + 1,
                        reason=f"vecEditMode() uses wrong enum {bad}, should be TA::VTT",
                        confidence="high",
                    )

def rule_burst_called_twice_same_port(lines):
    """Only one burstRunTime command per port."""
    port_bursts: dict[str, list[int]] = {}
    for i, l in enumerate(lines):
        m = re.search(r'rdi\.port\(["\'](\w+)["\']\).*\.burst\(', l)
        if m:
            port = m.group(1)
            port_bursts.setdefault(port, []).append(i + 1)
    for port, lnums in port_bursts.items():
        if len(lnums) > 1:
            return BugResult(
                bug_line=lnums[1],
                reason=f"burst() called more than once for port '{port}' — only one burstRunTime command allowed per port",
                confidence="high",
            )

def rule_duplicate_method_in_chain(lines):
    """Detect same method called twice in consecutive chain lines."""
    # Join continuation lines (lines ending with . or starting with .)
    seen_methods = []
    for i, l in enumerate(lines):
        stripped = l.strip()
        calls = re.findall(r'\.(\w+)\(', stripped)
        for c in calls:
            if c in seen_methods and c not in ("execute", "burst", "end", "begin"):
                return BugResult(
                    bug_line=i + 1,
                    reason=f"Method .{c}() appears to be called more than once in the same chain",
                    confidence="medium",
                )
        # Reset on non-chain lines (no leading/trailing dot)
        if stripped and not stripped.startswith(".") and not stripped.endswith("."):
            seen_methods = calls
        else:
            seen_methods.extend(calls)

def rule_wrong_vforce_unit(lines):
    """vForce unit should be mA or V, not uA for DC port operations."""
    for i, l in enumerate(lines):
        if "vForce" in l and "uA" in l:
            return BugResult(
                bug_line=i + 1,
                reason="vForce() uses current unit 'uA' — vForce sets voltage and should use mV/V, not uA",
                confidence="high",
            )

def rule_wrong_iforce_unit(lines):
    """iForce unit should be uA/mA, not V."""
    for i, l in enumerate(lines):
        if "iForce" in l and re.search(r'\b\d+\s*[Vv]\b', l):
            return BugResult(
                bug_line=i + 1,
                reason="iForce() uses voltage unit — iForce sets current and should use uA/mA, not V",
                confidence="high",
            )

def rule_iclamp_before_iforce_range(lines):
    """iClamp must be set after iForceRange, not before."""
    iclamp_line     = find_line(lines, "iClamp")
    iforce_r_line   = find_line(lines, "iForceRange")
    if iclamp_line and iforce_r_line and iclamp_line < iforce_r_line:
        return BugResult(
            bug_line=iclamp_line,
            reason="iClamp() called before iForceRange() — iForceRange must be set first per AVI64 documentation",
            confidence="high",
        )

def rule_iforce_before_vforce(lines):
    """iForceRange must come after vForce in DC scale pin setup."""
    iforce_r = find_line(lines, "iForceRange")
    vforce   = find_line(lines, "vForce")
    if iforce_r and vforce and iforce_r < vforce:
        return BugResult(
            bug_line=iforce_r,
            reason="iForceRange() called before vForce() — the correct order is vForce then iForceRange per DC scale pin documentation",
            confidence="high",
        )

def rule_wrong_method_name(lines):
    """Common method name typos."""
    TYPOS = {
        "getFFC":           ("getFFV",    "rdi.emap().FFV documentation requires getFFV"),
        "getFFc":           ("getFFV",    "rdi.emap().FFV documentation requires getFFV"),
        "readHumanSeniority":("readHumSensor","PMUX sensor documentation requires readHumSensor"),
        "interS(":          ("interSkip","digital capture test setup requires interSkip"),
        "getVesjkctor":     ("getVector", "Hidden upload documentation requires getVector"),
        "readTempThresh(":  ("readTempThresh()","readTempThresh takes no parameters per PMUX docs"),
        "writeBurst":       None,  # Not a typo — skip
    }
    for i, l in enumerate(lines):
        for wrong, fix in TYPOS.items():
            if fix is None:
                continue
            if wrong in l:
                correct, rule = fix
                return BugResult(
                    bug_line=i + 1,
                    reason=f"Wrong method '{wrong}' — should be '{correct}': {rule}",
                    confidence="high",
                )

def rule_write_instead_of_writeburst(lines):
    """protocol().write() used when writeBurst() is needed for burst data."""
    for i, l in enumerate(lines):
        if "protocol()" in l and ".write(" in l and "writeBurst" not in l:
            # Check if burst context
            context_lines = "\n".join(lines)
            if any(k in context_lines for k in ["ARRAY_I", "burst", "Burst"]):
                return BugResult(
                    bug_line=i + 1,
                    reason="protocol().write() used for burst data — should be protocol().writeBurst() per SmartRDI 2.1.0",
                    confidence="medium",
                )

def rule_samples_exceed_burst_limit(lines):
    """Sample count > 8192 violates DIGCAP_BURST_SITE_UPLOAD rule."""
    for i, l in enumerate(lines):
        m = re.search(r'\.samples\((\d+)\)', l)
        if m and int(m.group(1)) > 8192:
            return BugResult(
                bug_line=i + 1,
                reason=f"samples({m.group(1)}) exceeds maximum 8192 allowed when burst site upload is enabled",
                confidence="high",
            )

def rule_end_called_twice(lines):
    """end() called twice — need wait() between them per cogo rules."""
    end_lines = find_all(lines, ".end()")
    if len(end_lines) >= 2:
        return BugResult(
            bug_line=end_lines[1],
            reason="end() called twice — rdi.cogo().wait() must be called between end() calls per Important Rules doc",
            confidence="high",
        )

def rule_burst_upload_wrong_chain(lines):
    """burstUpload should be rdi.smartVec(id).burstUpload(), not rdi.burstUpload.smartVec()."""
    for i, l in enumerate(lines):
        if "burstUpload" in l and "smartVec" in l:
            if re.search(r'rdi\.burstUpload', l):
                return BugResult(
                    bug_line=i + 1,
                    reason="Wrong chain order: should be rdi.smartVec('id').burstUpload().end(), not rdi.burstUpload.smartVec()",
                    confidence="high",
                )

def rule_uninitialized_port_variable(lines):
    """Port variable used in burst without prior initialization."""
    declared = set()
    for i, l in enumerate(lines):
        # Track declared variables (simple heuristic)
        m = re.search(r'\b(\w+)\s*=\s*rdi\.port\(', l)
        if m:
            declared.add(m.group(1))
        # Check burst call uses undeclared var
        m2 = re.search(r'(\w+)\.burst\(', l)
        if m2:
            var = m2.group(1)
            if var not in declared and not var.startswith("rdi") and len(var) > 2:
                return BugResult(
                    bug_line=i + 1,
                    reason=f"Variable '{var}' used in burst() without initialization — should use the initialized port variable",
                    confidence="medium",
                )


# ─────────────────────────────────────────────────────────────────────────────
#  Rule registry
# ─────────────────────────────────────────────────────────────────────────────

RULES = [
    rule_rdi_end_before_begin,
    rule_veceditmode_outside_begin,
    rule_veceditmode_wrong_enum,
    rule_wrong_vforce_unit,
    rule_wrong_iforce_unit,
    rule_iclamp_before_iforce_range,
    rule_iforce_before_vforce,
    rule_wrong_method_name,
    rule_burst_called_twice_same_port,
    rule_end_called_twice,
    rule_burst_upload_wrong_chain,
    rule_samples_exceed_burst_limit,
    rule_write_instead_of_writeburst,
    rule_duplicate_method_in_chain,
    rule_uninitialized_port_variable,
]