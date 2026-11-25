# Aurelia Motors Cockpit Release Notes — v1.1

**Release ID:** `v1.1` (Baseline: `v1.0`)  
**Target Platform:** Android Automotive OS (AAOS API 33 / 34)  
**Affected Packages:** `com.aurelia.ev` (`1.1.0`), `com.aurelia.rearview` (`1.0.0`)

## Declared Changes
1. **CHG-101 — New Charging-Schedule Card (`APP-1`)**: Added an updated off-peak charging schedule card (`card_charging_schedule_v2`) with one-tap access to the charging schedule configuration modal.
2. **CHG-102 — Revised Navigation Shortcut (`APP-1`)**: Updated the quick-action navigation shortcut (`btn_nav_shortcut_v2`) to route directly to the nearest DC fast charger.
3. **CHG-103 — Updated German (`de-DE`) Strings (`APP-1`, `VAR-C`)**: Refined German terminology for charging schedule and cabin climate labels.

## Safety & Homologation Note
No changes are declared for `APP-2` (Rear-view Stand-in) or `GEAR_SELECTION` reverse-overlay timing. Rear-view display MUST remain visible on top within 500 ms across all cockpit variants (`VAR-A`, `VAR-B`, `VAR-C`).
