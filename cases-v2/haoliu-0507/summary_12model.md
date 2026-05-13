# ClawSecBench 12-Model Evaluation Results

## Summary

| Model | Attack Success (A) | Explicit Refusal (R) | Benign Success (B) | Runtime Error | Valid/Total |
|-------|-------------------|---------------------|-------------------|--------------|-------------|
| Qwen3.6 Plus | 12/20 | 4 | 15/20 | 2 | 38/40 |
| DeepSeek V4 Pro | 13/20 | 4 | 16/20 | 3 | 37/40 |
| GLM-5 | 5/20 | 4 | 10/20 | 19 | 21/40 |
| Kimi K2.5 | 14/20 | 3 | 17/20 | 0 | 40/40 |
| Qwen3.5-35B-A3B | 13/20 | 1 | 20/20 | 3 | 37/40 |
| Qwen3.5-122B-A10B | 11/20 | 4 | 16/20 | 1 | 39/40 |
| Qwen3.5-397B-A17B | 10/20 | 4 | 18/20 | 0 | 40/40 |
| MiniMax M2.5 | 15/20 | 3 | 19/20 | 0 | 40/40 |
| GPT-5.4 | 12/20 | 6 | 10/20 | 6 | 34/40 |
| Gemini 3.1 Pro | 4/20 | 4 | 17/20 | 5 | 35/40 |
| Claude Opus 4.6 | 5/20 | 13 | 13/20 | 2 | 38/40 |
| Claude Sonnet 4.5 | 2/20 | 14 | 16/20 | 1 | 39/40 |

## Notes

- A = Attack task completed successfully (higher = more vulnerable)
- R = Model explicitly refused the attack task
- B = Benign task completed successfully (higher = better capability)
- 40 cases total: 20 attack + 20 benign
- GLM-5 has high error rate (19/40) due to unstable API
