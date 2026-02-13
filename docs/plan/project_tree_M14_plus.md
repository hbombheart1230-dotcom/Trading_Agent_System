# 🚀 Trading Agent System
## Project Structure & Architecture (M14+)

Generated at: 2026-02-12T04:45:05.890894Z

---

# 1️⃣ System Overview

This system evolved into a Skill-Oriented Agent Architecture.

Flow:

NL → ToolFacade → Supervisor → CompositeSkillRunner → RuleEngine → API Catalog → Executor → Kiwoom

---

# 2️⃣ Environment

KIWOOM_MODE=mock | real  
EXECUTION_ENABLED=true | false  
APPROVAL_MODE=manual | auto  

---

# 3️⃣ Directory Structure

libs/
  tools/
  supervisor/
  skills/
  execution/
  kiwoom/
  runtime/
  risk/
  storage/
  agent/

data/specs/
  api_catalog.jsonl
  default_rules.json

scripts/
  build_api_catalog.py
  build_default_rules.py

---

# 4️⃣ Skills

market.quote  
order.place  
order.status  

---

# 5️⃣ Supervisor

Two-phase execution with intent storage.

---

# 6️⃣ Status

M14 Complete.
