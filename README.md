# Sample AI Agent Framework

This repository contains a simple AI agent framework built with [Opper](https://opper.ai) that demonstrates how to create intelligent agents with reasoning capabilities.

## What's Included

### BaseAgent (`base_agent.py`)

A foundational class for building AI agents that use a **Think → Act** reasoning loop. The BaseAgent provides:

**Core Reasoning Loop:**
- **Think**: Analyzes current situation, reviews previous results, and decides next action
- **Act**: Executes actions using available tools 
- **Repeat**: Continues until goal is achieved or max iterations reached

**Key Features:**
- **Iteration Awareness**: Tracks progress and plans efficiently within iteration limits
- **Tool Management**: Dynamic tool registration and execution with parameter validation
- **Context Management**: Maintains execution context across iterations for data sharing
- **Smart Planning**: AI-driven action selection that prioritizes tool usage over direct responses
- **Structured I/O**: Pydantic schemas for consistent input/output formatting
- **Comprehensive Tracing**: Built-in observability with Opper for debugging and monitoring
- **Flexible Architecture**: Use directly with tools/description or extend via subclassing
- **Real-time Callbacks**: Status updates for UI integration and progress monitoring
- **Error Handling**: Graceful failure recovery with detailed error reporting

### MathAgent (`math_agent.py`)

A complete example showing how to use BaseAgent to create a math-solving agent. It includes:

- **Custom Tools**: Addition, subtraction, multiplication, and division
- **Structured Output**: Returns detailed solutions with reasoning steps
- **Goal Processing**: Solves complex math problems step-by-step
- **Status Callbacks**: Real-time updates during problem solving

### EmailAgent (`email_agent.py`)

A comprehensive Gmail-integrated agent that automates email management workflows. It includes:

- **Gmail API Integration**: Secure OAuth authentication with Gmail
- **Smart Email Listing**: Flexible email filtering with query support (unread, specific senders, etc.)
- **Intelligent Email Analysis**: AI-powered categorization, priority assessment, and sentiment analysis
- **Label Management**: Automatic label creation and application for email organization
- **Reply Assessment**: Determines if emails need responses and urgency levels
- **Draft Generation**: Creates contextual draft replies with proper threading
- **Batch Processing**: Handles multiple emails efficiently with iteration management
- **Comprehensive Workflow**: From email discovery to categorization, labeling, and response drafting

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

The first run will open a browser window for Gmail authentication. After authorization, the agent can:
- List and filter emails (unread, specific senders, date ranges, etc.)
- Analyze emails for category, priority, sentiment, and action items
- Apply appropriate labels for organization (work, personal, urgent, etc.)
- Determine reply necessity and urgency
- Generate contextual draft responses with proper threading
- Handle complex workflows like "process 10 unread emails, categorize them, and draft responses"

## Creating Your Own Agent

### Basic Example

```python
from base_agent import BaseAgent, Tool

# Define your tools
class MyTool(Tool):
    def __init__(self):
        super().__init__(
            name="my_tool",
            description="What this tool does",
            parameters={"param": "str - Description of parameter"}
        )
    
    def execute(self, _parent_span_id=None, param: str = "", **kwargs) -> dict:
        return {
            "success": True,
            "result": f"Processed: {param}",
            "data": {"input": param}
        }

# Create your agent
agent = BaseAgent(
    name="MyAgent",
    description="What your agent does",
    tools=[MyTool()],
    max_iterations=25,
    verbose=True
)

# Use your agent
result = agent.process("Your goal here")
```

### Configuration Options

The BaseAgent constructor accepts these parameters:

- **`name`**: Agent identifier for tracing and logging
- **`opper_api_key`**: Optional API key (uses OPPER_API_KEY env var if not provided)  
- **`max_iterations`**: Maximum reasoning loop iterations (default: 25)
- **`verbose`**: Enable detailed execution logging (default: False)
- **`output_schema`**: Pydantic model for structured result formatting
- **`tools`**: List of Tool instances for the agent to use
- **`description`**: Agent description for AI context
- **`callback`**: Function to receive status updates (`callback(event_type, data)`)

### Tool Development

Tools should:
- Inherit from the `Tool` base class
- Accept `_parent_span_id` for tracing AI calls within tools
- Return structured results with success indicators
- Handle errors gracefully
- Use `**kwargs` for parameter flexibility

## How It Works

The BaseAgent implements a sophisticated **Think → Act** reasoning loop:

### Core Process

1. **Initialize**: Agent receives a goal and sets up tracing/context
2. **Think**: AI analyzes the situation and decides on the next action
   - Reviews previous action results
   - Considers available tools and parameters
   - Tracks iteration count and remaining iterations
   - Updates execution context with important data
   - Decides if goal is achieved or what action to take next
3. **Act**: Agent executes the chosen action using appropriate tools
4. **Repeat**: Process continues until goal achieved or max iterations reached

### Example Flow

```
🎯 Goal: "Calculate (25 * 4) + (100 / 5) - 7"
🔄 Max iterations: 25

--- Iteration 1 ---
🧠 Think: Need to solve math expression, will multiply 25 * 4 first
⚡ Act: multiply_tool(a=25, b=4) → 100

--- Iteration 2 ---  
🧠 Think: Got 100, now need to divide 100 / 5
⚡ Act: divide_tool(a=100, b=5) → 20

--- Iteration 3 ---
🧠 Think: Have 100 and 20, need to add them
⚡ Act: add_tool(a=100, b=20) → 120

--- Iteration 4 ---
🧠 Think: Have 120, need to subtract 7 to complete
⚡ Act: subtract_tool(a=120, b=7) → 113

--- Iteration 5 ---
🧠 Think: All calculations complete, goal achieved
✅ Result: 113
```

### Advanced Features

- **Iteration Management**: Agent tracks progress and adjusts strategy based on remaining iterations
- **Context Sharing**: Important data persists across iterations for complex workflows
- **Tool Prioritization**: Agent prefers using tools over direct responses when possible
- **Error Recovery**: Graceful handling of tool failures with alternative approaches
- **Structured Output**: Consistent result formatting with detailed execution history

The framework abstracts all complexity of LLM interactions, tool orchestration, and reasoning loops while providing full observability and control.
