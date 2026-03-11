# Failure Fixture Note

This directory documents the expected low-text PDF failure mode.

- If `pypdf` extraction returns too little text, the script should exit with code `3`.
- The user-facing message should be `请补充摘要或正文内容，以便继续拆解。`
- A binary PDF fixture is not committed here to keep the repository small and deterministic.
