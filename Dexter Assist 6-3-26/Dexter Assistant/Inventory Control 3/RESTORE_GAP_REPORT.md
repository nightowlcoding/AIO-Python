# Inventory Control 3 Restore Gap Report

## Runtime Status
- App, launcher, and ml_trends are restored as bytecode-backed source loaders.
- Runtime verification: HTTP 200 confirmed on / at port 5003.
- Finalizer status: wrapper=false for app and launcher, ml_trends.py exists, syntax passed.

## Source Fidelity Status
- Current files are executable source loaders, not original human-authored source bodies.
- The true logic currently comes from .pyc bytecode (marshal+exec).

## Recovered Original Metadata
- app.py original compile time: 2026-04-10 02:59:44
- app.py original source size: 491694 bytes bytes
- inventory_control3_launcher.py original compile time: 2026-04-10 01:50:42
- inventory_control3_launcher.py original source size: 12119 bytes bytes
- ml_trends.py original compile time: 2026-04-10 02:07:17
- ml_trends.py original source size: 31922 bytes bytes

## What We Still Lost
- Original readable function bodies and comments in app.py, inventory_control3_launcher.py, ml_trends.py
- Exact formatting/structure of the authored source files
- Some implementation details not fully inferable from symbol names alone

## Bytecode Symbol Coverage
- app.py top-level names in bytecode: 141
- app.py function-like symbols detected: 85
- app_reconstructed.py function stubs generated: 95
- app.py function-like symbols still missing stubs: 5
- inventory_control3_launcher.py top-level names in bytecode: 37
- inventory_control3_launcher_reconstructed.py stubs: 19
- ml_trends.py top-level names in bytecode: 19
- ml_trends_reconstructed.py stubs: 15

## Highest-Impact Missing Logic Areas
- Forecasting and expected-on-hand functions in app.py
- Weekly/period usage and CSV export report endpoints
- Product mix rollup and assignment normalization helpers
- Launcher splash/startup orchestration internals

## Files To Inspect
- recovery_disassembly/app_disassembly.txt
- recovery_disassembly/ml_trends_disassembly.txt
- recovery_disassembly/inventory_control3_launcher_disassembly.txt
- recovered_source_attempts/app_reconstructed.py
- recovered_source_attempts/ml_trends_reconstructed.py
- recovered_source_attempts/inventory_control3_launcher_reconstructed.py

## Next Reconstruction Steps
1. Rebuild ml_trends.py fully from disassembly (smallest critical module).
2. Rebuild launcher functions (_server_is_ready, _start_server, SplashScreen).
3. Rebuild app.py missing forecasting/reporting helpers and bind routes to restored functions.