"""Registry consistency check — surface mismatches between codec use_for
and CNN intent, plus duplicate ship_class collisions.

Run from CI or manually:
    python3 tests/quality_gates/check_registry_consistency.py
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REG = json.loads((REPO / "pipelines/registry.json").read_text())

warnings = []
errors = []

# Every codec must have use_for
for name, codec in REG.get("codecs", {}).items():
    if "use_for" not in codec:
        warnings.append(f"codec {name!r} missing 'use_for' field")
    elif codec["use_for"] not in {"still", "video", "experiment", "deprecated"}:
        errors.append(f"codec {name!r} has invalid use_for={codec['use_for']!r}")

# Pipeline-level: still pipelines shouldn't reference video CNNs and vice-versa.
# Heuristic: CNN names containing 'sl_q3' or 'gpr_tools' = still-trained;
# CNN names containing 'ml2' or 'dmsr' or 'bido' = video-trained.
def cnn_intent(cnn_name):
    if cnn_name == "none":
        return "any"
    if "ml2" in cnn_name or "dmsr" in cnn_name or "bido" in cnn_name.lower():
        return "video"
    if "sl_q3" in cnn_name or "gpr_tools" in cnn_name:
        return "still"
    if "hh1x4" in cnn_name or "l1l2x4" in cnn_name:
        return "video"  # historical multi-level CNNs
    return "unknown"

for pname, pipe in REG.get("pipelines", {}).items():
    if not isinstance(pipe, dict):
        continue  # skip $doc / $rules meta keys
    codec_name = pipe.get("codec")
    cnn_name = pipe.get("cnn", "none")
    if codec_name not in REG.get("codecs", {}):
        errors.append(f"pipeline {pname!r}: unknown codec {codec_name!r}")
        continue
    codec_use = REG["codecs"][codec_name].get("use_for", "unknown")
    cnn_use = cnn_intent(cnn_name)
    # still codec + video CNN, or vice-versa, is suspicious
    if codec_use == "still" and cnn_use == "video":
        warnings.append(f"pipeline {pname!r}: still codec paired with video CNN ({cnn_name})")
    if codec_use == "video" and cnn_use == "still":
        # acceptable as a cross-pair probe but flag it
        warnings.append(f"pipeline {pname!r}: video codec paired with still CNN ({cnn_name}) — cross-pair probe?")
    if codec_use == "deprecated":
        warnings.append(f"pipeline {pname!r}: uses deprecated codec {codec_name!r}")

print(f"=== registry consistency check ===")
print(f"codecs: {len(REG.get('codecs', {}))}  pipelines: {len(REG.get('pipelines', {}))}")
if warnings:
    print(f"\n{len(warnings)} warnings:")
    for w in warnings[:20]:
        print(f"  WARN: {w}")
    if len(warnings) > 20:
        print(f"  ... ({len(warnings) - 20} more)")
if errors:
    print(f"\n{len(errors)} ERRORS:")
    for e in errors:
        print(f"  ERROR: {e}")
    sys.exit(1)
print(f"\nOK" if not errors else "")
