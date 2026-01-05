"""
Smart Mermaid Diagram Guide - Flexible & Helpful
"""

from mcp_app import mcp

@mcp.prompt()
def diagram_selection_guide():
    """Intelligent workflow for Mermaid diagram generation"""
    
    return """
# Smart Mermaid Workflow

## Core Principles
1. **Respect explicit user intent** - If user specifies diagram type, use it immediately
2. **Suggest only when helpful** - Brief recommendation only if better option clearly exists
3. **Accept user's choice** - Never argue or over-explain
4. **Default: Just do it** - When in doubt, generate what user asked for

## Decision Flow

### Scenario A: User Explicitly Specifies Type
User: "Create a flowchart from this: graph TD; User-->API"
→ Generate flowchart immediately. No questions.

### Scenario B: Code Matches Intent (Good Fit)
User: "graph TD; Start-->Process-->Decision-->End"
→ Code is flowchart syntax, content is process flow. Perfect match.
→ Generate quietly.

### Scenario C: Clear Better Alternative Exists
User: "graph TD; User->>Server->>Database"
→ Code uses flowchart but shows interactions (arrows suggest communication)
→ Brief suggestion: "I can generate as flowchart, or sequence diagram (better for interactions). Your choice?"
→ User decides → Generate their choice

## Diagram Types Reference

**flowchart/graph** - Processes, decisions, workflows, steps
**sequenceDiagram** - Interactions, API calls, communication between entities
**erDiagram** - Database schemas, table relationships
**classDiagram** - OOP design, class structures, inheritance
**stateDiagram** - State transitions, status changes, lifecycles
**gantt** - Timelines, schedules, project plans
**pie** - Data distributions, percentages, breakdowns
**gitGraph** - Git branching, version control workflows

## Suggestion Rules

✅ **Suggest when:**
- Flowchart code but shows entity interactions (→ sequenceDiagram)
- List of data but not database (→ pie chart)
- Timeline described but wrong type (→ gantt)

❌ **Don't suggest when:**
- User explicitly named type ("make a flowchart")
- Code syntax matches content well
- Multiple options equally valid
- Minor improvements only

## Response Format

**When suggesting:**
"I can generate [what they asked], or [better option] which is clearer for [reason]. Your choice?"

**Keep it short:** One sentence recommendation max.

**Then:** Accept whatever user chooses and generate immediately.

## Defaults
- Format: SVG (fastest, scalable)
- Theme: default
- Quality: scale=2, width=1600 (balanced)
"""
