# Sample AI Agent Framework

This repository contains a simple AI agent framework built with [Opper](https://opper.ai) that demonstrates how to create intelligent agents with reasoning capabilities.

## What's Included

### BaseAgent (`base_agent.py`)

A foundational class for building AI agents that use a **Plan → Act → Reflect** reasoning loop. The BaseAgent:

- **Plans**: Creates a step-by-step plan to achieve a goal
- **Acts**: Executes actions using available tools
- **Reflects**: Analyzes results and decides next steps
- **Repeats**: Continues until the goal is achieved

Key features:
- Tool management system for adding custom capabilities
- Structured input/output with Pydantic schemas
- Built-in tracing and observability with Opper
- Flexible architecture - use directly or extend with subclasses
- Callback for yielding agent progress to UIs

### MathAgent (`math_agent.py`)

A complete example showing how to use BaseAgent to create a math-solving agent. It includes:

- **Custom Tools**: Addition, subtraction, multiplication, and division
- **Structured Output**: Returns detailed solutions with reasoning steps
- **Goal Processing**: Solves complex math problems step-by-step
- **Status Callbacks**: Real-time updates during problem solving

### EmailAgent (`email_agent.py`)

A Gmail-integrated agent that automates email management tasks. It includes:

- **Gmail API Integration**: Secure OAuth authentication with Gmail
- **Email Fetching**: Finds unreplied emails in your inbox
- **AI Reply Generation**: Creates contextual draft replies
- **Batch Processing**: Handles multiple emails efficiently
- **Draft Management**: Creates drafts you can review before sending

Example run output:

```
Agent created:  MathAgent
Goal: Calculate the result of (25 * 4) + (100 / 5) - 7
Agent: I will now compute the first term by multiplying 25 by 4.
Agent: I will now divide 100 by 5 to calculate the second term.
Agent: I will proceed to add the results of the first term (100) and the second term (20) together.
Agent: I am about to subtract 7 from 120 to complete the calculation.
Result: 113
```

## Quick Start

### Math Agent

1. **Install dependencies**:
```bash
pip install opperai pydantic
```

2. **Set your Opper API key**:
```bash
export OPPER_API_KEY="your_api_key_here"
```

3. **Run the math agent example**:
```bash
python math_agent.py
```

### Email Agent

1. **Install all dependencies**:
```bash
python setup_email_agent.py
```

2. **Set up Gmail API credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select existing one
   - Enable the Gmail API
   - Configure OAuth consent screen
   - Create OAuth 2.0 credentials (Desktop application)
   - Download credentials as `credentials.json`

3. **Set your Opper API key**:
```bash
export OPPER_API_KEY="your_api_key_here"
```

4. **Run the email agent**:
```bash
python email_agent.py
```

The first run will open a browser window for Gmail authentication. After authorization, the agent will:
- Find your last 5 unreplied emails
- Generate appropriate draft replies
- Save drafts to your Gmail account for review

## Creating Your Own Agent

```python
from base_agent import BaseAgent, Tool

# Define your tools
class MyTool(Tool):
    def __init__(self):
        super().__init__(
            name="my_tool",
            description="What this tool does",
            parameters={"param": "type"}
        )
    
    def execute(self, param: str) -> str:
        return f"Processed: {param}"

# Create your agent
agent = BaseAgent(
    name="MyAgent",
    description="What your agent does",
    tools=[MyTool()],
    verbose=True
)

# Use your agent
result = agent.process("Your goal here")
```

## How It Works

1. **Give the agent a goal**: "Calculate (25 * 4) + (100 / 5) - 7"
2. **Agent plans**: Breaks down the problem into steps
3. **Agent acts**: Uses math tools to perform calculations
4. **Agent reflects**: Checks if the answer is correct
5. **Agent responds**: Returns structured solution with reasoning

The framework handles all the complexity of LLM interactions, tool management, and reasoning loops automatically.
