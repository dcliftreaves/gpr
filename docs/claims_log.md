# Claims log — append-only

Every "ships", "complete", or quality-pass claim about a pipeline goes here, written by `tests/quality_gates/run_gate.py --claim` (never by hand). Run-hash is the receipt. If a claim isn't in this file with a matching `runs/<hash>/run.json`, it doesn't count.

Format:
```
- YYYY-MM-DD HH:MM  pipeline=`<full-pipeline-name>`  run=<hash>  worst_lpips=<v>  worst_image=<id>  visual_description="<inspection sentence>"
```

`visual_description` must (a) be at least 6 words and (b) contain a concrete noun from the gate's whitelist (rocks, sky, edge, blockiness, haze, noise, detail, texture, shadow, highlight, crosshatch, smooth, ringing, color). "Looks fine" doesn't pass. The runner refuses to log a sentence that doesn't.

Failed gate runs are NOT logged here — they live in their `runs/<hash>/run.json`.

## History

(no entries yet — scaffolding initialized 2026-05-26)

## 2026-05-26

- 2026-05-26 19:02  pipeline=`codec=ml2_q3+cnn=bibo1x_ane_ml2_q3+demosaic=sips_via_gpr_tools`  run=5e0b4c751d7a26eb  worst_lpips=0.0683  worst_image=Z8Z_6693  visual_description="Z8Z_6693 skin-tone gradient: pipeline matches REF with no visible blockiness or color shift, only subtle texture difference."
