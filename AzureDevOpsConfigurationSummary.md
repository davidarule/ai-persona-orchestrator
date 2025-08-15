# AI Persona Orchestrator - Phase 1 Configuration Summary
**Generated**: August 15, 2025  
**Location**: Australia East (Sydney)

## Resource Groups
- **Main**: rg-ai-persona-orchestrator
- **Dev**: rg-ai-persona-dev  
- **Staging**: rg-ai-persona-staging
- **Prod**: rg-ai-persona-prod

## Key Vaults (RBAC-enabled)
- **Dev**: kv-aip-dev-1755223521
- **Staging**: kv-aip-stg-1755223521
- **Prod**: kv-aip-prod-1755223521

## Container Registry
- **Name**: acrpersona0815
- **Login Server**: acrpersona0815.azurecr.io
- **Username**: acrpersona0815
- **SKU**: Basic

## Log Analytics Workspace
- **Name**: law-ai-persona-dev
- **Workspace ID**: c61d7341-2f39-46b4-bebe-24827b855e93

## Container Apps Environment
- **Dev**: cae-ai-persona-dev

## Application Insights
- **Name**: ai-persona-dev
- **Instrumentation Key**: [Check in azure-config-phase1.txt]

## Storage Account
- **Dev**: [Check in azure-config-phase1.txt]

## Managed Identity
- **Name**: mi-ai-persona-dev
- **Principal ID**: cd21bea1-0713-4210-bfe8-728c18d4d0c2
- **Permissions**: 
  - Key Vault Secrets User (on kv-aip-dev-1755223521)

## Your User Permissions
- **Principal ID**: 9e93ba93-0bae-4931-8394-8a43e4f6eb06
- **Key Vault Role**: Key Vault Administrator (on kv-aip-dev-1755223521)

## Important Notes
1. Key Vaults are using RBAC authorization (not access policies)
2. Container Registry is using Basic SKU (can upgrade to Standard later if needed)
3. All resources are in Australia East region
4. Your user has Key Vault Administrator role for managing secrets

## Next Steps for Phase 2
1. Migrate repository from GitHub to Azure DevOps
2. Create service connections in Azure DevOps
3. Set up variable groups with these resource names
4. Configure CI/CD pipelines
5. Add secrets to Key Vault

## Commands to Verify Setup
```bash
# List all resources
az resource list --resource-group rg-ai-persona-dev --output table

# Test ACR login
az acr login --name acrpersona0815

# List Key Vault secrets (once added)
az keyvault secret list --vault-name kv-aip-dev-1755223521

# View Container Apps Environment
az containerapp env show --name cae-ai-persona-dev --resource-group rg-ai-persona-dev
```
