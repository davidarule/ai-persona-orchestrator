#!/usr/bin/env python3
"""
Extract RACI patterns from workflows using actual persona types
"""

import yaml
import json
from pathlib import Path
from collections import defaultdict

# Group personas by their general function
PERSONA_GROUPS = {
    'developers': [
        'software-architect',
        'backend-developer',
        'frontend-developer',
        'mobile-developer',
        'developer-engineer',
        'ai-engineer'
    ],
    'qa-testers': [
        'qa-test-engineer',
        'test-engineer',
        'software-qa'
    ],
    'security': [
        'security-architect',
        'security-engineer',
        'devsecops-engineer'
    ],
    'operations': [
        'site-reliability-engineer',
        'cloud-engineer',
        'configuration-release-engineer',
        'integration-engineer'
    ],
    'management': [
        'engineering-manager',
        'product-owner',
        'scrum-master'
    ],
    'analysts': [
        'business-analyst',
        'requirements-analyst',
        'data-engineer-dba'
    ],
    'design': [
        'ui-ux-designer',
        'systems-architect',
        'technical-writer'
    ]
}

# Reverse mapping for quick lookup
PERSONA_TO_GROUP = {}
for group, personas in PERSONA_GROUPS.items():
    for persona in personas:
        PERSONA_TO_GROUP[persona] = group

def get_workflow_owner_persona(workflow):
    """Get the persona that owns this workflow"""
    persona_info = workflow.get('metadata', {}).get('persona_info', {})
    return persona_info.get('type', '')

def extract_phase_name(step):
    """Extract phase name from step"""
    step_id = step['id']
    step_name = step['name']
    
    # Group common phases
    if any(x in step_id.lower() for x in ['initialize', 'validate', 'analyze', 'check']):
        return 'INITIALIZATION'
    elif any(x in step_id.lower() for x in ['develop', 'implement', 'code', 'build']):
        return 'DEVELOPMENT'
    elif any(x in step_id.lower() for x in ['review', 'pr', 'pull-request']):
        return 'REVIEW'
    elif any(x in step_id.lower() for x in ['test', 'qa', 'verify']):
        return 'TESTING'
    elif any(x in step_id.lower() for x in ['merge', 'integrate']):
        return 'INTEGRATION'
    elif any(x in step_id.lower() for x in ['deploy', 'release']):
        return 'DEPLOYMENT'
    elif any(x in step_id.lower() for x in ['monitor', 'post']):
        return 'POST-DEPLOYMENT'
    else:
        return 'EXECUTION'

def determine_accountability(workflow_id, step, owner_persona):
    """Determine who is accountable for a step"""
    # For persona workflows, the persona owner is generally accountable
    if 'persona-' in workflow_id:
        # Check if this is a management decision
        if any(x in step.get('name', '').lower() for x in ['approve', 'decision', 'prioritize']):
            return 'engineering-manager'
        return owner_persona
    
    # For system workflows, determine by workflow type
    if 'feature' in workflow_id:
        return 'software-architect'
    elif 'bug' in workflow_id:
        return 'engineering-manager'
    elif 'hotfix' in workflow_id:
        return 'site-reliability-engineer'
    elif 'security' in workflow_id:
        return 'security-architect'
    else:
        return 'engineering-manager'

def extract_personas_from_step(step, owner_persona):
    """Extract persona involvement from a workflow step"""
    responsible = set()
    accountable = set()
    consulted = set()
    informed = set()
    
    # The owner persona is responsible by default for their own workflow steps
    if owner_persona:
        responsible.add(owner_persona)
    
    # Analyze Azure DevOps work item assignments
    if step.get('action') == 'azure-devops':
        for work_item in step.get('inputs', []):
            assigned_to = work_item.get('assignedTo', '')
            if assigned_to and assigned_to != owner_persona:
                # This persona is being assigned work, so they're responsible
                responsible.add(assigned_to)
                # The owner is consulting them
                if owner_persona:
                    consulted.add(assigned_to)
    
    # Analyze workflow delegations
    elif step.get('action') == 'execute-workflow':
        sub_workflow = step.get('workflow', '')
        # Determine which persona type would handle this workflow
        if 'pr' in sub_workflow or 'review' in sub_workflow:
            consulted.add('software-architect')
            consulted.add('qa-test-engineer')
        elif 'merge' in sub_workflow:
            consulted.add('configuration-release-engineer')
        elif 'monitor' in sub_workflow:
            consulted.add('site-reliability-engineer')
        elif 'security' in sub_workflow:
            consulted.add('security-architect')
        elif 'test' in sub_workflow:
            consulted.add('qa-test-engineer')
    
    # Analyze conditional branches for consultation patterns
    elif step.get('action') == 'conditional':
        branches = step.get('branches', [])
        for branch in branches:
            for sub_step in branch.get('steps', []):
                if sub_step.get('action') == 'azure-devops':
                    for work_item in sub_step.get('inputs', []):
                        assigned_to = work_item.get('assignedTo', '')
                        if assigned_to:
                            consulted.add(assigned_to)
    
    # Analyze error handling for escalation (informed)
    error_handling = step.get('errorHandling', {})
    on_failure = error_handling.get('onFailure', [])
    for failure_step in on_failure:
        command = failure_step.get('command', '')
        if 'alert' in command or 'notify' in command:
            if 'security' in command:
                informed.add('security-architect')
                informed.add('security-engineer')
            elif 'management' in command or 'leadership' in command:
                informed.add('engineering-manager')
                informed.add('product-owner')
            elif 'team' in command:
                informed.add('scrum-master')
    
    return responsible, accountable, consulted, informed

def extract_raci_from_workflow(workflow_path):
    """Extract RACI patterns using persona types"""
    with open(workflow_path, 'r') as f:
        workflow = yaml.safe_load(f)
    
    workflow_id = workflow['metadata']['id']
    workflow_name = workflow['metadata']['name']
    owner_persona = get_workflow_owner_persona(workflow)
    
    raci_patterns = []
    phases = defaultdict(list)
    
    # Process each step
    for step in workflow.get('steps', []):
        step_id = step['id']
        step_name = step['name']
        phase = extract_phase_name(step)
        
        # Extract RACI from step
        responsible, accountable_from_step, consulted, informed = extract_personas_from_step(step, owner_persona)
        
        # Determine accountability
        accountable = set()
        primary_accountable = determine_accountability(workflow_id, step, owner_persona)
        if primary_accountable:
            accountable.add(primary_accountable)
        accountable.update(accountable_from_step)
        
        # Also check error handling at workflow level
        workflow_error = workflow.get('errorHandling', {})
        for failure_step in workflow_error.get('onFailure', []):
            command = failure_step.get('command', '')
            if 'alert' in command or 'notify' in command:
                if 'security' in command:
                    informed.add('security-architect')
                elif 'management' in command:
                    informed.add('engineering-manager')
        
        # Create pattern
        pattern = {
            'workflow_id': workflow_id,
            'workflow_name': workflow_name,
            'owner_persona': owner_persona,
            'phase': phase,
            'phase_id': step_id,
            'task_type': step_name,
            'responsible': sorted(list(responsible)),
            'accountable': sorted(list(accountable)),
            'consulted': sorted(list(consulted)),
            'informed': sorted(list(informed))
        }
        
        phases[phase].append(pattern)
        raci_patterns.append(pattern)
    
    return raci_patterns, phases

def create_raci_summary_table(workflow_id, patterns, phases):
    """Create a summary table showing RACI by persona groups"""
    summary = []
    summary.append(f"\n{'='*100}")
    summary.append(f"RACI Matrix for: {workflow_id}")
    summary.append(f"{'='*100}\n")
    
    # Collect all personas involved
    all_personas = set()
    for pattern in patterns:
        all_personas.update(pattern['responsible'])
        all_personas.update(pattern['accountable'])
        all_personas.update(pattern['consulted'])
        all_personas.update(pattern['informed'])
    
    # Group by persona groups for display
    persona_columns = defaultdict(set)
    for persona in all_personas:
        group = PERSONA_TO_GROUP.get(persona, 'other')
        persona_columns[group].add(persona)
    
    # Display by phase
    for phase_name in ['INITIALIZATION', 'DEVELOPMENT', 'REVIEW', 'TESTING', 
                       'INTEGRATION', 'DEPLOYMENT', 'POST-DEPLOYMENT', 'EXECUTION']:
        if phase_name not in phases:
            continue
            
        summary.append(f"\n{phase_name} PHASE")
        summary.append("-" * 80)
        
        for pattern in phases[phase_name]:
            summary.append(f"\n{pattern['task_type']}:")
            
            # Show RACI by persona
            if pattern['responsible']:
                summary.append(f"  Responsible (R): {', '.join(pattern['responsible'])}")
            if pattern['accountable']:
                summary.append(f"  Accountable (A): {', '.join(pattern['accountable'])}")
            if pattern['consulted']:
                summary.append(f"  Consulted (C): {', '.join(pattern['consulted'])}")
            if pattern['informed']:
                summary.append(f"  Informed (I): {', '.join(pattern['informed'])}")
    
    return '\n'.join(summary)

def main():
    print("🔍 Extracting RACI patterns using persona types...\n")
    
    all_patterns = []
    workflow_summaries = {}
    
    # Process all workflows
    workflow_files = []
    workflow_files.extend(Path('workflows/system').glob('*.yaml'))
    workflow_files.extend(Path('workflows/personas').glob('*.yaml'))
    
    for workflow_path in workflow_files:
        print(f"Analyzing {workflow_path.name}...")
        try:
            patterns, phases = extract_raci_from_workflow(workflow_path)
            all_patterns.extend(patterns)
            
            workflow_id = patterns[0]['workflow_id'] if patterns else workflow_path.stem
            workflow_summaries[workflow_id] = {
                'file': str(workflow_path),
                'patterns': patterns,
                'phases': dict(phases),
                'persona_count': len(set(p for pattern in patterns 
                                       for p in pattern['responsible'] + pattern['accountable'] + 
                                       pattern['consulted'] + pattern['informed']))
            }
            
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
    
    # Save patterns
    with open('raci_patterns_personas.json', 'w') as f:
        json.dump(all_patterns, f, indent=2)
    
    # Save summaries
    with open('raci_summaries_personas.json', 'w') as f:
        json.dump(workflow_summaries, f, indent=2)
    
    print(f"\n✅ Extracted {len(all_patterns)} RACI patterns from {len(workflow_summaries)} workflows")
    
    # Show examples
    print("\n📊 Example RACI Patterns:\n")
    
    # Show feature development workflow
    if 'wf0-feature-development' in workflow_summaries:
        patterns = workflow_summaries['wf0-feature-development']['patterns']
        phases = workflow_summaries['wf0-feature-development']['phases']
        print(create_raci_summary_table('wf0-feature-development', patterns, phases))
    
    # Show statistics
    print("\n📈 RACI Statistics:")
    
    # Count persona involvement
    persona_counts = defaultdict(int)
    for pattern in all_patterns:
        for persona in pattern['responsible']:
            persona_counts[persona] += 1
        for persona in pattern['accountable']:
            persona_counts[persona] += 1
    
    print("\nMost involved personas:")
    for persona, count in sorted(persona_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        group = PERSONA_TO_GROUP.get(persona, 'other')
        print(f"  {persona} ({group}): {count} responsibilities")
    
    print("\n📄 Results saved to:")
    print("  - raci_patterns_personas.json")
    print("  - raci_summaries_personas.json")

if __name__ == "__main__":
    main()