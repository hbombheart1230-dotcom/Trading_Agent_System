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
# - AUTO_APPROVE=auto|manual : treated as APPROVAL_MODE (compat)
# - AUTO_APPROVE=true        : treated as APPROVAL_MODE=auto (legacy boolean)
#   (운영/문서에서는 APPROVAL_MODE 사용 권장)
