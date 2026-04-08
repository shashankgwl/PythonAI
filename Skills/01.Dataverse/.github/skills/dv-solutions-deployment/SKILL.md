---
name: dv-solutions-deployment
description: Move one or more Microsoft Dataverse solutions from a source environment to a target environment using PAC CLI with service-principal authentication. The skill can use interactive input or a deployment.json file, exports from source, imports into target, and deletes temporary PAC auth profiles at the end.
argument-hint: "[deployment.json path] or [source environment] [target environment] [solution names]"
---

# Dataverse Solutions Deployment Skill

Use this skill when the user wants to move one or more Dataverse solutions from one environment to another using PAC CLI.

This skill supports:
- interactive source and target environment selection
- interactive solution selection
- listing available solutions from the source environment
- file-driven execution using a `deployment.json` file
- export from source environment
- import into target environment
- service-principal PAC authentication created at runtime and removed when work is complete

## Core rules
- Use only documented PAC auth, PAC env, and PAC solution commands.
- Always create PAC auth profiles with `pac auth create` using the **Named Create with Service Principal** pattern.
- Always create fresh PAC auth profiles for both source and target environments for the current run.
- Always delete the temporary PAC auth profiles created by this skill after the work is done by using `pac auth delete --index`.
- Never use browser-based interactive login for this skill when service-principal values are available.
- Never use `pac auth clear` as part of normal flow.
- Always validate the active source environment before export.
- Always validate the active target environment before import.
- Always verify that source and target environments are different.
- Always verify that export paths are full `.zip` file paths.
- Always verify that import paths exist before import.
- Never overwrite an existing export file unless the user explicitly approves it.
- If any export fails, stop before import.
- If any import fails, stop and report the failure.
- If the user provides `deployment.json`, use it as the primary source of truth.

## Service-principal authentication model
This skill must create auth profiles by using the documented PAC service-principal flow:

```powershell
pac auth create --name <profile-name> --applicationId <client-id> --clientSecret <client-secret> --tenant <tenant-id> --environment <environment>
```

The skill must:
1. create a named auth profile for the source environment
2. capture the profile index from `pac auth list`
3. select it with `pac auth select --index <index>`
4. run export work
5. create a named auth profile for the target environment
6. capture the profile index from `pac auth list`
7. select it with `pac auth select --index <index>`
8. run import work
9. delete both temporary profiles at the end using `pac auth delete --index <index>`

If cleanup runs after a failure, still attempt to delete any profile that was created successfully.

## Inputs

### Option A — Interactive mode
The user can provide:
- source environment
- target environment
- one or more solution names
- whether export should be managed or unmanaged
- optional output directory or zip paths
- source service-principal credentials
- target service-principal credentials

### Option B — File-driven mode
The user can point to a `deployment.json` file.

If a `deployment.json` file is present:
- read it first
- validate required fields
- ask follow-up questions only for missing values

## deployment.json schema

```json
{
  "sourceEnvironment": {
    "name": "string",
    "ClientId": "string",
    "ClientSecret": "string",
    "TenantId": "string"
  },
  "targetEnvironment": {
    "name": "string",
    "ClientId": "string",
    "ClientSecret": "string",
    "TenantId": "string"
  },
  "solutions": {
    "exportProfile": {
      "solutions": [
        {
          "name": "string",
          "managed": true,
          "exportPath": "string",
          "exportVersion": "string"
        }
      ]
    },
    "importProfile": {
      "targetEnvironmentName": "string",
      "solutions": [
        {
          "name": "string"
        }
      ]
    }
  }
}
```

## JSON validation rules
- `sourceEnvironment.name` and `targetEnvironment.name` must be non-empty strings.
- `sourceEnvironment.ClientId`, `sourceEnvironment.ClientSecret`, `sourceEnvironment.TenantId` must be present.
- `targetEnvironment.ClientId`, `targetEnvironment.ClientSecret`, `targetEnvironment.TenantId` must be present.
- `solutions.exportProfile.solutions` must contain at least one solution.
- every export solution must have `name`, `exportPath`, and `exportVersion`.
- `exportVersion` must follow Dataverse solution version format: `major.minor.build.revision`.
- `exportPath` must end with `.zip`.
- if .zip isn't present then consider the solution name with .zip as the export path.
- source and target environments must not resolve to the same environment.
- if validation fails, report all validation errors and stop.

## Workflow

### Step 1: Validate prerequisites
Check that PAC CLI is installed and available in the current shell.

If PAC CLI is missing:
- stop
- tell the user to install or enable PAC CLI first

### Step 2: Resolve input mode
Determine whether the user is using:
- interactive mode, or
- `deployment.json`

If `deployment.json` is provided:
- read it
- validate it
- use it as the primary input source

If not:
- ask the user for source environment, target environment, solutions, and service-principal values

### Step 3: Resolve credentials and environments
Resolve the following for both source and target:
- environment value to pass to PAC (`name`, environment ID, URL, unique name, or partial name)
- client ID
- client secret
- tenant ID

If any required value is missing:
- stop and ask only for the missing values

Verify source and target are different.

### Step 4: Create source PAC auth profile with service principal
Create a unique source profile name, for example:
- `dv-alm-src-<timestamp>`

Run:

```powershell
pac auth create --name "<source-profile-name>" --applicationId "<source-client-id>" --clientSecret "<source-client-secret>" --tenant "<source-tenant-id>" --environment "<source-environment>"
```

Then run:
- `pac auth list`

Find the index of the newly created source profile.
Store that index for cleanup.

Select it:

```powershell
pac auth select --index <source-profile-index>
```

Verify the active source environment:
- `pac auth who`
- `pac env who`

Show the active source environment and ask for confirmation before export.

If the selected source environment is wrong:
- stop
- do not export
- do not fall back to another environment automatically

### Step 5: Resolve solutions
If the user does not know exact solution names, run:
- `pac solution list`

Then ask which solution(s) to move.

### Step 6: Export from source
For each solution:
- verify `exportPath`
- verify overwrite intent if the file already exists

Managed export:

```powershell
pac solution export --name "<solution-name>" --path "<export-path>" --managed
```

Unmanaged export:

```powershell
pac solution export --name "<solution-name>" --path "<export-path>"
```

After each export:
- confirm PAC output indicates success
- confirm the zip file exists
- report progress

If any export fails:
- stop before import
- continue to cleanup of any created auth profiles

### Step 7: Create target PAC auth profile with service principal
Create a unique target profile name, for example:
- `dv-alm-tgt-<timestamp>`

Run:

```powershell
pac auth create --name "<target-profile-name>" --applicationId "<target-client-id>" --clientSecret "<target-client-secret>" --tenant "<target-tenant-id>" --environment "<target-environment>"
```

Then run:
- `pac auth list`

Find the index of the newly created target profile.
Store that index for cleanup.

Select it:

```powershell
pac auth select --index <target-profile-index>
```

Verify the active target environment:
- `pac auth who`
- `pac env who`

Show the active target environment and ask for confirmation before import.

If the selected target environment is wrong:
- stop
- do not import
- do not fall back to another environment automatically

### Step 8: Import into target
Before import:
- verify each exported zip file exists

For each package, run:

```powershell
pac solution import --path "<export-path>"
```

If doing a managed import and the solution already exists in the target environment, prefer upgrade behavior only if the documented command set available in the current PAC version supports it and the user explicitly requested it.

After each import:
- confirm PAC output indicates success
- report progress

If any import fails:
- stop
- continue to cleanup of any created auth profiles

### Step 9: Cleanup temporary PAC auth profiles
At the end of the run, whether success or failure, delete any auth profiles that were created by this skill.

Delete source profile:

```powershell
pac auth delete --index <source-profile-index>
```

Delete target profile:

```powershell
pac auth delete --index <target-profile-index>
```

Only delete profiles created by this skill during the current run.
Never delete unrelated profiles.

### Step 10: Final summary
Summarize:
- source environment used
- target environment used
- solution names
- export paths
- export results
- import results
- cleanup results for source and target PAC auth profiles

## Safety and correctness constraints
- Do not claim export success unless PAC output confirms success and the zip file exists.
- Do not claim import success unless PAC output confirms success.
- Do not skip cleanup of temporary auth profiles when possible.
- Do not delete any PAC auth profile not created by this skill in the current run.
- Do not use browser/device-code login when service-principal values are available.
- Do not proceed if source and target environments are the same.
- Do not proceed if required service-principal values are missing.

## Prompt examples

### Example 1
"Use deployment.json to move my Dataverse solutions from source to target using service principal auth, and delete the PAC auth profiles when done."

### Example 2
"Move CustomRAG from DEV to TEST using managed export and import. I will provide source and target client IDs, secrets, and tenant IDs."

### Example 3
"List solutions from the source environment, let me choose which ones to move, authenticate source and target with service principals, and delete the PAC auth profiles after the job completes."

## Output style
When using this skill:
- clearly separate phases: input resolution, source auth, export, target auth, import, cleanup, summary
- show the exact PAC command before running sensitive actions
- stop immediately if authentication, environment, or file-path context is uncertain
