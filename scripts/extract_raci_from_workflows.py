#!/usr/bin/env python3
"""
Extract RACI patterns from workflow YAML files
"""

import yaml
import json
from pathlib import Path
from collections import defaultdict

def extract_raci_from_workflow(workflow_path):
    """Extract RACI patterns from a single workflow"""
    with open(workflow_path, 'r') as f:
        workflow = yaml.safe_load(f)
    
    workflow_id = workflow['metadata']['id']
    workflow_name = workflow['metadata']['name']
    
    raci_patterns = []
    
    # Analyze each step to extract RACI patterns
    for step in workflow.get('steps', []):
        step_id = step['id']
        step_name = step['name']
        
        # Determine responsible parties based on action type
        responsible = []
        accountable = []
        consulted = []
        informed = []
        
        # Azure DevOps operations show responsibility
        if step.get('action') == 'azure-devops':
            operation = step.get('operation')
            if operation == 'create-work-items':
                # Extract assigned personas from work items
                for work_item in step.get('inputs', []):
                    assigned_to = work_item.get('assignedTo')
                    if assigned_to:
                        responsible.append(assigned_to)
                        
        # Execute workflow shows delegation/consultation
        elif step.get('action') == 'execute-workflow':
            sub_workflow = step.get('workflow')
            consulted.append(f"workflow:{sub_workflow}")
            
        # Conditional branches show decision points
        elif step.get('action') == 'conditional':
            # The workflow executor is responsible for decisions
            responsible.append('current-executor')
            
            # Look for sub-steps that might indicate consultation
            branches = step.get('branches', [])
            for branch in branches:
                for sub_step in branch.get('steps', []):
                    if sub_step.get('action') == 'execute-workflow':
                        consulted.append(f"workflow:{sub_step.get('workflow')}")
                    elif sub_step.get('action') == 'azure-devops':
                        for work_item in sub_step.get('inputs', []):
                            assigned_to = work_item.get('assignedTo')
                            if assigned_to:
                                informed.append(assigned_to)
        
        # Shell commands indicate direct responsibility
        elif step.get('action') == 'shell-command':
            responsible.append('current-executor')
        
        # Error handling shows escalation patterns
        error_handling = workflow.get('errorHandling', {})
        on_failure = error_handling.get('onFailure', [])
        for failure_step in on_failure:
            if 'alert' in failure_step.get('command', ''):
                # Extract who gets alerted
                if 'security_team' in failure_step.get('command', ''):
                    informed.append('security-team')
                elif 'security_leadership' in failure_step.get('command', ''):
                    informed.append('security-leadership')
                elif 'management' in failure_step.get('command', ''):
                    informed.append('management')
        
        if responsible or accountable or consulted or informed:
            raci_patterns.append({
                'workflow_id': workflow_id,
                'workflow_name': workflow_name,
                'phase': step_id,
                'task_type': step_name,
                'responsible': list(set(responsible)),
                'accountable': list(set(accountable)),
                'consulted': list(set(consulted)),
                'informed': list(set(informed))
            })
    
    # Also extract from metadata if available
    persona_info = workflow['metadata'].get('persona_info', {})
    if persona_info:
        # The persona type is responsible for their own workflow
        persona_type = persona_info.get('type')
        if persona_type and raci_patterns:
            # Update the first pattern to show persona ownership
            raci_patterns[0]['responsible'] = [persona_type] + raci_patterns[0]['responsible']
    
    return raci_patterns

def analyze_all_workflows():
    """Analyze all workflows and extract RACI patterns"""
    all_patterns = []
    
    # Process system workflows
    system_workflow_dir = Path('workflows/system')
    for workflow_file in system_workflow_dir.glob('*.yaml'):
        print(f"Analyzing {workflow_file.name}...")
        try:
            patterns = extract_raci_from_workflow(workflow_file)
            all_patterns.extend(patterns)
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
    
    # Process persona workflows
    persona_workflow_dir = Path('workflows/personas')
    for workflow_file in persona_workflow_dir.glob('*.yaml'):
        print(f"Analyzing {workflow_file.name}...")
        try:
            patterns = extract_raci_from_workflow(workflow_file)
            all_patterns.extend(patterns)
        except Exception as e:
            print(f"  ⚠️  Error: {e}")
    
    return all_patterns

def generate_raci_summary(patterns):
    """Generate summary of RACI patterns"""
    summary = defaultdict(lambda: {
        'phases': set(),
        'responsible': set(),
        'accountable': set(),
        'consulted': set(),
        'informed': set()
    })
    
    for pattern in patterns:
        workflow_id = pattern['workflow_id']
        summary[workflow_id]['phases'].add(pattern['phase'])
        summary[workflow_id]['responsible'].update(pattern['responsible'])
        summary[workflow_id]['accountable'].update(pattern['accountable'])
        summary[workflow_id]['consulted'].update(pattern['consulted'])
        summary[workflow_id]['informed'].update(pattern['informed'])
    
    # Convert sets to lists for JSON serialization
    for workflow_id in summary:
        for key in ['phases', 'responsible', 'accountable', 'consulted', 'informed']:
            summary[workflow_id][key] = sorted(list(summary[workflow_id][key]))
    
    return dict(summary)

def main():
    print("🔍 Extracting RACI patterns from workflows...\n")
    
    # Extract patterns
    patterns = analyze_all_workflows()
    
    # Save detailed patterns
    with open('raci_patterns_extracted.json', 'w') as f:
        json.dump(patterns, f, indent=2)
    
    print(f"\n✅ Extracted {len(patterns)} RACI patterns")
    
    # Generate summary
    summary = generate_raci_summary(patterns)
    
    # Save summary
    with open('raci_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)
    
    print("\n📊 RACI Summary by Workflow:")
    for workflow_id, data in sorted(summary.items())[:5]:  # Show first 5
        print(f"\n{workflow_id}:")
        print(f"  Phases: {len(data['phases'])}")
        print(f"  Responsible: {', '.join(data['responsible'][:3])}...")
        print(f"  Consulted: {', '.join(data['consulted'][:3])}...")
        print(f"  Informed: {', '.join(data['informed'][:3])}...")
    
    print("\n📄 Full results saved to:")
    print("  - raci_patterns_extracted.json (detailed)")
    print("  - raci_summary.json (summary)")
    
    # Look for specific patterns
    print("\n🔍 Key RACI Patterns Found:")
    
    # Find workflows with multiple responsible parties
    multi_responsible = [p for p in patterns if len(p['responsible']) > 1]
    if multi_responsible:
        print(f"\n  Multi-party responsibility: {len(multi_responsible)} cases")
        print(f"    Example: {multi_responsible[0]['workflow_id']} - {multi_responsible[0]['phase']}")
    
    # Find escalation patterns
    escalations = [p for p in patterns if any('management' in i or 'leadership' in i for i in p['informed'])]
    if escalations:
        print(f"\n  Escalation patterns: {len(escalations)} cases")
        print(f"    Example: {escalations[0]['workflow_id']} - {escalations[0]['informed']}")
    
    # Find consultation patterns
    consultations = [p for p in patterns if p['consulted']]
    if consultations:
        print(f"\n  Consultation patterns: {len(consultations)} cases")
        print(f"    Example: {consultations[0]['workflow_id']} - {consultations[0]['consulted']}")

if __name__ == "__main__":
    main()