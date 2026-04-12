---
name: dv-flowanalyzer
description: >-
  Export or use a Dataverse solution ZIP, extract its contents, identify Power Automate
  flows and related metadata, and answer questions such as: which flows trigger on
  Account, how many flows exist, and which flows use a specific connector like SQL.
  Use this when the user wants to analyze Power Automate / cloud flow metadata from a
  Dataverse solution.
license: Proprietary - for local/internal use
---

# Dataverse Solution Flow Analyzer

## Goal
Help the user analyze Power Automate flows contained in a Dataverse solution.

This skill must:
1. Ask whether the user already has the solution ZIP file.
2. If **yes**, ask for the ZIP file path.
3. If **no**, ask for the **solution name** and, if needed, confirm or ask for the target Dataverse environment/auth profile.
4. Verify the **Power Platform CLI (`pac`)** is available locally.
5. Export the solution ZIP to a temporary workspace.
6. Extract the ZIP contents into the same workspace.
7. Inspect the extracted files to find Power Automate flow definitions and metadata.
8. Answer the user’s questions from the extracted artifacts.

---

## Important operating principles

- Prefer a workspace rooted at **`$env:TEMP\dv-flowanalyzer`** instead of a hard-coded user profile path. This is more portable and avoids embedding the username. On Windows, `$env:TEMP` typically resolves under the user’s local temp directory.
- Create a **unique run folder per analysis** to avoid collisions:
  - Example: `$env:TEMP\dv-flowanalyzer\<sanitized-solution-name>\<yyyyMMdd-HHmmss>`
- Never overwrite an existing ZIP or extracted folder unless the user explicitly asks.
- Prefer **read-only analysis** of the exported solution contents.
- Do **not** modify the user’s Dataverse environment unless the user explicitly requests changes.
- If PAC is installed but there is no active auth profile, explain that export cannot proceed until the user signs in or selects an auth profile.
- If the solution ZIP is already available, skip export and go straight to extraction and analysis.
- If the user only wants counts or quick facts, avoid verbose summaries unless asked.

---

## What to ask the user

### Step 1: Determine whether a ZIP already exists
Ask:
> Do you already have the Dataverse solution ZIP file available locally?

If the user says **yes**:
- Ask for the full ZIP path.
- If the path contains spaces, treat it as a quoted path in commands.

If the user says **no**:
- Ask:
  1. What is the **solution name**?
  2. Which Dataverse environment/auth profile should be used, if not already selected?

If the environment/auth context is unclear, ask one concise follow-up such as:
> I need the Dataverse environment that contains this solution. Do you want me to use the currently selected PAC auth profile, or should I help you choose one?

---

## Preconditions and checks

### Check whether PAC CLI is installed
Use PowerShell:

```powershell
Get-Command pac -ErrorAction SilentlyContinue | Format-List
```

If PAC is not found:
- Stop.
- Tell the user that Power Platform CLI must be installed before solution export can run.
- Ask whether they want installation guidance.

### Check PAC authentication profiles
Use:

```powershell
pac auth list
```

Interpretation guidance:
- If there are no profiles, tell the user they need to sign in first.
- If there are multiple profiles and none is clearly selected for the target environment, ask the user which one to use.
- If a profile is already selected and the user did not specify otherwise, use it.

Optional environment checks if needed:

```powershell
pac env list
```

---

## Workspace layout

Use this structure for each run:

```text
$env:TEMP\dv-flowanalyzer\
  <solution-name>\
    <timestamp>\
      export\
        <solution-name>.zip
      extracted\
      reports\
        manifest.json
        flow-summary.json
```

### Naming rules
- Sanitize the solution name for file-system safety.
- Preserve the original user-provided solution name for PAC export commands.
- Use lowercase and hyphens for generated folder names where practical.

---

## Export procedure

Only run this procedure if the user does **not** already have a ZIP.

### 1. Create the workspace folders
Use PowerShell similar to:

```powershell
$solutionName = "<USER_SOLUTION_NAME>"
$sanitizedName = ($solutionName -replace '[^a-zA-Z0-9._-]', '-')
$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$root = Join-Path $env:TEMP "dv-flowanalyzer"
$runRoot = Join-Path $root (Join-Path $sanitizedName $timestamp)
$exportDir = Join-Path $runRoot "export"
$extractDir = Join-Path $runRoot "extracted"
$reportsDir = Join-Path $runRoot "reports"

New-Item -ItemType Directory -Force -Path $exportDir | Out-Null
New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

$zipPath = Join-Path $exportDir ("$sanitizedName.zip")
```

### 2. Export the solution with PAC
Use:

```powershell
pac solution export --name "<USER_SOLUTION_NAME>" --path "<ZIP_PATH>"
```

Notes:
- Use `--managed` only if the user specifically wants the managed export or your workflow requires it.
- If export is long-running, `--async` can be considered.
- If export fails, capture and summarize the PAC error.

### 3. Confirm the ZIP exists
Check:

```powershell
Test-Path "<ZIP_PATH>"
```

If the file does not exist after PAC reports success, stop and tell the user export did not produce the expected artifact.

---

## Existing ZIP procedure

If the user already has a ZIP file:
1. Validate that the path exists.
2. Copy the ZIP into the run workspace **only if needed**. Prefer analyzing it in place unless a local working copy is useful.
3. Create the extraction and reports folders under the run workspace.
4. Continue to extraction.

Validation example:

```powershell
Test-Path "<USER_ZIP_PATH>"
```

If the ZIP path is invalid, stop and ask the user for the correct file path.

---

## Extraction procedure

The user explicitly wants Python used to extract the ZIP. Use Python standard library `zipfile`.

### Python extraction script pattern
Generate and run Python code equivalent to:

```python
from pathlib import Path
from zipfile import ZipFile

zip_path = Path(r"<ZIP_PATH>")
extract_dir = Path(r"<EXTRACT_DIR>")
extract_dir.mkdir(parents=True, exist_ok=True)

with ZipFile(zip_path, 'r') as zf:
    zf.extractall(extract_dir)

print(f"Extracted: {zip_path} -> {extract_dir}")
```

After extraction:
- Confirm the extraction directory contains files.
- If extraction fails, summarize the exception and stop.

---

## Analysis procedure

After extraction, inspect the solution contents to identify Power Automate / flow artifacts.

### Primary analysis goals
Build enough metadata to answer questions like:
- How many flows are in the solution?
- Which flows trigger on `account`?
- Which flows use the SQL connector?
- Which flows use Dataverse, SharePoint, Outlook, HTTP, or custom connectors?
- Which flows are triggered by row changes in Dataverse?
- Which tables/entities are referenced by triggers or actions?
- Which flows update `account`?
- Which flows have recurrence triggers vs event triggers?
- Which flows contain conditions, loops, scopes, or child-flow patterns?

### File discovery guidance
Search recursively in the extracted folder for:
- JSON files that contain Power Automate / Logic Apps style workflow definitions.
- Files that include keys such as:
  - `definition`
  - `triggers`
  - `actions`
  - `connectionReferences`
  - Logic Apps schema URLs
- Any flow-specific folders or exported artifacts that represent cloud flows.

### Metadata to extract per flow
For each discovered flow definition, extract at minimum:
- Flow display name or best available name
- Source file path
- Trigger names and trigger types
- Trigger connector/API IDs
- Trigger entities/tables if present (e.g., `account`, `accounts`)
- Action names and action types
- Connectors used from `connectionReferences`
- Connector/API names used directly in trigger/action `inputs.host.apiId` or `inputs.host.connectionName`
- Dataverse entities referenced in parameters such as `entityName`, `subscriptionRequest/entityname`, `recordId`, `$filter`, etc.
- Whether the flow appears to read or update `account`
- Whether it uses SQL connector or another requested connector

### Recommended analysis output
Produce a normalized manifest such as:

```json
{
  "solution": "<solution-name>",
  "runRoot": "<run-root>",
  "flowCount": 0,
  "flows": [
    {
      "name": "...",
      "file": "...",
      "connectors": ["shared_commondataserviceforapps"],
      "triggers": [
        {
          "name": "When_a_row_is_added,_modified_or_deleted",
          "type": "OpenApiConnectionWebhook",
          "entity": "account"
        }
      ],
      "actions": ["Compose", "ListRecords", "UpdateOnlyRecord"],
      "entitiesReferenced": ["account", "kdpt_postcodedistricts", "accounts"],
      "updatesAccount": true,
      "usesSql": false
    }
  ]
}
```

Store machine-readable outputs in `reports/manifest.json` and `reports/flow-summary.json` when possible.

---

## How to answer the user’s questions

Once analysis is complete, answer directly from the extracted manifest.

### Examples

If asked:
> Which flows have triggers on account?

Return:
- A concise bullet list of matching flow names.
- Mention the trigger name/type where useful.

If asked:
> How many flows are there in total?

Return:
- The total count of discovered flow definitions.
- If relevant, note whether the count includes only cloud flows discovered in the solution export.

If asked:
> Which flows use SQL connector?

Return:
- A list of flows where connectors include SQL-related API names.
- If none are found, say so clearly.

If asked a question that cannot be answered from the extracted solution alone:
- Say exactly what is missing.
- Do not guess.

---

## Connector detection guidance

When detecting connectors, inspect both:
1. `connectionReferences`
2. `inputs.host.apiId`, `inputs.host.connectionName`, and related API metadata in triggers/actions

Common examples:
- Dataverse / Common Data Service: `shared_commondataserviceforapps`
- SQL: often connector names containing `sql`
- SharePoint: connector names containing `sharepoint`
- Outlook / Office 365: connector names containing `office365`, `outlook`, etc.

Use exact matches when present, otherwise case-insensitive contains checks.

---

## Quality and safety rules

- Do not claim certainty when the export format is ambiguous.
- If flow artifacts are not found where expected, explain that not all solution exports serialize cloud flow definitions in the same layout, and report what was searched.
- Be transparent about partial analysis.
- Prefer deterministic parsing over heuristic guessing.
- Never expose secrets or credentials if any are present in extracted content.
- Never modify extracted files unless the user explicitly asks for transformation or cleanup.

---

## Error handling rules

### If PAC is missing
Say:
> Power Platform CLI (`pac`) is not available on this machine, so I can’t export the solution yet. If you want, I can help you install it or proceed with an existing solution ZIP.

### If PAC auth is missing
Say:
> PAC is installed, but I don’t see a usable authentication profile for the Dataverse environment. Please sign in or tell me which PAC auth profile/environment to use.

### If solution export fails
Say:
> The solution export failed. I’ll summarize the PAC error and stop so we can correct the solution name, auth profile, or environment.

### If extraction fails
Say:
> The ZIP export succeeded, but extraction failed. I’ll report the Python error so we can retry with the same ZIP or inspect whether the file is corrupted.

### If no flows are found
Say:
> I extracted the solution, but I couldn’t find any recognizable flow definitions in the exported contents. I can still summarize what artifacts were found and refine the search.

---

## Suggested execution order

1. Ask whether the user already has the solution ZIP.
2. If yes, collect ZIP path.
3. If no, collect solution name and confirm/select PAC auth/environment.
4. Check `pac` availability.
5. Check PAC auth profiles.
6. Create the temp workspace.
7. Export solution ZIP if needed.
8. Run Python extraction.
9. Discover flow definition files.
10. Build a manifest of flows, triggers, actions, entities, and connectors.
11. Answer the user’s question from the manifest.
12. Offer follow-up analysis, such as connector inventory or trigger/entity matrix.

---

## Output style

When reporting results:
- Start with a short answer.
- Then show the supporting list or count.
- Include the workspace path if relevant for troubleshooting.
- Offer a follow-up question like:
  - “Do you want a connector inventory for all flows?”
  - “Do you want me to list every flow that references the Account table?”

---

## Example follow-up prompts this skill should handle well
- Analyze this Dataverse solution for cloud flows.
- Which flows trigger on account?
- Count all Power Automate flows in this solution.
- Which flows use the SQL connector?
- Show all Dataverse entities referenced by flows in this solution.
- Which flows update accounts?
- Which connectors are used across all flows?
- Export my solution and tell me how many flows it contains.
