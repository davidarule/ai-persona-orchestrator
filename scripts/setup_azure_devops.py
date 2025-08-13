import os
import sys
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication
from azure.devops.v7_0.build.models import BuildDefinition, BuildDefinitionVariable
import yaml

def setup_azure_devops():
    """Configure Azure DevOps integration"""
    
    # Get credentials
    organization_url = input("Enter Azure DevOps Organization URL: ")
    pat = input("Enter Personal Access Token (PAT): ")
    
    # Create connection
    credentials = BasicAuthentication('', pat)
    connection = Connection(base_url=organization_url, creds=credentials)
    
    # Get clients
    build_client = connection.clients.get_build_client()
    git_client = connection.clients.get_git_client()
    work_item_client = connection.clients.get_work_item_tracking_client()
    
    # Create service hooks for real-time updates
    service_hooks_client = connection.clients.get_service_hooks_client()
    
    # Create webhook for work item updates
    webhook_subscription = {
        "publisherId": "tfs",
        "eventType": "workitem.updated",
        "consumerId": "webHooks",
        "consumerActionId": "httpRequest",
        "publisherInputs": {
            "areaPath": "",
            "workItemType": ""
        },
        "consumerInputs": {
            "url": "https://your-server/api/webhooks/azure-devops"
        }
    }
    
    # Store configuration
    config = {
        "organization_url": organization_url,
        "pat": pat,
        "webhook_url": "https://your-server/api/webhooks/azure-devops"
    }
    
    with open('.env.d/azure_devops.env', 'w') as f:
        f.write(f"AZURE_DEVOPS_ORG_URL={organization_url}\n")
        f.write(f"AZURE_DEVOPS_PAT={pat}\n")
    
    print("✅ Azure DevOps integration configured successfully!")

if __name__ == "__main__":
    setup_azure_devops()