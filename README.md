# [Repository name: to be decided]

A small, runnable demonstration of a procedure for building a dataset from AI personas:
person-level texts become personas, the personas answer the same situation and questions,
the answers are checked and coded by machine, and the result is a dataset that can be analysed.

**Everything produced here comes from fictional, synthetic texts. It has no research meaning and is not a validation of anything.**
The demo shows that the *procedure* runs from start to end and that every text sent to a model is recorded and checked against a frozen template.
It does not test hypotheses and it does not compute any test statistic.

## 1. What is in the repository

| Part | Folder | What it is |
|---|---|---|
| Engine (generic) | `engine/`, `demo.py` | Python code that assembles prompts, sends them, checks and codes the answers, builds the dataset and audits the record. Contains no prompt wording. |
| Template (empty) | `projects/_template/` | Where you put your own texts and attribute table. The `templates/` folder holds the prompt parts (Japanese) and their SHA-256 record. |
| Demo example | `projects/demo_synthetic/` | Fictional texts, a fictional person table, saved answers (`outputs_example/`). The attribute values in the person table were **set by the authors as a design table** when the texts were written; they were not derived from the texts. Two of the six texts (D05, D06) carry no cue to their attributes on purpose. |
| Tests | `tests/` | Replay-mode tests (no GPU, no model). |
| Tools | `tools/` | A pre-push scan (`check_forbidden.py`). |

Real data from the underlying study is **not** in this repository. `projects/_template/` has empty inputs; `projects/demo_synthetic/` has synthetic inputs.

The template files were produced by extracting, from the study's frozen prompt documents, only the text between the separator lines (the parts actually sent to the models); header fields of those documents were not copied.

The prompts that the models receive are in Japanese. English reference translations may be placed in `templates/reference_translation_en/`; they are **not** used for generation and **not** hashed.

## 2. Two ways to run it

1. **Replay mode (no model, seconds).** Uses the answers saved in `projects/demo_synthetic/outputs_example/`.

   ```
   pip install -r requirements.txt
   python demo.py replay
   ```

   It first compares `manifest.json` with the current templates, texts and settings (and stops if anything differs),
   then rebuilds every text, compares the SHA-256 values with the saved ledger, runs the acceptance rules,
   reads the saved coding results, builds the dataset and runs the audit. The rejected answers are printed before the dataset is built.
   The automated tests run this mode.

2. **Your own PC or any OpenAI-compatible endpoint.** Edit `config/demo.yaml` (`generation.base_url`, `generation.model`, optionally `coding.*`), then:

   ```
   python demo.py check
   python demo.py build
   python demo.py generate        # sends the texts; needs a running model server
   python demo.py accept
   python demo.py code
   python demo.py dataset
   python demo.py audit
   ```

   The default model name is `gpt-oss-20b`. The saved example was generated with vLLM 0.30.0 (`--reasoning-parser openai_gptoss`) on one NVIDIA H200 (141 GB) of a research cluster; see `projects/demo_synthetic/RUN_RECORD.md`. Other servers may differ in hardware needs and in how they separate the reasoning text (not verified here).
   Keys are read from the environment variable named in the config; they are never written to a file.

### Two levels of reproducibility

- **Replay mode** reproduces the texts that were sent, their SHA-256 values, the acceptance results and the dataset exactly.
- **Regenerating** with a model follows the same procedure and yields a *new sample*. The outputs need not match the saved ones; with a different endpoint the seed does not guarantee the same output.
  If you edit a text or a template, the saved answers no longer belong to it and must be regenerated (replay stops and says so).

## 3. What the engine does

0. **Inputs**: one text per person (`inputs/texts/<person_id>.md`, anonymised), a person table (`inputs/persons.csv`), the templates, and the settings.
1. **Build** (`build`): header + persona block + scenario + questions + output format, joined by blank lines.
   Before building, every template file is compared with `templates/frozen_hashes.csv` (a mismatch stops the run).
   The SHA-256 of every text to be sent is written to `ledger.jsonl`.
   Conditions: `C3` (own text), `C0` (no persona block), `C3W` (the next person's text, cyclic shift by one), `C3-mixed` (the person's episodes replaced one by one by episodes of other persons with the closest length; no randomness).
2. **Generate** (`generate`): each text is checked against the ledger hash again, then sent as one user message to the configured endpoint.
   Temperature 1.0, top_p 1.0, max_tokens 8192, seed = `seed_base` x 100 + repetition. `reasoning_effort` is a setting of its own and is recorded.
   The text actually sent and the response are saved, one file per job.
3. **Accept** (`accept`): seven format rules (valid JSON; exactly seven keys; q1 three distinct symbols; q2 category in range; q3 one of four options; q5 a permutation of five names; three non-empty free texts).
   Failed jobs are **not** regenerated; they are listed in `rejects.csv`.
4. **Code** (`code`): the three free-text answers are classified or rated with a separate prompt per variable. The coder receives only the sentence(s) to be coded, never the person, condition, model or scenario. The coding endpoint can be set separately from the generation endpoint; by default it is the same model (a simplification).
5. **Dataset** (`dataset`): `dataset_A.csv` (one row per generation job: `person_id, condition, model, scenario, rep, accepted`, structured answers, coded values) and `dataset_B.csv` (one row per person: the columns of `persons.csv`). Join key: `person_id`. `C0` jobs have an empty `person_id`.
6. **Audit** (`audit`): ledger, sent files and output records are compared (counts and number of matching hashes are printed), and the texts are re-assembled from the templates as an independent check.

Values in the output (for example the choice of option) stay in Japanese. A draft translation table is in section 6.

## 4. Correspondence with the underlying study (draft)

| Demo step | Study step | What is simplified |
|---|---|---|
| Build, hash check | Machine assembly from frozen texts, pre-send check, ledger | Same design (ported) |
| Generate | Open-weight models on a research cluster, thousands of jobs | One small model, tens of jobs; `reasoning_effort` is a new degree of freedom |
| Accept | Seven rules; failures recorded only | Same design |
| Code | A model from a different family, four variables, sentence only | Default: same model as generation (can be separated); the same four variables |
| Dataset | A larger dataset built by a separate script | Two minimal tables |
| Analysis | Mixed models, after human checking | **Not included** |
| Long-term-orientation measure | Extraction, pairwise comparison, Bradley-Terry | **Not included in v1** |

The SHA-256 values in `templates/frozen_hashes.csv` are hashes of the files in this repository. They are **not** the values of the study's own freeze record and will not match it.
The codebook of the study is not included; it is to be added separately.
Texts here are about 3,000 to 5,000 characters; the study's texts are much longer, so run time and model behaviour differ.

## 5. Using your own data

See `projects/_template/README.md`. In short: copy `projects/_template/` to `projects/<your_project>/`, put anonymised texts in `inputs/texts/`, fill `inputs/persons.csv`, point `project:` in `config/demo.yaml` (or use `--project`) to your folder, and run `python demo.py check`.
What can be replaced: texts, attribute columns, scenario/question/output-format files, the choice of conditions, repetitions, endpoints and parameters.
What stays fixed in this version: the order of assembly, the hash record and check, the structure of the seven rules (only their value sets are configurable), and the form of the audit.
If you change a template file, regenerate `frozen_hashes.csv` deliberately; the generation parameters in the config must equal `generation_params.yaml`.

## 6. Draft translation of the output values (Japanese stays in the files)

| Japanese | English (draft) |
|---|---|
| 撤退 / 縮小 / 継続投資 / 提携 | withdraw / scale down / continue investing / partner |
| 株主 / 従業員 / 顧客 / 取引先 / 地域社会 | shareholders / employees / customers / business partners / local community |
| 財務収益 / 市場競争 / 技術 / 組織ステークホルダー / 複数拮抗 | finance and profitability / market and competition / technology / organisation and stakeholders / several in balance |
| 危機対処 / 技術・開発 / 海外 / 創業・立ち上げ / 人・組織 / その他 | crisis response / technology and development / overseas / founding and launch / people and organisation / other |

## 7. Limits and what has not been checked

- The saved example (`outputs_example/`) comes from one real run (vLLM + gpt-oss-20b on one GPU; `projects/demo_synthetic/RUN_RECORD.md`). The automated tests still use a dummy client and small fixtures, not a live model.
- Whether other endpoints keep the reasoning text out of the answer is not checked. In the saved run the reasoning text was returned in a separate field and no answer contained it.
- 2 of the 144 answers in the saved run failed acceptance rule 1 (not valid JSON: a Japanese closing quote `」` where `"` was expected). They are kept in `rejects.csv` and excluded from the coding and from the accepted rows of dataset A, as the procedure prescribes.
- The default coder is the generating model (a simplification).
- Synthetic texts cannot show that findings from real data would be reproduced.

## 8. License

Code: Apache-2.0 (`LICENSE`). Documents, templates, scenarios, questions and synthetic texts: CC BY 4.0 (`docs/LICENSE-docs`). Copyright holder: "The authors" (`NOTICE`), anonymous during Stage 1 review; to be updated at Stage 3.
