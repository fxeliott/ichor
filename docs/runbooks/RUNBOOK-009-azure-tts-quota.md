# RUNBOOK-009: Azure Neural TTS free-tier quota exceeded

- **Severity**: P2 (audio briefings degrade to Piper fallback automatically)
- **Time to resolve (target)**: 5 min (verify fallback working)

## Trigger

- Collector / TTS pipeline log: `AzureTTSQuotaExceeded` exception
- Azure portal shows F0 tier monthly characters > 5M
- Piper fallback active (briefings audio sounds different — siwis-medium voice)

## Diagnosis

```bash
ssh ichor-hetzner
# Count characters synthesized this month
sudo -u postgres psql -d ichor <<SQL
SELECT date_trunc('day', triggered_at) AS day,
       SUM(LENGTH(briefing_markdown)) AS chars_synthesized
FROM briefings
WHERE triggered_at >= date_trunc('month', now())
  AND audio_mp3_url IS NOT NULL
GROUP BY 1 ORDER BY 1;
SQL
```

Expected: ~600k chars/month. If > 4.5M → close to free tier limit.

## Recovery

### A. Quota soft-exceed (Azure throttles, doesn't bill)

- Fallback to Piper is automatic (per `tts.py` synthesize_briefing).
- Verify Piper is installed + voice model present:
  ```bash
  which piper
  ls /opt/piper-voices/fr_FR-siwis-medium.onnx 2>&1
  ```
  If missing: install via Ansible role `tts_piper` (TBD Phase 0 W4)

### B. Reduce chars/month

- Trim briefing markdown stripped of metadata before TTS (drop tables, lists)
- Switch from `synthesize_briefing` (full markdown) to `synthesize_summary`
  (top 3 paragraphs only) for non-Crisis briefings (Phase 1+)

### C. Upgrade if usage growth is sustained

- Azure F0 (free) → S0 (standard) starts at $4 per 1M chars Neural
- For 8M chars/month: ~$30/month — still flat, predictable
- Update `infra/secrets/azure-tts.env` + create new resource at S0 tier

## Post-incident

- Add monthly char counter to Grafana dashboard
- Consider precomputing audio for briefings with low new content vs prior
  (deduplication via diff)
