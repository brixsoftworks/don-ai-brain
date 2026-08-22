# SECURITY ACTION REQUIRED

## Findings (Phase 0 audit, 2026-08-22)

| Secret | Location | Status |
|---|---|---|
| Gemini API key (`AQ.Ab8RN6…`) | Hardcoded fallback in **tracked** `client/web_agent.py:20` and `client/voice_daemon.py:56`; entered git history at commit `aedd242` | LIVE IN HISTORY |
| OpenRouter API key (`sk-or-v1-…`) | Untracked scratch/test scripts (`scratch/test_lc_playwright.py`, `scratch/test_tool_calling.py`, `scratch/test_lc_agent.py`, `test_latency.py`) | Working-tree only |
| Gemini API key (same value as above) | Untracked `scratch/test_gemini_openai.py`, `scratch/check_models.py`, `test_llm.py` | Working-tree only |

## ACTION REQUIRED
1. **Rotate BOTH keys**: Gemini at https://aistudio.google.com/apikey,
   OpenRouter at https://openrouter.ai/settings/keys — the Gemini key is in
   remote git history (github.com/brixsoftworks/don-ai-brain).
2. Recommended follow-up (needs human confirmation): rewrite history to drop
   the key from `client/web_agent.py` / `client/voice_daemon.py` blobs
   (`git filter-repo --replace-text`). Force-push afterwards.

## Fixed automatically (this audit)
- Removed hardcoded key fallbacks from both tracked client files → they now
  require `os.environ["GEMINI_API_KEY"]`.
- Scrubbed keys from all 7 untracked scratch/test files → env-var reads.
- Real values moved to untracked `.env.local` (local runs keep working).
- `.env.example` placeholders added; `.gitignore` already covers `.env*`.
- NOTE: repo had pre-existing uncommitted WIP (worker.py, voice.yaml, core/
  deletions) BEFORE this audit — left untouched. Commit only the security
  scrub selectively, or review the whole tree yourself.
