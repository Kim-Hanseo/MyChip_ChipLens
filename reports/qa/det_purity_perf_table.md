| 확인 항목 | 기대 | 실제 | 결과 |
|---|---|---|---|
| same process: run_analysis(req) x2 -> model_dump_json bytes | identical | True (sha256 945b3c9ca8a1b9b8, 52,211 B) | PASS |
| same process: request rebuilt from file bytes -> bytes | identical | True | PASS |
| same process: error file + 100 MHz x2 | identical | True | PASS |
| report JSON has no timestamp / uuid-like fields (D10) | none | none found | PASS |
| 2 fresh interpreters: model_dump_json bytes | identical | True (sha256 945b3c9ca8a1b9b8 / 945b3c9ca8a1b9b8) | PASS |
| fresh interpreter bytes == in-process bytes | identical | True | PASS |
| source scan core/**/*.py for streamlit/plotly imports | 0 hits | 0 hits | PASS |
| core third-party imports ⊂ numpy/scipy/pandas/openpyxl/pydantic (D1) | nothing else | third-party used: ['core', 'numpy', 'openpyxl', 'pandas', 'pydantic', 'scipy'], extra: none | PASS |
| fresh interpreter: import core, core.adapters, core.analyzers, core.judge, core.pipeline (+models, preprocess) -> streamlit/plotly in sys.modules | none | none | PASS |
| same interpreter after a full run_analysis -> streamlit/plotly in sys.modules | none | none | PASS |
| analyze_all (measured 20k x 4ch) median of 5 | < 1 s target, 3 s limit (contract §3) | 9.5 ms (max 10.6 ms) | PASS |
| run_analysis full demo (20k x 4ch + sim 40k x 3ch + DMM + bits) median of 5 | < 3 s | 32.8 ms (max 38.9 ms) | PASS |
| file bytes -> preview_file -> read_table -> to_waveforms/to_dc_sweep (3 files) median of 5 | info | 409.2 ms | PASS |
| adapters + run_analysis total (upload -> cards data) | < 3 s | 442.0 ms | PASS |
| stress: 80k pts x 4ch (record tiled x4) run_analysis | info (scaling) | 77.7 ms | PASS |
