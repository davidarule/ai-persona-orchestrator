#!/bin/bash

echo "==================================="
echo "Azure AI Persona Orchestrator - Phase 1 Setup"
echo "Location: Australia East (Sydney)"
echo "==================================="

# Set variables
LOCATION="australiaeast"
RG_MAIN="rg-ai-persona-orchestrator"
RG_DEV="rg-ai-persona-dev"
RG_STAGING="rg-ai-persona-staging"
RG_PROD="rg-ai-persona-prod"

# Phase 1.0: Register Required Resource Providers
echo ""
echo "Phase 1.0: Registering Azure Resource Providers..."
echo "================================================"

az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.Insights
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.ManagedIdentity
az provider register --namespace Microsoft.Storage
az provider register --namespace Microsoft.Web

echo "Waiting for providers to register (this takes 1-3 minutes)..."
sleep 30

# Check registration status
echo ""
echo "Provider Registration Status:"
az provider list --query "[?namespace=='Microsoft.ContainerRegistry' || namespace=='Microsoft.App' || namespace=='Microsoft.OperationalInsights' || namespace=='Microsoft.Insights' || namespace=='Microsoft.KeyVault' || namespace=='Microsoft.ManagedIdentity'].{Provider:namespace, Status:registrationState}" --output table

# Wait a bit more if needed
sleep 30

# Phase 1.1: Create Resource Groups
echo ""
echo "Phase 1.1: Creating Resource Groups..."
echo "====================================="

az group create --name $RG_MAIN --location $LOCATION
az group create --name $RG_DEV --location $LOCATION
az group create --name $RG_STAGING --location $LOCATION
az group create --name $RG_PROD --location $LOCATION

# Phase 1.2: Create Azure Key Vaults
echo ""
echo "Phase 1.2: Creating Key Vaults..."
echo "================================"

# Generate unique Key Vault names (they must be globally unique)
KV_DEV="kv-aip-dev-$(date +%s)"
KV_STAGING="kv-aip-stg-$(date +%s)"
KV_PROD="kv-aip-prod-$(date +%s)"

echo "Creating Key Vault: $KV_DEV"
az keyvault create \
  --name $KV_DEV \
  --resource-group $RG_DEV \
  --location $LOCATION \
  --enable-rbac-authorization

echo "Creating Key Vault: $KV_STAGING"
az keyvault create \
  --name $KV_STAGING \
  --resource-group $RG_STAGING \
  --location $LOCATION \
  --enable-rbac-authorization

echo "Creating Key Vault: $KV_PROD"
az keyvault create \
  --name $KV_PROD \
  --resource-group $RG_PROD \
  --location $LOCATION \
  --enable-rbac-authorization

# Save Key Vault names for later use
echo ""
echo "Key Vault Names (save these!):"
echo "Dev: $KV_DEV"
echo "Staging: $KV_STAGING"
echo "Prod: $KV_PROD"

# Phase 1.3: Create Azure Container Registry
echo ""
echo "Phase 1.3: Creating Container Registry..."
echo "========================================"

# Generate unique ACR name (must be globally unique)
ACR_NAME="acraipersona$(date +%s)"

az acr create \
  --resource-group $RG_MAIN \
  --name $ACR_NAME \
  --sku Standard \
  --location $LOCATION \
  --admin-enabled true

# Get ACR credentials
ACR_USERNAME=$(az acr credential show --name $ACR_NAME --query username -o tsv)
ACR_PASSWORD=$(az acr credential show --name $ACR_NAME --query passwords[0].value -o tsv)
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --query loginServer -o tsv)

echo ""
echo "ACR Details (save these!):"
echo "Name: $ACR_NAME"
echo "Login Server: $ACR_LOGIN_SERVER"
echo "Username: $ACR_USERNAME"
echo "Password: [hidden - see Azure Portal]"

# Phase 1.4: Create Log Analytics Workspace
echo ""
echo "Phase 1.4: Creating Log Analytics Workspace..."
echo "============================================="

LAW_DEV="law-ai-persona-dev"

az monitor log-analytics workspace create \
  --resource-group $RG_DEV \
  --workspace-name $LAW_DEV \
  --location $LOCATION

# Get workspace details
WORKSPACE_ID=$(az monitor log-analytics workspace show \
  --resource-group $RG_DEV \
  --workspace-name $LAW_DEV \
  --query customerId --output tsv)

WORKSPACE_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group $RG_DEV \
  --workspace-name $LAW_DEV \
  --query primarySharedKey --output tsv)

echo "Log Analytics Workspace created"
echo "Workspace ID: $WORKSPACE_ID"

# Phase 1.5: Create Container Apps Environment
echo ""
echo "Phase 1.5: Creating Container Apps Environment..."
echo "==============================================="

CAE_DEV="cae-ai-persona-dev"

az containerapp env create \
  --name $CAE_DEV \
  --resource-group $RG_DEV \
  --location $LOCATION \
  --logs-workspace-id $WORKSPACE_ID \
  --logs-workspace-key $WORKSPACE_KEY

echo "Container Apps Environment created: $CAE_DEV"

# Phase 1.6: Create Application Insights
echo ""
echo "Phase 1.6: Creating Application Insights..."
echo "========================================="

AI_DEV="ai-persona-dev"

az monitor app-insights component create \
  --app $AI_DEV \
  --location $LOCATION \
  --resource-group $RG_DEV \
  --application-type web

# Get Application Insights key
APP_INSIGHTS_KEY=$(az monitor app-insights component show \
  --app $AI_DEV \
  --resource-group $RG_DEV \
  --query instrumentationKey -o tsv)

echo "Application Insights created"
echo "Instrumentation Key: $APP_INSIGHTS_KEY"

# Phase 1.7: Create Storage Account
echo ""
echo "Phase 1.7: Creating Storage Account..."
echo "====================================="

# Generate unique storage account name
STORAGE_DEV="staipersona$(date +%s)"

az storage account create \
  --name $STORAGE_DEV \
  --resource-group $RG_DEV \
  --location $LOCATION \
  --sku Standard_LRS

echo "Storage Account created: $STORAGE_DEV"

# Phase 1.8: Create Managed Identities
echo ""
echo "Phase 1.8: Creating Managed Identities..."
echo "========================================"

MI_DEV="mi-ai-persona-dev"

az identity create \
  --name $MI_DEV \
  --resource-group $RG_DEV \
  --location $LOCATION

IDENTITY_CLIENT_ID=$(az identity show \
  --name $MI_DEV \
  --resource-group $RG_DEV \
  --query clientId -o tsv)

IDENTITY_OBJECT_ID=$(az identity show \
  --name $MI_DEV \
  --resource-group $RG_DEV \
  --query principalId -o tsv)

echo "Managed Identity created"
echo "Client ID: $IDENTITY_CLIENT_ID"

# Phase 1.9: Grant Key Vault Access to Managed Identity
echo ""
echo "Phase 1.9: Configuring Key Vault Access..."
echo "========================================="

az keyvault set-policy \
  --name $KV_DEV \
  --object-id $IDENTITY_OBJECT_ID \
  --secret-permissions get list

echo "Key Vault access granted to Managed Identity"

# Summary
echo ""
echo "==========================================="
echo "Phase 1 Complete! Azure Infrastructure Created"
echo "==========================================="
echo ""
echo "IMPORTANT - Save these values for Phase 2:"
echo ""
echo "Resource Groups:"
echo "  Main: $RG_MAIN"
echo "  Dev: $RG_DEV"
echo "  Staging: $RG_STAGING"
echo "  Prod: $RG_PROD"
echo ""
echo "Key Vaults:"
echo "  Dev: $KV_DEV"
echo "  Staging: $KV_STAGING"
echo "  Prod: $KV_PROD"
echo ""
echo "Container Registry:"
echo "  Name: $ACR_NAME"
echo "  Login Server: $ACR_LOGIN_SERVER"
echo "  Username: $ACR_USERNAME"
echo ""
echo "Container Apps Environment:"
echo "  Dev: $CAE_DEV"
echo ""
echo "Application Insights:"
echo "  Key: $APP_INSIGHTS_KEY"
echo ""
echo "Storage Account:"
echo "  Dev: $STORAGE_DEV"
echo ""
echo "Managed Identity:"
echo "  Name: $MI_DEV"
echo "  Client ID: $IDENTITY_CLIENT_ID"
echo ""
echo "Next step: Save these values and proceed to Phase 2!"

# Save values to a file for reference
echo "Saving configuration to: azure-config-phase1.txt"
cat > azure-config-phase1.txt << EOF
Azure AI Persona Orchestrator - Phase 1 Configuration
Generated: $(date)
Location: $LOCATION

Resource Groups:
  Main: $RG_MAIN
  Dev: $RG_DEV
  Staging: $RG_STAGING
  Prod: $RG_PROD

Key Vaults:
  Dev: $KV_DEV
  Staging: $KV_STAGING
  Prod: $KV_PROD

Container Registry:
  Name: $ACR_NAME
  Login Server: $ACR_LOGIN_SERVER
  Username: $ACR_USERNAME

Container Apps Environment:
  Dev: $CAE_DEV

Application Insights:
  Name: $AI_DEV
  Key: $APP_INSIGHTS_KEY

Storage Account:
  Dev: $STORAGE_DEV

Managed Identity:
  Name: $MI_DEV
  Client ID: $IDENTITY_CLIENT_ID
  Object ID: $IDENTITY_OBJECT_ID

Log Analytics:
  Workspace: $LAW_DEV
  Workspace ID: $WORKSPACE_ID
EOF

echo "Configuration saved to azure-config-phase1.txt"
