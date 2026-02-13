# 9. Security / Compliance

## 9.1 Secret Management
- .env must be gitignored
- never print secrets to CI logs
- enforce local file permissions by policy

## 9.2 Access Control / Roles
- operator: can change approval/mode/guards
- developer: primarily tests in mock environment
- automation: least privilege

## 9.3 Safe Ops Policies
- enable real execution only during a change window
- require two-person review for real enabling (recommended)
- block large orders by default and require manual approval
