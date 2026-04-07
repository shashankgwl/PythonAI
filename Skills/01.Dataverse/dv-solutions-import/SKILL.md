---
name: dv-solutions-import
description: Import one or more Microsoft Dataverse solution zip files into the currently selected PAC CLI environment. The skill validates PAC auth, shows the active target environment, asks for explicit confirmation, and only then performs solution import.
argument-hint: "[solution zip path(s)] [target environment confirmation]"
---

# Dataverse Solution Import Skill

Use this skill when the user wants to import one or more Dataverse solution zip files into a target Dataverse environment using PAC CLI.

This skill is **import only**.
- Do **not** export solutions.
- If the user asks to export a solution, stop and explain that this skill only imports solutions.
- If export automation is needed, that should be handled by a separate export skill.

## Important behavioral rules
- Do not invent PAC CLI commands or parameters.
- Use only documented PAC auth, PAC env, and PAC solution commands.
- Always validate PAC authentication before any environment-specific action.
- Always show the active PAC profile and the active Dataverse environment before importing.
- Always ask for explicit user confirmation before importing into the selected environment.
- Never assume the current environment is correct.
- Never silently switch to another environment if import fails.
- Never chain environment selection and import into a single command without first re-validating the selected environment.
- Never use `pac auth clear --index` because `pac auth clear` clears all authentication profiles and is not an indexed delete operation.
- If re-authentication is needed, prefer creating a new auth profile with `pac auth create` and then explicitly selecting it.
- If the current authentication appears invalid or stale, stop and ask the user whether to create a new profile or manually troubleshoot the profile.
- Always verify that the import path points to an existing solution zip file.
- Never import from an unknown or missing file path.
- Never overwrite or upgrade a target environment without the user's explicit approval.
- If the user is unsure whether the package is managed or unmanaged, explain the difference before continuing.

## Supported capabilities
- Validate PAC CLI availability
