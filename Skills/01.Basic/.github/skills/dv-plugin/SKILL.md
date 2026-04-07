---
name: dv-plugin
description: Scaffold, write, build, and optionally deploy a Microsoft Dataverse / Dynamics 365 C# plug-in package using PAC CLI based on the user's natural-language requirements.
argument-hint: "[business requirement] [project folder] [table] [message] [stage] [sync/async] [first deployment or update]"
---

# Dataverse Plug-in Project Generator

Use this skill when the user wants to create, modify, build, or deploy a Microsoft Dataverse / Dynamics 365 plug-in project in C#.

This skill is designed for:
- Creating a new plug-in package project with PAC CLI
- Generating or updating plug-in C# code from natural-language requirements
- Building the project/package
- Updating an existing registered plug-in package
- Guiding the user through first-time registration and step registration when needed

## Important behavioral rules
- Do not invent PAC commands or parameters.
- Prefer documented PAC CLI commands and documented Plug-in Registration Tool workflows.
- Never deploy if the project does not build successfully.
- Treat first-time registration differently from updating an existing package.
- Ask clarifying questions only when required inputs are missing.
- Generate stateless plug-in code.
- Do not overwrite existing user code without warning the user.
- Always validate PAC auth, show the active environment, and obtain explicit user confirmation before any Dataverse-affecting action.
- Never assume the active environment is correct.

## Supported capabilities

### A. Project scaffolding
Create a new Dataverse plug-in package project in the requested folder using PAC CLI.

Preferred command:
- `pac plugin init --skip-signing`

Use `--skip-signing` unless the user explicitly requires assembly signing.

### B. Code generation
Generate a C# plug-in class based on the user's natural-language specification.

The generated code should:
- target Dataverse plug-in patterns
- implement `IPlugin` or follow the generated `PluginBase` pattern already present in the scaffolded project
- be stateless
- use tracing and clear exception handling when appropriate
- avoid unnecessary dependencies
- keep business logic readable and maintainable

### C. Build
Build the plug-in project/package after generating or modifying code.

Use the build tooling available in the environment. Prefer:
- Visual Studio/MSBuild-compatible build commands
- the project's existing build configuration

If the build fails:
- inspect the compiler errors
- fix the code
- rebuild
- do not proceed to deployment until the build is clean

### D. Deployment / update
If the user provides an existing `pluginId`, update the existing plug-in assembly/package using:
- `pac plugin push --pluginId <id>`

If the user does **not** provide a `pluginId` and this is a first-time deployment:
- do **not** pretend that `pac plugin push` can fully perform initial registration on its own
- launch or instruct the user to launch Plug-in Registration Tool using:
  - `pac tool prt`
- guide the user through:
  - importing/registering the generated NuGet package
  - registering the plug-in assembly/package
  - registering the required step(s)

## Required inputs to collect
Before generating code, gather these inputs if they are not already provided.

### Project / packaging
- project folder name
- desired project/assembly name
- namespace
- class name
- whether signing is required or not

### Plug-in behavior
- target table/entity logical name
- message/operation (`Create`, `Update`, `Delete`, etc.)
- execution stage (`PreValidation` / `PreOperation` / `PostOperation`)
- synchronous or asynchronous execution
- filtering attributes (for `Update` steps)
- whether pre-images or post-images are required
- expected business logic
- required tracing or custom exception behavior

### Deployment mode
- whether this is:
  - **first-time registration**, or
  - **update of an existing registered package**
- if update:
  - `pluginId`
  - optional target environment URL if different from the active auth profile

## Environment confirmation policy
Before any Dataverse-affecting action, always:
1. check that PAC authentication exists
2. show the active PAC auth profile and environment
3. ask the user for explicit confirmation
4. stop if the environment is not confirmed

Never deploy, update, or register against Dataverse without explicit confirmation of the target environment.

## Workflow

### Step 1: Validate prerequisites
Check that the local machine has the required tools and context.

Verify:
- PAC CLI is installed
- required build tooling is available
- the requested project folder is writable
- the user has sufficient privileges in the target environment if deployment or registration is requested

If PAC CLI is missing:
- stop and tell the user to install it before continuing

### Step 2: Validate PAC authentication
Run:
- `pac auth list`

If there are no auth profiles:
- stop
- tell the user that Power Platform CLI authentication is required
- instruct the user to authenticate using:
  - `pac auth create`
- do not continue until authentication is available

Then run:
- `pac auth who`

Use the result to identify:
- the active auth profile
- the connected Dataverse environment URL
- the signed-in user
- any friendly profile/environment name if available

### Step 3: Confirm target Dataverse environment
Always tell the user which environment is currently selected before continuing.

Use wording like:
- "The active PAC auth profile is connected to: <environment-url-or-name>."
- "Do you want me to continue against this environment?"

Wait for explicit user confirmation before:
- running `pac plugin init`
- launching Plug-in Registration Tool
- running `pac plugin push`
- or performing any environment-specific action

If the user says the selected environment is incorrect:
- stop
- instruct the user to switch authentication context first
- suggest:
  - `pac auth list`
  - `pac auth select`
  - or `pac auth create --environment "<name-or-url>"`
- do not continue until the user confirms the intended environment

If the user explicitly provides an environment URL or environment id for deployment/update:
- prefer that explicit environment when supported by the PAC command
- still show the resolved target environment and ask for confirmation before continuing

### Step 4: Determine scenario
Classify the request into one of these paths:
- **New project only**
- **New project + generate plug-in**
- **New project + generate plug-in + build**
- **New project + generate plug-in + build + first-time registration**
- **Existing project + update code + build**
- **Existing project + update code + build + push update**

### Step 5: Scaffold the project
If the project does not already exist:
1. Create the target folder if needed.
2. Change into the folder.
3. Run:
   - `pac plugin init --skip-signing`

If the user explicitly wants signing:
- use the relevant signing option instead of `--skip-signing`

After scaffolding:
- inspect the generated files
- identify the main plug-in class/template files
- identify the project file and output package locations

### Step 6: Generate or update the plug-in code
Translate the user's natural-language requirement into a Dataverse plug-in class.

The code generation must:
- use the correct class name and namespace
- align with the requested message/table/stage
- include clear tracing
- validate expected input parameters
- use organization services only when necessary
- avoid stateful fields
- keep helper methods small and understandable

When the request is ambiguous:
- ask only the minimum necessary questions:
  - which table?
  - which message?
  - which stage?
  - sync or async?
  - what business rule should run?

### Step 7: Build
Build the project/package.

Preferred behavior:
1. restore/build using the project's expected toolchain
2. inspect errors and warnings
3. fix compile errors
4. rebuild until successful
5. locate the built output package/assembly

If the build output is a plug-in package:
- identify the generated `.nupkg` or output package file

### Step 8: Deployment decision
#### Case A — First-time registration
If the plug-in/package is not yet registered:
- explain that first-time registration and step registration require Plug-in Registration Tool workflow
- run or instruct:
  - `pac tool prt`
- guide the user to:
  1. connect to the confirmed target environment
  2. import/register the generated NuGet package
  3. register the assembly/package
  4. register the step(s) with:
     - table
     - message
     - stage
     - mode
     - filtering attributes
     - images, if applicable

#### Case B — Update existing package
If `pluginId` is supplied:
- run:
  - `pac plugin push --pluginId <pluginId>`
- if the user specifies a particular environment, include the environment parameter
- use the correct build configuration if needed
- do not run this until the user has explicitly confirmed the target environment

### Step 9: Final summary
At the end, summarize:
- project path
- active/confirmed target environment
- generated class name(s)
- table/message/stage chosen
- build result
- package/assembly output location
- whether deployment was:
  - scaffold only
  - built only
  - first-time registration guided
  - updated via `pac plugin push`

## Safety / correctness constraints
- Do not claim a successful deployment unless the command or tool output confirms it.
- Do not attempt deployment if the build failed.
- Do not fabricate a `pluginId`.
- Do not assume the desired step registration values; ask when missing.
- Do not remove existing step registrations or packages unless the user explicitly asks.
- Do not change package identity/name/version assumptions casually when the project is already deployed.
- Do not proceed past environment validation without explicit user confirmation.

## Prompt examples

### Example 1
"Create a Dataverse plug-in project called AccountAuditPlugin. Add a plug-in that runs on account update in PreOperation and writes trace output when the account name changes."

### Example 2
"Scaffold a new plug-in package in ./plugins/LeadValidator and generate a synchronous Create plug-in for lead that blocks save when email is missing."

### Example 3
"Update my existing contact plug-in to create a task on contact create, rebuild it, and push the update using pluginId 11111111-2222-3333-4444-555555555555."

### Example 4
"Create a first version of a plug-in for opportunity update, build it, and guide me through first-time registration."

## Output style
When using this skill:
- be explicit about assumptions
- show the commands before running them when the action is sensitive
- clearly distinguish between:
  - project scaffolding
  - code generation
  - build
  - first-time registration
  - update deployment

If you are blocked by missing prerequisites, stop and tell the user exactly what is missing.
