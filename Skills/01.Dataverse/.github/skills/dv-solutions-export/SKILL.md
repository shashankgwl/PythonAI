---
name: dv-solutions-export
description: Export one or more Microsoft Dataverse solutions to a user-specified zip file path using PAC CLI. The skill validates PAC auth, shows the active environment, asks for explicit confirmation, and only then performs solution export.
argument-hint: "[solution name(s)] [output zip path(s)] [managed or unmanaged]"
---

# Dataverse Solution Export Skill

Use this skill when the user wants to export one or more Dataverse solutions from the currently selected PAC CLI environment to one or more zip file paths.

This skill is **export only**.
- Do **not** import solutions.
- If the user asks to import a solution, stop and explain that this skill only exports solutions.
- If import automation is needed, that should be handled by a separate import skill.

## Important behavioral rules
- Do not invent PAC CLI commands or parameters.
- Use only documented PAC auth, PAC env, and PAC solution commands.
- Always validate PAC authentication before any environment-specific action.
- Always show the active PAC profile and the active Dataverse environment before exporting.
- Always ask for explicit user confirmation before exporting from the selected environment.
- Never assume the current environment is correct.
- Never silently switch to another environment if export fails.
- Never chain environment selection and export into a single command without first re-validating the selected environment.
- Never use `pac auth clear --index` because `pac auth clear` clears all authentication profiles and is not an indexed delete operation.
- If re-authentication is needed, prefer creating a new auth profile with `pac auth create` and then explicitly selecting it.
- If the current authentication appears invalid or stale, stop and ask the user whether to create a new profile or manually troubleshoot the profile.
- Always verify that the output path includes a zip file name, not just a folder.
- Never overwrite an existing export file unless the user explicitly approves it.
- If the requested solution name is ambiguous or not found, list available solutions and ask the user to choose.

## Supported capabilities
- Validate PAC CLI availability
- Validate PAC authentication
- Show the active auth profile
- Show the active Dataverse environment
- List solutions in the selected environment
- Export one or more solutions as managed or unmanaged packages
- Write exported zip files to user-specified paths

## Required inputs to collect
Before exporting, gather these inputs if they are not already provided:
- solution name or a list of solution names
- output zip path for each solution
- whether to export as managed or unmanaged
- confirmation that the selected environment is the intended source environment

## Workflow

### Step 1: Validate prerequisites
Check that PAC CLI is installed and available in the current shell.

If PAC CLI is missing:
- stop
- tell the user to install or enable PAC CLI first

### Step 2: Validate PAC authentication
Run:
- `pac auth list`

If there are no auth profiles:
- stop
- tell the user that Power Platform CLI authentication is required
- instruct the user to authenticate using one of the documented flows, for example:
  - `pac auth create --environment "<environment-name>"`
  - or `pac auth create --url "https://<org>.crm.dynamics.com/"`
- do not continue until authentication exists

### Step 3: Show active auth profile and environment
Run:
- `pac auth who`
- `pac env who`

Use these commands to show:
- the active PAC auth profile
- the connected Dataverse environment URL/name
- the signed-in user

### Step 4: Confirm source environment
Always tell the user which environment is currently selected.

Use wording like:
- "The active PAC profile is connected to <environment>."
- "Do you want me to export from this environment?"

Wait for explicit user confirmation before continuing.

If the user says the environment is wrong:
- stop
- suggest:
  - `pac auth list`
  - `pac auth select`
  - `pac env list`
  - `pac env select`
  - or `pac auth create` to create a new profile
- after the user changes the environment/profile, re-run:
  - `pac auth who`
  - `pac env who`
- ask for confirmation again

### Step 5: Optional solution discovery
If the user does not know the exact solution name, run:
- `pac solution list`

Show the results and ask the user which solution(s) to export.

### Step 6: Validate output path(s)
For each solution export request:
- ensure the output path is a zip file path
- if the path is only a folder, ask the user for the full zip file path
- if the output file already exists, ask whether it should be overwritten

### Step 7: Export the solution
Run exports only after environment confirmation and output path validation.

Use:
- `pac solution export --name "<solution-name>" --path "<full-zip-path>" --managed`

or:
- `pac solution export --name "<solution-name>" --path "<full-zip-path>"`

Use managed export only when the user explicitly requests managed export or clearly indicates a downstream ALM/target-environment scenario.

If exporting multiple solutions:
- export them one by one
- report progress after each export completes

### Step 8: Handle authentication or token failures safely
If export fails because of authentication/token/profile issues:
- do not silently switch to another environment
- do not export from a fallback environment
- explain which environment/profile failed
- ask the user whether they want to:
  1. create a new auth profile for the intended environment
  2. manually switch profiles/environment and retry
  3. stop

If the user chooses to re-authenticate:
- prefer creating a fresh profile with `pac auth create`
- then run:
  - `pac auth list`
  - `pac auth select` if needed
  - `pac auth who`
  - `pac env who`
- ask for confirmation again before retrying export

Do not use `pac auth clear` unless the user explicitly wants to remove **all** auth profiles.
Do not use undocumented index-based clear operations.

### Step 9: Final summary
At the end, summarize:
- the confirmed source environment
- the solution name(s)
- whether the export was managed or unmanaged
- the output zip path(s)
- whether each export succeeded or failed

## Safety / correctness constraints
- Do not claim export success unless the PAC command output confirms success and the expected zip file exists.
- Do not export from any environment that the user did not explicitly confirm.
- Do not automatically fall back to a different environment if the selected one fails.
- Do not attempt import operations in this skill.
- Do not use unsupported PAC auth syntax.
- Do not ask PAC CLI to monitor folders continuously; instead, confirm export success from command output and file existence.

## Prompt examples
### Example 1
"Export the solution 'Custom RAG' as managed to C:\Exports\CustomRAG_managed.zip. First show me the active PAC environment and ask for confirmation."

### Example 2
"List available solutions in the current environment and export MyCoreSolution as unmanaged to D:\ALM\MyCoreSolution.zip."

### Example 3
"I need to export three solutions from my dev environment. First verify PAC auth, show the current environment, and ask me before continuing."

## Output style
When using this skill:
- be explicit about the selected auth profile and environment
- clearly separate these phases:
  - auth validation
  - environment confirmation
  - solution discovery
  - export execution
  - final summary
- show the exact command before running it when the action is sensitive
- stop immediately if authentication or environment context is uncertain
