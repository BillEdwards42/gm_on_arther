# Gemini AI Assistant Instructions

As the AI assistant working in this repository, you must strictly adhere to the following rules at all times:

## 1. Always Start with the Wiki (`ai/wiki/`)
The `ai/wiki/` directory contains the complete and up-to-date documentation of the system's architecture, including the Event Sourced Document CMS, AI Agents, Data Integrator, Grader, and Frontend Integration.
- **MANDATORY**: At the beginning of any new session or feature request, you MUST start by reading the files in `ai/wiki/` to understand the codebase context.
- Always use the information in the wiki to guide your implementations and ensure you align with existing patterns.

## 2. Do Not Execute Blocking Terminal Commands
- **DO NOT** execute hosting commands (like starting development servers, Uvicorn, `docker logs -f`, etc.) or any commands that will block the terminal forever.
- Execution of blocking processes will be handled manually by the user. 

## 3. Do Not Do What Is Not Asked (Avoid Over-engineering)
- Only make changes that are directly requested or clearly necessary. Keep solutions simple, focused, and strictly within the scope of the prompt.
- **DO NOT** add features, refactor surrounding code, or make unsolicited "improvements". 
- **DO NOT** add error handling, validation, or complex abstractions for hypothetical future scenarios. The right amount of complexity is the minimum needed for the current task.
- If you fix a bug, only fix the bug—do not touch surrounding formatting or logic unless it is broken.