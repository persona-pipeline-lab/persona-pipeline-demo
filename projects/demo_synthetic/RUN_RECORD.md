# Record of the saved run (`outputs_example/`)

Date of the run: 2026-10-25 (JST). One run, no reruns; nothing was regenerated or hand-edited afterwards.

| Item | Value |
|---|---|
| Hardware | One NVIDIA H200 (141 GB) on a shared GPU node of a research cluster; one job |
| Server | vLLM 0.30.0, OpenAI-compatible API, `--reasoning-parser openai_gptoss`, `--max-model-len 16384` |
| Model | `openai/gpt-oss-20b`, Hugging Face revision `6cee5e81ee83917806bbde320786a8fb61efebee`, served as `gpt-oss-20b` |
| Python on the cluster | 3.12.9 |
| Generation parameters | temperature 1.0, top_p 1.0, max_tokens 8192, seed = 1000 x 100 + rep, reasoning_effort medium (as in `templates/generation_params.yaml`) |
| Classification | same model and endpoint as generation (simplification), 4 blocks |
| Jobs | 144 = 6 texts x 4 conditions x 3 scenarios x 2 reps; 39 unique sent texts (C3 18, C0 3, C3W 18, C3-mixed 18) |
| Generation time | first request 11:00:39 UTC, last request 11:20:22 UTC (about 20 minutes) |
| Format check | PASS 142, FAIL 2 (both criterion 1: not valid JSON, a Japanese closing quote where `"` was expected), MISSING 0 |
| Classification | 568 cells = 142 accepted x 4 blocks; no accepted row without a classification file |
| Audit on the cluster | ledger 144, sent files 144, records 144, match 144, mismatch 0, RESULT = OK |
| Replay on a laptop (Windows, Python 3.12.10) | manifest check OK; rebuilt texts equal to the ledger 144/144; dataset_A.csv and dataset_B.csv identical to the saved ones; RESULT = OK |

Notes.

- The two rejected responses have the same text: job `D06|C3W|tech_transition|2` sends the same prompt as `D01|C3|tech_transition|2` (C3W rotates the texts by one) and both used seed 100002, and the server returned identical output. Identical prompt plus identical seed giving identical output is a property of this server; other servers may not behave so.
- Identical prompt plus identical seed often gave identical output in this run. Of the 144 responses, 101 are distinct: the 36 C0 rows contain only 9 distinct responses (every C0 slot receives the same text), and 16 of the 36 C3W rows are identical to a C3 response (C3W sends the next person's text with the same seeds). The saved rows are therefore not 144 independent responses.
- Two responses (`D04|C3|international|1`, `D03|C3-mixed|tech_transition|2`) gave their free-text answers in English. Both passed the format check, which does not check the language.
- The reasoning text was returned in a separate field (`reasoning_text` in `generated/*.json`) and was not found inside any response.
- `rejects.csv` keeps the two failed rows; they are excluded from classification and from the accepted rows of `dataset_A.csv`, as the procedure prescribes. No response was regenerated.
- The `manifest.json` written by `snapshot` holds the SHA-256 of the 10 template files, `persons.csv`, the 6 texts and the relevant part of the config, so `replay` stops if any of them changes.
