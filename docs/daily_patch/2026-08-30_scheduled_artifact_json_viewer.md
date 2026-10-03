# Scheduled Artifact Viewer

## Purpose

Replace path-copy-only scheduled intelligence evidence with direct, read-only
JSON and Markdown inspection in the authenticated operator UI.

## Scope

- Preopen briefing
- Memory delivery receipt
- Strategy memory source
- Strategist canonical source
- Closeout JSON artifacts already listed by the scheduled intelligence card

## Safety Boundary

- Only artifacts listed by the current scheduled intelligence projection are
  readable.
- Only UTF-8 JSON and Markdown below the configured report-size limit are accepted.
- Absolute paths, source-root traversal and unlisted report files return no
  content.
- The API has no write method and the report mount remains read-only.
- Trading Runtime, scheduler, LLM, strategy and execution behavior are unchanged.

## Verification

- API runtime-status tests: 10 passed.
- Web tests: 14 passed.
- API and Web Docker production builds completed.
- Trackable-file secret scan found no Cloudflare Tunnel token.
