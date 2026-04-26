# MagenticUI Local Setup

This folder is prepared to run `magentic-ui` with a local virtual environment and a YAML model client config that points to Azure instead of the default OpenAI API key flow.

## Files

- `config.azure-openai.yaml`: safe template AutoGen model-client config for Azure OpenAI style deployments.
- `.env.azure.example`: example environment values to copy into `.env`.
- `Start-MagenticUI.ps1`: PowerShell launcher that loads `.env` and starts Magentic-UI with the Azure config.

## Expected Azure Values

Use the Azure OpenAI style endpoint and deployment details for the model you created in Azure AI Foundry.

- `AZURE_OPENAI_ENDPOINT`: usually `https://<resource>.openai.azure.com/`
- `AZURE_OPENAI_DEPLOYMENT`: your deployment name in Azure
- `AZURE_OPENAI_MODEL`: model family behind that deployment, such as `gpt-4o`
- `AZURE_OPENAI_API_VERSION`: API version supported by your deployment
- `AZURE_OPENAI_API_KEY`: only needed if you are using key-based auth

## Run Flow

1. Create a `.env` file from `.env.azure.example`.
2. Copy `.env.azure.example` to `.env` and fill in your real endpoint and deployment values there.
3. Create and populate `.venv`.
4. Start Docker.
5. Run `.\Start-MagenticUI.ps1`

## Notes

- The upstream Magentic-UI docs recommend WSL2 on Windows for the most reliable Docker and path behavior.
- This starter config uses `AzureOpenAIChatCompletionClient`, which matches Azure OpenAI deployments hosted through Azure AI Foundry.
- `Start-MagenticUI.ps1` renders a local `.runtime.config.azure-openai.yaml` at launch time so secrets do not need to live in the checked-in template.
