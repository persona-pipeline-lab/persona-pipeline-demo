# Public demo example (fictional autobiographies)

The fictional autobiographies, the person table and one saved run (`outputs_example/`, see `RUN_RECORD.md`) are in place.

- `inputs/texts/D01.md` ... `D06.md`: fictional autobiographies (no real person or company). Each has a one-paragraph English summary in `inputs/texts_summary_en.md`.
- `inputs/persons.csv`: six fictional people with invented attributes (`crisis`, `tech_background`, and the basis columns). The basis text of each row is fictional and names no real publication. The values were set by the authors as a design table before the texts were written; they were **not** derived from the texts. D01 to D04 carry cues to their attributes in the text; D05 and D06 carry none (the table and the text are independent for these two, as can happen with real external records).
- `WRITING_NOTES.md`: how the six texts were written and checked (character counts, the rules followed, what was not checked).
- `config.yaml`: uses the shared templates in `../_template/templates/`.
- `outputs_example/`: saved responses, ledger, format-check tables, classification results, datasets and `manifest.json` (used by `python demo.py replay`). Saved from the run described in `RUN_RECORD.md` with `python demo.py snapshot`.

Every number or table produced from this folder is a product of the construction of the fictional autobiographies. It carries no research meaning.
