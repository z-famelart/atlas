---
name: feature
description: Implement a feature from its spec file end-to-end
---
Given a spec file path in $ARGUMENTS:
1. READ the spec file directly. Do NOT call MCP search/workflow tools.
2. Restate the acceptance criteria as a checklist.
3. Implement: no monolithic files, ORM not hand-written SQL, real JSON schemas.
4. If CLI-facing: add flags AND update --help text.
5. Remove every debug print/console.log.
6. Run the full test suite and the linter; paste raw output.
7. Only then commit with a message referencing the spec ID.
