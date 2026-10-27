# persona-pipeline-demo

A small, runnable public demo of a procedure for building a dataset from AI personas:
person-level texts become AI personas, the AI personas answer the same scenarios and questions,
the responses are format-checked and classified by machine, and the result is a dataset that can be analyzed.

**Everything produced here comes from fictional autobiographies. It has no research meaning and is not a validation of anything.**
The public demo shows that the *procedure* runs from start to end and that every text sent to a model is recorded and checked against a fixed template.
It does not test hypotheses and it does not compute any test statistic.

## 1. What is in the public repository

| Part | Folder | What it is |
|---|---|---|
| Engine (generic) | `engine/`, `demo.py` | Python code that assembles prompts, sends them, runs the format check and the classification, builds the dataset and audits the record. Contains no template wording. |
| Project template (empty inputs) | `projects/_template/` | Where you put your own texts and person table. The `templates/` folder holds the templates (Japanese) and their SHA-256 record. |
| Public demo example | `projects/demo_synthetic/` | Fictional autobiographies, a fictional person table, saved responses (`outputs_example/`). The attribute values in the person table were **set by the authors as a design table** when the texts were written; they were not derived from the texts. Two of the six texts (D05, D06) carry no cue to their attributes on purpose. |
| Tests | `tests/` | Replay-mode tests (no GPU, no model). |
| Tools | `tools/` | A pre-push scan (`check_forbidden.py`). |

Real data from this study is **not** in this public repository. `projects/_template/` has empty inputs; `projects/demo_synthetic/` has fictional-autobiography inputs.

The template files were produced by extracting, from this study's fixed prompt documents, only the text between the separator lines (the parts actually sent to the models); header fields of those documents were not copied.

The prompts that the models receive are in Japanese. English reference translations may be placed in `templates/reference_translation_en/`; they are **not** used for generation and **not** hashed.

## 2. Two ways to run it

1. **Replay mode (no model, seconds).** Uses the responses saved in `projects/demo_synthetic/outputs_example/`.

   ```
   pip install -r requirements.txt
   python demo.py replay
   ```

   It first compares `manifest.json` with the current templates, texts and settings (and stops if anything differs),
   then rebuilds every text, compares the SHA-256 values with the saved ledger, runs the format check,
   reads the saved classification results, builds the dataset and runs the audit. The rejected responses are printed before the dataset is built.
   The automated tests run this mode on small test fixtures (`tests/fixtures/`).

2. **Generate mode (your own PC or any OpenAI-compatible endpoint).** Edit `config/demo.yaml` (`generation.base_url`, `generation.model`, optionally `coding.*`), then:

   ```
   python demo.py check
   python demo.py build
   python demo.py generate        # sends the texts; needs a running model server
   python demo.py accept
   python demo.py code
   python demo.py dataset
   python demo.py audit
   ```

   Optionally, `python demo.py snapshot` copies the finished run to `outputs_example/` and writes `manifest.json`, so that `replay` can use it. It deletes the existing `outputs_example/` first.

   The default model name is `gpt-oss-20b`. The saved example was generated with vLLM 0.30.0 (`--reasoning-parser openai_gptoss`) on one NVIDIA H200 (141 GB) of a research cluster; see `projects/demo_synthetic/RUN_RECORD.md`. Other servers may differ in hardware needs and in how they separate the reasoning text (not verified here).
   Keys are read from the environment variable named in the config; they are never written to a file.

### Two levels of reproducibility

- **Replay mode** reproduces the texts that were sent, their SHA-256 values, the format-check results and the dataset exactly.
- **Generate mode** follows the same procedure with a model and yields a *new sample*. The outputs need not match the saved ones; with a different endpoint the seed does not guarantee the same output.
  If you edit a text or a template, the saved responses no longer belong to it and must be regenerated (replay stops and says so).

## 3. What the engine does

0. **Inputs**: one text per person (`inputs/texts/<person_id>.md`, anonymized), a person table (`inputs/persons.csv`), the templates, and the settings.
1. **Build** (`build`): header + persona block + scenario + questions + output format, joined by blank lines.
   Before building, every template file is compared with `templates/frozen_hashes.csv` (a mismatch stops the run).
   The SHA-256 of every text to be sent is written to `ledger.jsonl`.
   Conditions: `C3` (own autobiography), `C0` (no autobiography), `C3W` (another executive's autobiography, cyclic shift by one), `C3-mixed` (mixed autobiography: the person's episodes replaced one by one by episodes of other executives with the closest length; no randomness).
2. **Generate** (`generate`): each text is checked against the ledger hash again, then sent as one user message to the configured endpoint.
   Temperature 1.0, top_p 1.0, max_tokens 8192, seed = `seed_base` x 100 + repetition. `reasoning_effort` is a setting of its own and is recorded.
   The text actually sent and the response are saved, one file per job.
3. **Format check** (`accept`): seven format criteria (valid JSON; exactly seven keys; q1 three distinct symbols; q2 category in range; q3 one of four options; q5 a permutation of five names; three non-empty free texts).
   Rejected jobs are **not** regenerated; they are listed in `rejects.csv`.
4. **Classification** (`code`): the three free-text responses are classified with a separate prompt per variable. The classifying model receives only the sentence(s) to be coded, never the person, condition, model or scenario. The classification endpoint can be set separately from the generation endpoint; by default it is the same model (a simplification).
5. **Dataset** (`dataset`): `dataset_A.csv` (one row per generation job: `person_id, condition, model, scenario, rep, accepted`, structured responses, classification values) and `dataset_B.csv` (one row per person: the columns of `persons.csv`). Join key: `person_id`. `C0` jobs have an empty `person_id`.
6. **Audit** (`audit`): ledger, sent files and output records are compared (counts and number of matching hashes are printed), and the texts are re-assembled from the templates as an independent check.

Values in the output (for example the choice of option) stay in Japanese. Free-text answers may come back in English (2 of 144 in the saved run). A translation table is in section 6.

## 4. Correspondence with this study

| Public demo step | Study step | What is simplified |
|---|---|---|
| Build, hash check | Machine assembly from fixed templates, pre-send check, ledger | Same design (ported) |
| Generate | Open-weight models on a research cluster, thousands of jobs | One small model, 144 jobs in the saved run; `reasoning_effort` is a new degree of freedom |
| Format check | Seven format criteria; rejections recorded only | Same design |
| Classification | A model from a different family, four variables, sentence only | Default: same model as generation (can be separated); the same four variables |
| Dataset | A larger dataset built by a separate script | Two minimal tables |
| Analysis | Mixed models, after the human check | **Not included** |
| Long-term orientation measure | Extraction, pairwise comparison, Bradley–Terry | **Not included in v1** |

The SHA-256 values in `templates/frozen_hashes.csv` are hashes of the files in this public repository. They are **not** the values of this study's own record of fixed files and will not match it.
The codebook of this study is not included; it is to be added separately.
Texts here are about 3,000 to 5,000 characters; this study's texts are much longer, so run time and model behavior differ.

## 5. Using your own data

See `projects/_template/README.md`. In short: copy `projects/_template/` to `projects/<your_project>/`, put anonymized texts in `inputs/texts/`, fill `inputs/persons.csv`, point `project:` in `config/demo.yaml` (or use `--project`) to your folder, and run `python demo.py check`.
What can be replaced: texts, attribute columns, scenario/question/output-format files, the choice of conditions, repetitions, endpoints and parameters.
What stays fixed in this version: the order of assembly, the hash record and check, the structure of the seven format criteria (only their value sets are configurable), and the form of the audit.
If you change a template file, regenerate `frozen_hashes.csv` deliberately; the generation parameters in the config must equal `generation_params.yaml`.

## 6. Translation of the output values (Japanese stays in the files)

| Japanese | English |
|---|---|
| 撤退 / 縮小 / 継続投資 / 提携 | exit / downsizing / continued investment / alliance with another firm |
| 株主 / 従業員 / 顧客 / 取引先 / 地域社会 | shareholders / employees / customers / business partners / local community |
| 財務収益 / 市場競争 / 技術 / 組織ステークホルダー / 複数拮抗 | finance and profitability / market and competition / technology / organization and stakeholders / several in balance |
| 危機対処 / 技術・開発 / 海外 / 創業・立ち上げ / 人・組織 / その他 | crisis response / technology and development / overseas / founding and launch / people and organization / other |

## 7. Limits and what has not been checked

- The saved example (`outputs_example/`) comes from one real run (vLLM + gpt-oss-20b on one GPU; `projects/demo_synthetic/RUN_RECORD.md`). The automated tests still use a dummy client and small fixtures, not a live model.
- Whether other endpoints keep the reasoning text out of the response is not checked. In the saved run the reasoning text was returned in a separate field and no response contained it.
- 2 of the 144 responses in the saved run were rejected by format criterion 1 (not valid JSON: a Japanese closing quote `」` where `"` was expected). They are kept in `rejects.csv` and excluded from the classification and from the accepted rows of dataset A, as the procedure prescribes.
- In the saved run, rows with the same sent text and seed often received the same response: 101 of the 144 responses are distinct (the 36 C0 rows have 9 distinct responses; 16 of the 36 C3W rows equal a C3 response). The 144 rows are not independent responses (see `projects/demo_synthetic/RUN_RECORD.md`).
- The default coder is the generating model (a simplification).
- Fictional autobiographies cannot show that findings from real data would be reproduced.

## 8. Status, provenance and how to verify

- **Version.** Tag `v0.1-stage1` is the snapshot that accompanies a Stage 1 research proposal under anonymous review. Author names and a citation will be added at a later stage.
- **Tested on.** Windows 11 (Python 3.12.10): `python -m pytest`, `python demo.py check`, `python demo.py replay` and `python tools/check_forbidden.py`. Ubuntu via GitHub Actions (Python 3.12): `python -m pytest`, `python demo.py check` and `python tools/check_forbidden.py` (the replay tests inside pytest use small test fixtures, not `projects/demo_synthetic/`).
- **Saved run.** `projects/demo_synthetic/RUN_RECORD.md` records the model revision, server version, generation parameters, counts, timing and the two rejected responses.
- **Fictional autobiographies.** The six autobiographies were written for this public demo; `projects/demo_synthetic/WRITING_NOTES.md` (in Japanese) records the writing rules and the checks made (no years, no real names, no real events). They were also compared with the texts of this study (no 12-character overlap) and probed with three commercial models using this study's fixed re-identification prompt (0 of 90 trials named a person of this study under decision rules fixed in advance).
- **Integrity.** `projects/_template/templates/frozen_hashes.csv` and `projects/demo_synthetic/outputs_example/manifest.json` hold SHA-256 values; `python demo.py replay` stops if any template, text or relevant config value differs from the saved run.
- **Not included.** Real autobiographies, real names, the real-data responses, and the analysis code for this study's hypotheses. During review, questions reach the authors through the journal.

## 9. License

Code: Apache-2.0 (`LICENSE`). Documents, templates, scenarios, questions and fictional autobiographies: CC BY 4.0 (`docs/LICENSE-docs`). Copyright holder: "The authors" (`NOTICE`), anonymous during Stage 1 review; to be updated at Stage 3.
