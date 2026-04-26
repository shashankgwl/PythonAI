param(
    [int]$Port = 8081,
    [string]$ConfigPath = ".\config.azure-openai.yaml"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$venvMagentic = Join-Path $projectRoot ".venv\Scripts\magentic-ui.exe"
$runtimeConfigPath = Join-Path $projectRoot ".runtime.config.azure-openai.yaml"

if (!(Test-Path $venvPython)) {
    throw "Virtual environment not found at .venv. Create it first."
}

$envFile = Join-Path $projectRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -match '^\s*$') {
            return
        }

        $parts = $_ -split '=', 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
        }
    }
}

$requiredEnvVars = @(
    "AZURE_OPENAI_API_KEY"
)

$missingEnvVars = $requiredEnvVars | Where-Object { -not [System.Environment]::GetEnvironmentVariable($_) }
if ($missingEnvVars.Count -gt 0) {
    throw "Missing required environment variables: $($missingEnvVars -join ', ')"
}

function Get-EnvValue {
    param([string]$Name)

    $value = [System.Environment]::GetEnvironmentVariable($Name)
    if ($null -eq $value) {
        return ""
    }

    return $value
}

$configTemplate = Get-Content (Join-Path $projectRoot $ConfigPath) -Raw
$renderedConfig = $configTemplate
$renderedConfig = $renderedConfig.Replace("__AZURE_OPENAI_ENDPOINT__", (Get-EnvValue "AZURE_OPENAI_ENDPOINT"))
$renderedConfig = $renderedConfig.Replace("__AZURE_OPENAI_DEPLOYMENT__", (Get-EnvValue "AZURE_OPENAI_DEPLOYMENT"))
$renderedConfig = $renderedConfig.Replace("__AZURE_OPENAI_MODEL__", (Get-EnvValue "AZURE_OPENAI_MODEL"))
$renderedConfig = $renderedConfig.Replace("__AZURE_OPENAI_API_VERSION__", (Get-EnvValue "AZURE_OPENAI_API_VERSION"))
$renderedConfig = $renderedConfig.Replace("__AZURE_OPENAI_API_KEY__", (Get-EnvValue "AZURE_OPENAI_API_KEY"))

$renderedConfig | Set-Content -Path $runtimeConfigPath -Encoding utf8

if (!(Test-Path $venvMagentic)) {
    & $venvPython -m magentic_ui --port $Port --config $runtimeConfigPath
    exit $LASTEXITCODE
}

& $venvMagentic --port $Port --config $runtimeConfigPath
exit $LASTEXITCODE
