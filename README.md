# NimbusPay ticket triage

- **Base model:** `Qwen/Qwen2.5-1.5B-Instruct`
- **Loading:** 4-bit NF4 QLoRA is the primary configuration; the controlled comparison also runs FP16 LoRA.
- **Best result:** pending Colab T4 execution; no baseline or fine-tuning score is claimed yet.

The audit and training workflow is in [notebook.ipynb](notebook.ipynb), with reusable training-data repair logic in [audit_clean.py](audit_clean.py). The notebook expects the assignment data in a Drive folder and writes the adapter, metrics, and test predictions there. Do not commit the supplied data or the base model.
