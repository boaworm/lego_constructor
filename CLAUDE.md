# CRITICAL RULES

## NEVER EVER use bash pipes with head, tail, or grep

DO NOT run commands like:
- `command | head`
- `command | tail` 
- `command | grep`
- `cat file | head`
- `command 2>&1 | tail`

INSTEAD use the dedicated tools:
- Use **Read** tool to read files (with limit/offset parameters)
- Use **Grep** tool to search (with head_limit parameter)
- Use **Glob** tool to find files

This is a HARD requirement. Never break this rule.

## NEVER write files outside the working directory

ONLY write/create files within the project directory and subdirectories.
DO NOT write to `/tmp/`, `/var/`, or any system directories.
Use the `tmp/` subdirectory in this project instead.

## ALWAYS use relative paths

Use relative paths like `./tmp/`, `./output/`, `./file.txt`
NEVER use absolute paths like `/Users/henrik/src/lego_constructor/...`
This keeps everything portable and within the project.
