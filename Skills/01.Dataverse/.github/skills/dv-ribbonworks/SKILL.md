---
name: dv-formbench
description: Add or update a Dataverse command bar button for an entity main form only by exporting an unmanaged solution, patching RibbonDiff.xml with a fixed PowerShell script, and importing it back.
---

## Dataverse RibbonWorks (Entity Main Form Only)

This skill is intentionally narrow:
- Target: entity `mainForm` command bar only.
- Mutation engine: `./scripts/Patch-RibbonDiff.ps1` only.
- No main grid, subgrid, associated view, hide, or override scenarios.

### Required user flow
1. Ask user to select environment.
2. Ensure authentication is valid.
3. Ask for button details one by one (NOT all questions at once):
   - Button label.
   - JavaScript library web resource name.
   - JavaScript function name.
   - Icon choice (must ask every run): give following choices, `ignore`, `existing web resource`.
   - If icon = existing web resource: ask for one or two image web resource names.
4. Show a simple plan and ask for approval.
5. Execute with PAC CLI: export -> unpack -> patch with PowerShell -> pack -> import -> publish.

### Minimal inputs
- Environment.
- Unmanaged solution name.
- Table logical name.
- Button label.
- JavaScript library web resource name.
- JavaScript function name.
- Icon choice (must ask once per run).

### Icon rules
- If one icon web resource name is supplied, reuse it for both `Image16by16` and `Image32by32`.
- If icon choice is `ignore`, do not pass icon parameters to the patcher.
- If icon choice is `local SVG file path`, validate the local file exists before patching.
- For local SVG mode, use or resolve deterministic image web resource name(s) before patching.

### Simple plan format
Use this exact concise structure:

Plan:
- Environment: <env>
- Solution: <solution>
- Table: <table>
- Temp workspace: $env:TEMP\dv-formbench\<guid>
- Export path: $env:TEMP\dv-formbench\<guid>\<solution>.unmanaged.zip
- Scope: entity mainForm command bar only
- Button label: <label>
- JavaScript library: <webresource name>
- JavaScript function: <function name>
- Icon choice: <ignore/existing web resource/local SVG file path>
- Icon source: <none/path/webresource>
- Icon web resource names: <value(s) or not required>
- Steps:
  - Validate auth/environment
  - Export unmanaged solution
  - Unpack solution
  - Locate `Entities/*/RibbonDiff.xml` for the table
  - Run `./scripts/Patch-RibbonDiff.ps1`
  - Pack solution
  - Import solution
  - Publish customizations

### Required execution path
- `pac auth list`
- `pac auth who`
- `pac env who`
- `pac solution list`
- Create temp workspace: `$tempRoot = Join-Path $env:TEMP ("dv-formbench\" + [guid]::NewGuid().ToString())`
- `pac solution export --name "<solution>" --path "$tempRoot\<solution>.unmanaged.zip"`
- `pac solution unpack --zipfile "$tempRoot\<solution>.unmanaged.zip" --folder "$tempRoot\unpacked\<solution>" --packagetype Unmanaged`
- Identify target file: `Entities/<entity folder>/RibbonDiff.xml`
- Run patcher:

```powershell
pwsh -File ./scripts/Patch-RibbonDiff.ps1 \
  -RibbonDiffPath "<path-to-RibbonDiff.xml>" \
  -TableLogicalName "<table>" \
  -ButtonLabel "<label>" \
  -JavaScriptLibraryWebResourceName "<js-webresource-name>" \
  -JavaScriptFunctionName "<function-name>" \
  -PublisherPrefix "<prefix-or-new>" \
  [-Image16by16WebResourceName "<image-webresource-name>"] \
  [-Image32by32WebResourceName "<image-webresource-name>"]
```

- `pac solution pack --zipfile "$tempRoot\<solution>.patched.zip" --folder "$tempRoot\unpacked\<solution>" --packagetype Unmanaged`
- `pac solution import --path "$tempRoot\<solution>.patched.zip" --stage-and-upgrade`
- `pac solution publish`

### Verification
- Target `RibbonDiff.xml` was updated.
- `CustomAction`, `Button`, and `CommandDefinition` IDs exist once.
- `CommandDefinition/Actions/JavaScriptFunction` exists once and points to the requested web resource and function.
- Location uses `Mscrm.Form.<table>.MainTab.Actions.Controls._children`.
- If icon provided, `Image16by16`/`Image32by32` contain `$webresource:` values.

### Clarification examples
- Which environment should I use?
- Which unmanaged solution should I use?
- What is the table logical name?
- What button label should I set?
- What JavaScript library web resource name should the button call?
- What JavaScript function name should the button call?
- For icon, do you want: ignore, existing web resource, or local SVG file path?
- If local SVG: what is the file path and target image web resource name?

### Schema references
- https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/ribbon-core-schema
- https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/ribbon-types-schema
- https://learn.microsoft.com/en-us/power-apps/developer/model-driven-apps/ribbon-wss-schema
