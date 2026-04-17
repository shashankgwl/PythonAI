---
name: dv-ribbonworks
description: Create and update Dataverse model-driven app command bar buttons using a deterministic PowerShell RibbonDiffXml patcher with a safe, plan-first workflow intended as a practical Ribbon Workbench replacement for common button scenarios.
---

## Dataverse RibbonWorks Skill

This skill is a **practical Ribbon Workbench replacement** for common Dataverse command bar button work using **Ribbon XML** and a **fixed deterministic PowerShell patcher**.

### Primary outcome
- Ask only for the minimum safe inputs.
- Build one deterministic plan.
- Create a per-run temp workspace under `$env:TEMP` and show its absolute path.
- Export the chosen unmanaged solution.
- Locate the correct RibbonDiff.xml artifact.
- Invoke the checked-in PowerShell patcher `./scripts/Patch-RibbonDiff.ps1` with explicit parameters.
- Repack and import the solution when `dryRun = false`.
- Publish only when `dryRun = false` and the user explicitly asked for publish.
- Return a concise verification report.

---

## Design principle: the skill orchestrates, PowerShell mutates

For the common scenario, the workflow is intentionally simple:
1. Confirm environment.
2. Confirm unmanaged solution.
3. Collect only the missing button inputs.
4. Produce one dry-run plan.
5. Require one approval for execution.
6. Export -> backup -> unpack -> patch via the provided PowerShell file.
7. If `dryRun = false`: pack -> import with `--stage-and-upgrade`.
8. Publish if approved in the plan and `dryRun = false`.
9. Verify and report.

Do **not** drift into alternate implementation paths, speculative XML generation, or repeated approval loops once the user already approved the latest plan.

The AI must **never generate Ribbon XML inline as the mutation engine**. All RibbonDiffXml mutation for supported scenarios must happen through the deterministic PowerShell script described below.

---

## Scope

Use this skill only for **Ribbon XML** command bar customization in Dataverse model-driven apps.

### Supported by the current deterministic PowerShell patcher
- Create a new custom button.
- Update the same custom button deterministically when the generated IDs match.
- Create a placeholder button with `action type = none`.
- Create a JavaScript-bound button with `action type = javascript`.

### Not supported by the current deterministic PowerShell patcher
- Hide existing commands.
- Override existing out-of-box commands.
- Add custom DisplayRule / EnableRule logic.
- Add localization labels beyond direct button text attributes.
- Patch arbitrary existing command trees outside the supported container mappings.
- In-place rename when the new label changes generated IDs.

For `operation = update`, deterministic update is ID-based. If table/location/publisher prefix/button label produce a different ID base, the result is effectively a new button plus the old button remaining in place.

If the user asks for an unsupported operation, do **not** fake completion. State that the current deterministic patcher does not yet support that scenario and stop after producing a clear gap report or implementation recommendation.

---

## Deterministic execution policy

Always separate:
- **Planner layer**: interprets user intent, resolves inputs, produces the plan.
- **Executor layer**: performs PAC CLI commands and calls the fixed PowerShell patcher.

Never let free-form narrative text act as the mutation engine.
Never invent success when a command, artifact, or capability is missing.
Never generate ad-hoc RibbonDiffXml or ad-hoc PowerShell during execution when the supported scenario can be handled by the checked-in patcher.

---

## Minimal safe inputs

Ask only for missing inputs that are required for safe execution.

### Required in supported scenarios
- Target environment.
- Target unmanaged solution.
- Table logical name.
- Location.
- Operation: `create` or `update`.
- Button label.
- Action type: `none` or `javascript`.
- Publish after import: yes/no.
- Dry-run only: yes/no.

### Only ask these when needed
- Publisher prefix (only when creating new IDs and it cannot be derived safely).
- JavaScript web resource name and function (only for `javascript` action type).
- Explicit container override (only when the standard location mapping is known to be insufficient and the user or repository provides the exact supported container location).
- Existing button identity inputs for update safety (`publisherPrefix` and current `button.label`) when they are not already known.

### Default behavior for simple create scenarios
- Publisher prefix defaults to `new` if no usable value is supplied.
- JavaScript parameter contract is `PrimaryControl` when `action type = javascript`.
- `none` action type creates a placeholder/no-op button with no JS requirement.
- No custom EnableRule / DisplayRule nodes are created for the placeholder path.

---

## Conversation contract

### 1) Environment first
Run:
- `pac auth list`
- `pac auth who`
- `pac env who`
- `pac env list`

Behavior:
- Show the active environment.
- If multiple environments are available, ask the user to choose one.
- Do not ask solution questions before environment confirmation.

### 2) Solution second
Run:
- `pac solution list`

Behavior:
- Ask which unmanaged solution to use.
- Never default to Default Solution unless the user explicitly insists.
- Confirm that the selected solution exists.

### 3) Collect the supported button spec
Normalize to this structure:

```json
{
  "environment": "<env>",
  "solution": "<solution>",
  "publisherPrefix": "<prefix or new>",
  "table": "contact",
  "location": "mainForm",
  "operation": "create",
  "button": {
    "label": "My Button"
  },
  "action": {
    "type": "none",
    "webResource": null,
    "function": null,
    "parameters": []
  },
  "publish": true,
  "dryRun": false,
  "containerOverride": null
}
```

When `operation = update`, carry this additional safety note in planning:
- `identityWarning`: `"update is deterministic only when generated IDs are unchanged"`

### 4) Produce exactly one approval plan
Use this format:

Plan:
1. Target environment: <env>
2. Target solution: <solution>
3. Target table/location: <table> / <location>
4. Mode: ribbonXml via deterministic PowerShell patcher
5. Changes:
   - Operation: <create/update>
   - Button label: <value>
   - Action type: <none/javascript>
   - Web resource/function: <value or not required>
   - Container location: <resolved standard mapping or explicit override>
6. Execution:
    - Create temp workspace under `$env:TEMP` and display its absolute path
    - Export unmanaged solution
    - Create rollback backup
    - Unpack solution
    - Locate target RibbonDiff.xml
    - Invoke fixed PowerShell patcher
    - If dry-run = no: Repack solution
    - If dry-run = no: Import solution with `--stage-and-upgrade`
    - If dry-run = no: Publish: <yes/no>
    - If dry-run = yes: Skip pack/import/publish and output artifact verification only
7. Rollback point: <backup zip path>
8. Verification:
   - target RibbonDiff.xml patched
   - expected CustomAction/Command/Button IDs present
   - javascript binding valid when applicable
   - import succeeded
   - publish succeeded if requested
Risk level: <Low/Medium/High>
Reasoning: <1-3 lines>

### 5) Approval gate
Accepted approvals:
- Proceed
- Yes
- Apply
- Run now

Once the user approves the latest plan, do **not** ask for another confirmation for patch/import/publish if those steps were already included in the approved plan.

---

## Required execution path

### Working directory policy (mandatory)
All export, unpack, patch, pack, and backup artifacts must be placed under a per-run temp workspace rooted at `$env:TEMP`.

Use this pattern:
- `<$env:TEMP>/dv-ribbonworks/<solution>.<yyyyMMddHHmmss>`

Before any mutation, print the resolved absolute paths so the user can open the folder directly.

### Shared preflight
Run:
- `pac auth list`
- `pac auth who`
- `pac env who`
- `pac env list`
- `pac solution list`

Stop if environment or solution is not confirmed.

### Export / backup / unpack
Run:
- `pac solution export --name "<solution>" --path "<temp-workdir>/<solution>.unmanaged.zip"`
- Create timestamped backup copy before any mutation.
- `pac solution unpack --zipfile "<temp-workdir>/<solution>.unmanaged.zip" --folder "<temp-workdir>/unpacked/<solution>" --packagetype Unmanaged`
- Display:
  - `Temp workspace: <absolute-temp-workdir-path>`
  - `Unpacked folder: <absolute-temp-workdir-path>/unpacked/<solution>`

### Ribbon artifact selection
Search the unpacked solution for Ribbon XML artifacts using this deterministic resolver:
1. Build candidate list of all `RibbonDiff.xml` files.
2. For table-scoped requests, keep only candidates under `Entities/*/RibbonDiff.xml`.
3. Prefer exact table folder name match (case-insensitive) to `<table logical name>`.
4. If no exact folder match, inspect candidate XML for table-specific location patterns containing `.<table>.` and keep matching candidates only.
5. If exactly one candidate remains, select it.
6. If zero or multiple candidates remain, stop and ask for explicit artifact path (do not patch ambiguously).

Use application ribbon artifacts only when the scenario is truly app/global scoped and explicitly requested.

Expected table-scoped path pattern example:
- `Entities/<TableDisplayFolder>/RibbonDiff.xml`

### Deterministic PowerShell patcher (mandatory)
For all supported create/update button scenarios, the executor must call a **checked-in fixed script** instead of generating XML or PowerShell inline.

Recommended script path:
- `./scripts/Patch-RibbonDiff.ps1`

Required invocation shape:

```powershell
pwsh -File ./scripts/Patch-RibbonDiff.ps1 \
  -RibbonDiffPath "<path-to-RibbonDiff.xml>" \
  -TableLogicalName "<table>" \
  -Location "<mainForm|mainGrid|subGrid|associatedView>" \
  -ButtonLabel "<label>" \
  -PublisherPrefix "<prefix>" \
  -ActionType "<none|javascript>" \
  [-WebResourceName "<webresource>"] \
  [-FunctionName "<function>"] \
  [-ContainerLocation "<explicit-container-override>"]
```

The script is the mutation engine. The AI must only resolve and pass parameters.

Do **not** generate ad-hoc XML snippets during execution when this script can handle the request.

---

## Fixed patcher contract

The skill must assume and rely on these script behaviors:

### Script parameters
- `RibbonDiffPath` (required)
- `TableLogicalName` (required)
- `Location` = `mainForm | mainGrid | subGrid | associatedView` (required)
- `ButtonLabel` (required)
- `PublisherPrefix` (optional, defaults to `new`)
- `ActionType` = `none | javascript` (optional, defaults to `none`)
- `WebResourceName` (required when `ActionType=javascript`)
- `FunctionName` (required when `ActionType=javascript`)
- `Sequence` (optional, defaults to `100`)
- `ContainerLocation` (optional explicit override)

### Script-generated standard container mappings
If `ContainerLocation` is not supplied, the script resolves the container as follows:
- `mainForm` -> `Mscrm.Form.<table>.MainTab.Actions.Controls._children`
- `mainGrid` -> `Mscrm.HomepageGrid.<table>.MainTab.Management.Controls._children`
- `subGrid` -> `Mscrm.SubGrid.<table>.MainTab.Actions.Controls._children`
- `associatedView` -> `Mscrm.AssociatedMenu.<table>.MainTab.Actions.Controls._children`

The skill must **not** substitute `...MainTab.CommandBar` for supported create/update button scenarios.

### Script-generated IDs
The skill must assume the script generates IDs as follows:
- Normalize publisher prefix to remove invalid characters and trim trailing separators; default to `new` if empty.
- Normalize button label to a lowercase alphanumeric slug.
- Base ID = `<prefix>.<table>.<location>.<slug>`
- CustomAction = `<base>.CustomAction`
- Command = `<base>.Command`
- Button = `<base>.Button`

The skill must not claim different ID patterns for supported operations.

### Script behavior for `action type = none`
- Creates a placeholder/no-op button.
- Creates `CommandDefinition` with empty `<EnableRules />`, empty `<DisplayRules />`, and empty `<Actions />`.
- Does **not** create custom rule references.
- Does **not** require a JS web resource.

### Script behavior for `action type = javascript`
- Requires `WebResourceName` and `FunctionName`.
- Creates a `<JavaScriptFunction>` action.
- Binds `<CrmParameter Value="PrimaryControl" />`.

### Script idempotency
- Removes existing `CustomAction` with the same generated ID before writing the new one.
- Removes existing `CommandDefinition` with the same generated ID before writing the new one.
- Re-running the same spec should update in place rather than duplicate the same generated IDs.

### Script limitations
- Does not generate custom EnableRule / DisplayRule definitions.
- Does not create `LocLabels` entries.
- Does not currently implement hide/override flows.

If the requested behavior needs any of the above unsupported capabilities, stop and report the gap clearly.

---

## Action binding rules

### If action type is `javascript`
- Ask for `WebResourceName` and `FunctionName`.
- Ensure the web resource exists or is being created by a separate deterministic process.
- Validate that the function symbol is expected in the JS content when verification data is available.
- Pass the values directly to the fixed PowerShell patcher.

### If action type is `none`
- Create a placeholder/no-op button with no JS web resource requirement.
- Do not ask unnecessary JavaScript questions.
- Do not claim that custom rules were created.

---

## Pack / import / publish
When `dryRun = false`, run:
- `pac solution pack --zipfile "<temp-workdir>/<solution>.patched.zip" --folder "<temp-workdir>/unpacked/<solution>" --packagetype Unmanaged`
- `pac solution import --path "<temp-workdir>/<solution>.patched.zip" --stage-and-upgrade`
- `pac solution publish` when publish was approved

When `dryRun = true`:
- Do not run `pack`, `import`, or `publish`.
- Report the exact patched artifact path and the expected generated IDs from the patcher output.

Do not insert an extra confirmation gate between patching and importing if the approved plan already included import.

---

## Verification gates

Report success only if all applicable checks pass.

### Artifact verification
- Target RibbonDiff.xml exists.
- Resolved container location matches the script mapping or the approved explicit override.
- Expected generated `CustomAction`, `Command`, and `Button` IDs are present exactly once in the patched artifact.
- For `none`, confirm empty `EnableRules`, `DisplayRules`, and `Actions` were written without dangling custom rule references.
- For `javascript`, confirm `JavaScriptFunction` exists and references the expected library/function.

### Platform verification
- If `dryRun = false`: Import completed successfully.
- If `dryRun = false`: Publish completed successfully when requested.
- If `dryRun = true`: Import/publish intentionally skipped.

### Optional manual smoke test checklist
- Open the target app/table location.
- Confirm button visibility and label.
- Click the button and verify expected behavior.

---

## Error handling rules

Classify failures as one of:
- Auth/Environment
- Solution not found
- Ribbon artifact not found
- Unsupported operation for current patcher
- Unsupported container mapping
- PowerShell patcher failure
- Import failure
- Publish failure
- JavaScript binding mismatch

For every failure report:
- exact failed step
- exact command or file that failed
- safe next action

Never claim completion after a failed export, unpack, patch, import, or publish step.

---

## Rollback policy

Before import, create:
- `<solution>.backup.<yyyyMMddHHmmss>.zip`
- Store the backup zip under the same temp workspace rooted at `$env:TEMP`.

Rollback triggers:
- import failure
- verification failure
- user asks to rollback

Rollback steps:
- import the backup zip
- publish if needed
- rerun verification
- report rollback outcome

---

## Clarification rules

Ask only focused clarifications that unblock safe execution.

Allowed examples:
- Which unmanaged solution should I use?
- Which location: main form or main grid?
- Should the button be placeholder (`none`) or `javascript`?
- If `javascript`, what web resource and function should be bound?
- Publish after import?
- Do you want to supply an explicit container override, or should I use the standard mapping from the fixed patcher?

Do **not** ask unnecessary follow-up questions once the inputs are already sufficient.
Do **not** re-ask a location question after the user already selected a normalized location such as `main form`, unless the request is still genuinely ambiguous.
Do **not** invent a new XML strategy if the fixed patcher already supports the requested scenario.

---

## Output conventions

When responding:
- State mode: `ribbonXml via deterministic PowerShell patcher`.
- Show the dry-run plan first.
- Ask for one approval.
- After execution, provide a final report.

Final report format:

Status: Success | Partial | Failed
Applied changes:
- <change>
- <change>
Verification:
- <result>
- <result>
Publish:
- executed | skipped | failed | dry-run skipped
Rollback:
- not needed | available at <path> | applied
Notes:
- temp workspace path: <absolute path>
- <follow-up or limitation>

---

## Implementation reference

### Supported generated IDs
- Command: `<prefix>.<table>.<location>.<slug>.Command`
- Button: `<prefix>.<table>.<location>.<slug>.Button`
- CustomAction: `<prefix>.<table>.<location>.<slug>.CustomAction`

### Supported container mappings
- `mainForm` -> `Mscrm.Form.<table>.MainTab.Actions.Controls._children`
- `mainGrid` -> `Mscrm.HomepageGrid.<table>.MainTab.Management.Controls._children`
- `subGrid` -> `Mscrm.SubGrid.<table>.MainTab.Actions.Controls._children`
- `associatedView` -> `Mscrm.AssociatedMenu.<table>.MainTab.Actions.Controls._children`

### Minimal XML shape written by the fixed patcher for `none`
```xml
<CustomAction Id="<CustomActionId>" Location="<ContainerLocation>" Sequence="100">
  <CommandUIDefinition>
    <Button Id="<ButtonId>"
            Command="<CommandId>"
            LabelText="<ButtonLabel>"
            ToolTipTitle="<ButtonLabel>"
            ToolTipDescription="<ButtonLabel>"
            Sequence="100"
            TemplateAlias="o1" />
  </CommandUIDefinition>
</CustomAction>

<CommandDefinition Id="<CommandId>">
  <EnableRules />
  <DisplayRules />
  <Actions />
</CommandDefinition>
```

### Minimal XML shape written by the fixed patcher for `javascript`
```xml
<Actions>
  <JavaScriptFunction Library="$webresource:<webresource-name>" FunctionName="<function-name>">
    <CrmParameter Value="PrimaryControl" />
  </JavaScriptFunction>
</Actions>
```

---

## Done criteria

A request is complete only when all are true:
- latest plan was approved
- deterministic mutation completed through the fixed PowerShell patcher
- verification gates passed
- publish matched the approved plan
- final report includes rollback state

### Final rule
This skill exists to make Dataverse command bar button changes simple, deterministic, reviewable, and safe by using a fixed PowerShell patcher as the only supported mutation engine for common Ribbon Workbench replacement scenarios.
