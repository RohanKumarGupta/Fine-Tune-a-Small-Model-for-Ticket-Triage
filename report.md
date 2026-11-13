# NimbusPay ticket triage — working report

> **Work in progress.** Baselines, training runs, final adapter, test predictions, and error explanations require a Colab T4 run. No model performance numbers are claimed here.

## Data audit

Audited all 1,445 training rows against `SCHEMA.md`; dev and test labels were not used for cleaning. The assistant target strings contain several systematic faults:

- 25 targets are truncated/invalid JSON and are dropped because the missing label text cannot be recovered reliably.
- 70 labels have a corrupted `prio` key and invalid words such as `low` or `medium` instead of the required priority. Priority is recomputed from the ticket and the ordered schema rules.
- 30 transaction dates use `DD/MM/YYYY`; these are normalized to `YYYY-MM-DD`.
- 20 NimbusPay transaction IDs have casing, spaces, or hyphens; these are normalized to `NP` plus 10 digits.
- 65 additional structurally valid labels conflict with the priority rules; four `needs_human` values conflict with the escalation rule. Priority is recalculated from category, annotated transaction amount, and explicit legal-threat wording; human escalation is recalculated from the corrected priority and explicit prior-contact wording.

The reproducible implementation is [audit_clean.py](audit_clean.py). It retained 1,420 rows, fixed 157 rows, dropped 25 rows, and wrote 182 row-level actions to [cleaning_log.csv](cleaning_log.csv). Categories, amounts, dates, and language labels beyond the listed structural/rule checks need a further manual review before submission.

## Baselines and controlled experiments

| Run | Single factor changed from cleaned QLoRA rank-8, 2-epoch run | Dev exact match | Dev mean field accuracy | Peak GPU memory | Training minutes |
|---|---|---:|---:|---:|---:|
| Base, fixed system prompt | No adapter | Pending | Pending | Pending | N/A |
| Base, rules in system prompt | Reference only | Pending | Pending | Pending | N/A |
| Clean QLoRA, rank 8, 2 epochs | Reference run | Pending | Pending | Pending | Pending |
| Raw QLoRA, rank 8, 2 epochs | Raw vs. cleaned data | Pending | Pending | Pending | Pending |
| Clean FP16 LoRA, rank 8, 2 epochs | 16-bit vs. 4-bit | Pending | Pending | Pending | Pending |
| Clean QLoRA, rank 16, 2 epochs | Rank | Pending | Pending | Pending | Pending |
| Clean QLoRA, rank 8, 1 epoch | Epoch count | Pending | Pending | Pending | Pending |
| Clean QLoRA, rank 8, 2 epochs, LR 1e-4 | Lower learning rate to test overfitting (own idea) | Pending | Pending | Pending | Pending |

The notebook measures token-length percentiles from cleaned training rows, masks system/user tokens from loss, asserts no more than 50M trainable parameters, and records the requested run metrics.

Qwen2.5-1.5B is small enough for a free T4 and supports system-role chat formatting. Rank 8 is the lower-cost starting point; alpha is set to twice the rank and dropout to 0.05. Two epochs and a 2e-4 learning rate are the reference settings, with one-epoch and 1e-4 comparisons to check overfitting. Micro-batch 2 with accumulation 4 gives an effective batch of 8; FP16 compute and gradient checkpointing reduce T4 memory use. The context length is computed from the cleaned training data rather than guessed.

## Error analysis and next steps

Pending selection and evaluation of the best run on dev. The notebook prints per-field and per-category results plus at least ten concrete failures; explanations should be written after inspecting those tickets rather than inferred from aggregate metrics. Next: review all targeted schema edge cases, tune only against dev, rerun the selected adapter for reproducibility, and verify all 400 test outputs.

## AI tools

Copilot SDK in VS Code assisted with audit logic and notebook scaffolding. It was not used to produce labels or predictions. The author is responsible for executing the notebook, checking every result, and completing the error explanations.
