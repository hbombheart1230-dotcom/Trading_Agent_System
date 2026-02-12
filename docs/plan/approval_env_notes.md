# Approval policy
# - APPROVAL_MODE=manual : always require explicit '승인' before execution
# - APPROVAL_MODE=auto   : execute immediately after intent creation ONLY if EXECUTION_ENABLED=true
#
# Safety switch
# - EXECUTION_ENABLED=false : blocks real execution (and auto execution) regardless of approval mode
#
# Server routing
# - KIWOOM_MODE=mock|real
#
# Backward compatibility
# - AUTO_APPROVE=true is treated as APPROVAL_MODE=auto (deprecated; prefer APPROVAL_MODE)
