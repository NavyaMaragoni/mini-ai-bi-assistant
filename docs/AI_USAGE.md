# AI Usage, Problems and Improvements

## AI tools used
- Claude (chat, across two sessions): planning, step-by-step guidance, and code for the loader, analytics, interpreter, AI layer, UI, tests, README and GitHub push help.
- Gemini API (optional, at runtime): routes questions to intents only.

## How I used AI
I worked in small steps (setup, data profiling, loader, analytics, API, AI layer, UI, tests, docs).
After each step I ran the commands myself and checked the output before moving on. The design
choice that the LLM only routes and never writes SQL came from the requirement to avoid
destructive or incorrect answers.

## Problems encountered and how I debugged them
| Problem | How it was found and fixed |
|---|---|
| `python` not found on Ubuntu | Used `python3` and a virtual environment |
| Pasted heredocs garbled in the terminal | Created long files with nano instead |
| `profile.py` shadows a standard-library module | Renamed to `profile_data.py` |
| "Which region had the lowest sales?" would have returned the highest region | Found while testing refusals; added deterministic pre-checks that refuse "lowest" and similar |
| `DROP TABLE sales;` returned total revenue because the word "sales" matched | Added an SQL-like input guard; also removed "drop" from the comparison keywords |
| Port 8000 already in use, old server running stale code | Stopped the old process with `pkill`, restarted |
| New terminal had no active venv | Re-activated it with `source venv/bin/activate` |
| A placeholder API key was saved to `.env` | Deleted the file; the key is git-ignored |
| Rows with bad data (qty 0, missing price, returned order) | Profiled the CSV first, documented a rule for each |

## What works / what does not
Works: all five question types, validation, fallback, UI, 17 automated tests, and the live Gemini call.
Not supported: filtering by a specific
product, region or single month; "lowest" and "average" questions.

## With another day I would
- Add an optional text-to-SQL mode with a SELECT-only validator.
- Support filters (region, product, month) and "lowest/average" questions.
- Use an isolated test database and add LLM-path and error-path tests.
- Add authentication, caching and logging of refused questions.
