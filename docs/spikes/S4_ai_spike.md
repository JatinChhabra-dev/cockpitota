# Spike S4 — AI Defect Triage & Analysis

## Question
Can a multimodal LLM (Claude / Gemini) accurately analyze a cockpit test failure bundle (screenshot + logcat window + UI hierarchy dump) and identify the root cause of the planted regression?

## Exit Criteria
- [ ] Construct canned failure bundle for the planted regression:
  - Scenario: SC-03 (Reverse with menu open)
  - Variant: VAR-B (Portrait)
  - Logcat snippet showing WindowManager / Focus logs
  - UI hierarchy XML showing modal charging menu in foreground
  - Cockpit screenshot showing rear-view camera suppressed
- [ ] Implement provider-agnostic AI adapter (`ai/adapter.py`)
- [ ] Define prompt template for Failure Triage (`ai/prompts/triage_v1.txt`)
- [ ] Run 5 consecutive evaluations: model must achieve 5/5 correct identification naming `APP-1 modal focus / z-order window obstruction`
- [ ] Record prompt, input hash, output, and latency in `AIRecord` format

## Status: IN PROGRESS
