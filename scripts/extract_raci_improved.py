#!/usr/bin/env python3
"""
Improved RACI extraction from workflows with better role mapping
"""

import yaml
import json
from pathlib import Path
from collections import defaultdict

# Define standard roles that should appear in RACI matrices
STANDARD_ROLES = {
    # Human/AI Roles
    'developer': 'Developer',
    'tech-lead': 'Tech Lead',
    'code-reviewer': 'Code Reviewer',
    'product-owner': 'Product Owner',
    'qa-engineer': 'QA Engineer',
    'security-architect': 'Security Architect',
    'devops-engineer': 'DevOps Engineer',
    'monitoring-team': 'Monitoring Team',
    'management': 'Management',
    
    # System/Tool Roles
    'workflow-system': 'Workflow System',
    'azure-devops': 'Azure DevOps',
    'git-repository': 'Git Repository',
    'ci-cd-pipeline': 'CI/CD Pipeline',
    'monitoring-system': 'Monitoring System'
}

# Map workflow types to default responsible parties
WORKFLOW_TYPE_DEFAULTS = {
    'feature': {
        'responsible': ['developer'],
        'accountable': ['tech-lead'],
        'consulted': ['product-owner'],
        'informed': ['monitoring-team']
    },
    'bug': {
        'responsible': ['developer'],
        'accountable': ['tech-lead'],
        'consulted': ['qa-engineer'],
        'informed': ['product-owner']
    },
    'hotfix': {
        'responsible': ['devops-engineer', 'developer'],
        'accountable': ['tech-lead'],
        'consulted': ['security-architect'],
        'informed': ['management', 'monitoring-team']
    },
    'pr': {
        'responsible': ['code-reviewer'],
        'accountable': ['tech-lead'],
        'consulted': ['developer'],
        'informed': ['product-owner']
    }
}

def determine_workflow_type(workflow_id, workflow_name):
    """Determine the type of workflow"""
    if 'feature' in workflow_id.lower():
        return 'feature'
    elif 'bug' in workflow_id.lower():
        return 'bug'
    elif 'hotfix' in workflow_id.lower():
        return 'hotfix'
    elif 'pull-request' in workflow_id.lower() or 'pr' in workflow_id.lower():
        return 'pr'
    else:
        return 'general'

def extract_phase_name(step):
    """Extract phase name from step"""
    step_id = step['id']
    step_name = step['name']
    
    # Group common phases
    if any(x in step_id for x in ['initialize', 'validate', 'check']):
        return 'INITIALIZATION'
    elif any(x in step_id for x in ['develop', 'implement', 'code']):
        return 'DEVELOPMENT'
    elif any(x in step_id for x in ['review', 'pr', 'pull-request']):
        return 'REVIEW'
    elif any(x in step_id for x in ['test', 'qa', 'verify']):
        return 'TESTING'
    elif any(x in step_id for x in ['merge', 'integrate']):
        return 'INTEGRATION'
    elif any(x in step_id for x in ['deploy', 'release']):
        return 'DEPLOYMENT'
    elif any(x in step_id for x in ['monitor', 'post']):
        return 'POST-DEPLOYMENT'
    else:
        return 'EXECUTION'

def extract_improved_raci(workflow_path):
    """Extract RACI with improved role mapping"""
    with open(workflow_path, 'r') as f:
        workflow = yaml.safe_load(f)
    
    workflow_id = workflow['metadata']['id']
    workflow_name = workflow['metadata']['name']
    workflow_type = determine_workflow_type(workflow_id, workflow_name)
    
    # Get default RACI for this workflow type
    defaults = WORKFLOW_TYPE_DEFAULTS.get(workflow_type, {})
    
    raci_patterns = []
    phases = defaultdict(list)
    
    for step in workflow.get('steps', []):
        step_id = step['id']
        step_name = step['name']
        phase = extract_phase_name(step)
        
        # Start with defaults
        responsible = defaults.get('responsible', ['workflow-system']).copy()
        accountable = defaults.get('accountable', ['tech-lead']).copy()
        consulted = defaults.get('consulted', []).copy()
        informed = defaults.get('informed', []).copy()
        
        # Analyze step action to refine RACI
        action = step.get('action', '')
        
        if action == 'azure-devops':
            responsible.append('azure-devops')
            operation = step.get('operation', '')
            
            if operation == 'create-work-items':
                # Extract assigned personas
                for work_item in step.get('inputs', []):
                    assigned_to = work_item.get('assignedTo', '')
                    if assigned_to:
                        # Map persona type to role
                        if 'engineer' in assigned_to:
                            responsible.append('developer')
                        elif 'qa' in assigned_to or 'test' in assigned_to:
                            responsible.append('qa-engineer')
                        elif 'security' in assigned_to:
                            consulted.append('security-architect')
                        elif 'devops' in assigned_to:
                            responsible.append('devops-engineer')
                            
        elif action == 'git-operation':
            responsible.append('git-repository')
            operation = step.get('operation', '')
            if 'branch' in operation:
                responsible.append('developer')
            elif 'commit' in operation:
                responsible.append('developer')
            elif 'push' in operation:
                responsible.append('developer')
                informed.append('ci-cd-pipeline')
                
        elif action == 'execute-workflow':
            sub_workflow = step.get('workflow', '')
            responsible.append('workflow-system')
            
            # Map sub-workflows to roles
            if 'pr' in sub_workflow or 'pull-request' in sub_workflow:
                consulted.append('code-reviewer')
            elif 'merge' in sub_workflow:
                responsible.append('developer')
                accountable.append('tech-lead')
            elif 'monitor' in sub_workflow:
                responsible.append('monitoring-system')
                informed.append('monitoring-team')
                
        elif action == 'shell-command':
            command = step.get('command', '')
            if 'test' in command or 'validate' in command:
                responsible.append('ci-cd-pipeline')
                consulted.append('qa-engineer')
            elif 'deploy' in command:
                responsible.append('devops-engineer')
                informed.append('monitoring-team')
                
        # Remove duplicates and clean up
        responsible = list(set(responsible))
        accountable = list(set(accountable))
        consulted = list(set(consulted))
        informed = list(set(informed))
        
        pattern = {
            'workflow_id': workflow_id,
            'workflow_name': workflow_name,
            'phase': phase,
            'phase_id': step_id,
            'task_type': step_name,
            'responsible': responsible,
            'accountable': accountable,
            'consulted': consulted,
            'informed': informed
        }
        
        phases[phase].append(pattern)
        raci_patterns.append(pattern)
    
    # Add phase grouping to patterns
    for pattern in raci_patterns:
        pattern['phase_activities'] = len(phases[pattern['phase']])
    
    return raci_patterns, phases

def generate_raci_html_preview(workflow_id, patterns, phases):
    """Generate a simple text preview of the RACI matrix"""
    lines = []
    lines.append(f"\n{'='*80}")
    lines.append(f"RACI Matrix for: {workflow_id}")
    lines.append(f"{'='*80}\n")
    
    # Define columns
    all_roles = set()
    for pattern in patterns:
        all_roles.update(pattern['responsible'])
        all_roles.update(pattern['accountable'])
        all_roles.update(pattern['consulted'])
        all_roles.update(pattern['informed'])
    
    # Map to display names
    role_columns = []
    for role in sorted(all_roles):
        display_name = STANDARD_ROLES.get(role, role.replace('-', ' ').title())
        role_columns.append((role, display_name))
    
    # Print by phase
    for phase_name, phase_patterns in phases.items():
        lines.append(f"\n{phase_name} PHASE")
        lines.append("-" * 40)
        
        for pattern in phase_patterns:
            lines.append(f"\n{pattern['task_type']}:")
            
            raci_line = []
            for role, display in role_columns:
                markers = []
                if role in pattern['responsible']:
                    markers.append('R')
                if role in pattern['accountable']:
                    markers.append('A')
                if role in pattern['consulted']:
                    markers.append('C')
                if role in pattern['informed']:
                    markers.append('I')
                
                if markers:
                    raci_line.append(f"  {display}: {','.join(markers)}")
            
            lines.extend(raci_line)
    
    return '\n'.join(lines)

def main():
    print("🔍 Extracting improved RACI patterns from workflows...\n")
    
    all_patterns = []
    workflow_summaries = {}
    
    # Process a few key workflows for comparison
    key_workflows = [
        'workflows/system/wf0-feature-development.yaml',
        'workflows/system/wf1-bug-fix.yaml',
        'workflows/system/wf2-hotfix.yaml',
        'workflows/personas/persona-software-architect-workflow.yaml'
    ]
    
    for workflow_path in key_workflows:
        if Path(workflow_path).exists():
            print(f"Analyzing {Path(workflow_path).name}...")
            try:
                patterns, phases = extract_improved_raci(workflow_path)
                all_patterns.extend(patterns)
                
                workflow_id = patterns[0]['workflow_id'] if patterns else 'unknown'
                workflow_summaries[workflow_id] = {
                    'patterns': patterns,
                    'phases': dict(phases),
                    'preview': generate_raci_html_preview(workflow_id, patterns, phases)
                }
                
            except Exception as e:
                print(f"  ⚠️  Error: {e}")
    
    # Save improved patterns
    with open('raci_patterns_improved.json', 'w') as f:
        json.dump(all_patterns, f, indent=2)
    
    # Save summaries
    with open('raci_summaries_improved.json', 'w') as f:
        json.dump(workflow_summaries, f, indent=2)
    
    print(f"\n✅ Extracted {len(all_patterns)} improved RACI patterns")
    
    # Show preview for feature development workflow
    if 'wf0-feature-development' in workflow_summaries:
        print(workflow_summaries['wf0-feature-development']['preview'])
    
    print("\n📄 Results saved to:")
    print("  - raci_patterns_improved.json")
    print("  - raci_summaries_improved.json")

if __name__ == "__main__":
    main()