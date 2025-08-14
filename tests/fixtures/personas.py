"""
Test fixtures for persona data
"""

# Complete test persona data matching Azure DevOps sandbox
TEST_PERSONAS = [
    {
        "username": "steve.bot",
        "email": "steve.bot@insitec.com.au",
        "first_name": "Steve",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "System Architect",
        "description": "System design and technical architecture, including security",
        "persona_type": "systems-architect",
        "skills": ["System Architecture", "Security Architecture", "Technical Leadership"]
    },
    {
        "username": "jordan.bot",
        "email": "jordan.bot@insitec.com.au",
        "first_name": "Jordan",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Backend Developer",
        "description": "Backend implementation",
        "persona_type": "backend-developer",
        "skills": ["Python", "Java", "Database Design", "API Development"]
    },
    {
        "username": "matt.bot",
        "email": "matt.bot@insitec.com.au",
        "first_name": "Matt",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Frontend Developer",
        "description": "Frontend implementation",
        "persona_type": "frontend-developer",
        "skills": ["React", "Angular", "Vue.js", "UI Development"]
    },
    {
        "username": "kav.bot",
        "email": "kav.bot@insitec.com.au",
        "first_name": "Kav",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Test Engineer",
        "description": "Quality assurance and test planning",
        "persona_type": "test-engineer",
        "skills": ["Test Automation", "Performance Testing", "Test Planning"]
    },
    {
        "username": "dave.bot",
        "email": "dave.bot@insitec.com.au",
        "first_name": "Dave",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Security Engineer",
        "description": "Security specific implementation guidance",
        "persona_type": "security-engineer",
        "skills": ["Security Testing", "Vulnerability Assessment", "Security Implementation"]
    },
    {
        "username": "lachlan.bot",
        "email": "lachlan.bot@insitec.com.au",
        "first_name": "Lachlan",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "DevSecOps Engineer",
        "description": "Deployment and infrastructure",
        "persona_type": "devsecops-engineer",
        "skills": ["CI/CD", "Infrastructure as Code", "Security Automation"]
    },
    {
        "username": "shaun.bot",
        "email": "shaun.bot@insitec.com.au",
        "first_name": "Shaun",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "UI/UX Designer",
        "description": "Interface design and user experience",
        "persona_type": "ui-ux-designer",
        "skills": ["UI Design", "UX Research", "Prototyping", "Design Systems"]
    },
    {
        "username": "laureen.bot",
        "email": "laureen.bot@insitec.com.au",
        "first_name": "Laureen",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Technical Writer",
        "description": "Documentation",
        "persona_type": "technical-writer",
        "skills": ["Technical Documentation", "API Documentation", "User Guides"]
    },
    {
        "username": "ruley.bot",
        "email": "ruley.bot@insitec.com.au",
        "first_name": "Ruley",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Requirements Analyst",
        "description": "Requirements analysis and validation",
        "persona_type": "requirements-analyst",
        "skills": ["Requirements Gathering", "Business Analysis", "User Stories"]
    },
    {
        "username": "brumbie.bot",
        "email": "brumbie.bot@insitec.com.au",
        "first_name": "Brumbie",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Project Manager",
        "description": "Product management & Project coordination",
        "persona_type": "product-owner",
        "skills": ["Project Management", "Agile", "Stakeholder Management"]
    },
    {
        "username": "moby.bot",
        "email": "moby.bot@insitec.com.au",
        "first_name": "Moby",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Mobile Developer",
        "description": "Mobile-specific implementation guidance",
        "persona_type": "mobile-developer",
        "skills": ["iOS", "Android", "React Native", "Mobile Architecture"]
    },
    {
        "username": "claude.bot",
        "email": "claude.bot@insitec.com.au",
        "first_name": "Claude",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "AI Integration",
        "description": "AI feature integration planning",
        "persona_type": "ai-engineer",
        "skills": ["Machine Learning", "AI Integration", "LLM Development"]
    },
    {
        "username": "puck.bot",
        "email": "puck.bot@insitec.com.au",
        "first_name": "Puck",
        "last_name": "Bot",
        "password": "Automation123!",
        "role": "Developer",
        "description": "Core implementation specifications",
        "persona_type": "developer-engineer",
        "skills": ["Full Stack Development", "System Integration", "Code Review"]
    }
]


def get_test_persona(username: str) -> dict:
    """Get a specific test persona by username"""
    for persona in TEST_PERSONAS:
        if persona["username"] == username:
            return persona
    return None


def get_test_personas_by_role(role: str) -> list:
    """Get test personas by role"""
    return [p for p in TEST_PERSONAS if role.lower() in p["role"].lower()]


def get_test_persona_by_type(persona_type: str) -> dict:
    """Get first test persona by type"""
    for persona in TEST_PERSONAS:
        if persona["persona_type"] == persona_type:
            return persona
    return None