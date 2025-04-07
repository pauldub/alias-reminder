# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build/Lint/Test Commands
- No formal build process, this is a Zsh plugin
- Run the Python script directly: `python3 alias_reminder.py --help`
- Debug mode: `ALIAS_REMINDER_DEBUG=true python3 alias_reminder.py ...`
- No formal test suite, test manually in a Zsh shell

## Code Style Guidelines
- Python: Follow PEP 8 style guide
- Use type annotations for all function parameters and return values
- Error handling: Use try/except blocks with specific exception types
- Imports: Standard library first, then third-party, then local imports
- Variable naming: snake_case for variables and functions, UPPER_CASE for constants
- Zsh: Use function names with prefixes (_alias_reminder_*)
- Add DEBUG logging for important operations
- Comments should explain "why" not "what"
- Handle potential file system errors gracefully
- String formatting: Use f-strings in Python
- When adding new features, ensure backward compatibility
