"""
Example agent working of opper base agent
"""

from typing import Any, List, Dict
from pydantic import BaseModel, Field
from base_agent import BaseAgent, Tool


class AddTool(Tool):
    """Addition tool for mathematical operations."""
    
    def __init__(self):
        super().__init__(
            name="add",
            description="Adds two numbers together",
            parameters={
                "a": "float - The first number",
                "b": "float - The second number"
            }
        )
    
    def execute(self, _parent_span_id=None, a: float = None, b: float = None, **kwargs) -> float:
        """Execute the addition operation."""
        # Handle both old and new calling conventions
        if a is None:
            a = kwargs.get('a', 0.0)
        if b is None:
            b = kwargs.get('b', 0.0)
        return a + b


class SubtractTool(Tool):
    """Subtraction tool for mathematical operations."""
    
    def __init__(self):
        super().__init__(
            name="subtract",
            description="Subtracts the second number from the first number",
            parameters={
                "a": "float - The number to subtract from",
                "b": "float - The number to subtract"
            }
        )
    
    def execute(self, _parent_span_id=None, a: float = None, b: float = None, **kwargs) -> float:
        """Execute the subtraction operation."""
        # Handle both old and new calling conventions
        if a is None:
            a = kwargs.get('a', 0.0)
        if b is None:
            b = kwargs.get('b', 0.0)
        return a - b


class MultiplyTool(Tool):
    """Multiplication tool for mathematical operations."""
    
    def __init__(self):
        super().__init__(
            name="multiply",
            description="Multiplies two numbers together",
            parameters={
                "a": "float - The first number",
                "b": "float - The second number"
            }
        )
    
    def execute(self, _parent_span_id=None, a: float = None, b: float = None, **kwargs) -> float:
        """Execute the multiplication operation."""
        # Handle both old and new calling conventions
        if a is None:
            a = kwargs.get('a', 0.0)
        if b is None:
            b = kwargs.get('b', 0.0)
        return a * b


class DivideTool(Tool):
    """Division tool for mathematical operations."""
    
    def __init__(self):
        super().__init__(
            name="divide",
            description="Divides the first number by the second number",
            parameters={
                "a": "float - The dividend (number to be divided)",
                "b": "float - The divisor (number to divide by)"
            }
        )
    
    def execute(self, _parent_span_id=None, a: float = None, b: float = None, **kwargs) -> float:
        """Execute the division operation."""
        # Handle both old and new calling conventions
        if a is None:
            a = kwargs.get('a', 0.0)
        if b is None:
            b = kwargs.get('b', 0.0)
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b


class MathProblemInput(BaseModel):
    """Input schema for math problems."""
    problem: str = Field(description="A math problem to solve")


class MathSolution(BaseModel):
    """Output schema for math solutions."""
    thoughts: str = Field(description="The agent's reasoning about solving the problem")
    answer: float = Field(description="The numerical answer to the math problem")
    solution_steps: List[str] = Field(description="Step-by-step process used to solve the problem")
    operations_used: List[str] = Field(description="List of mathematical operations that were performed")
    confidence: str = Field(description="How confident the agent is in the solution (high, medium, low)")
    verification: str = Field(description="How the answer was verified or could be verified")


def print_status(event_type: str, data: dict):
    """
    Example callback that prints key events from the Think->Act loop.
    
    This demonstrates how to filter specific events and data from the agent's execution.
    
    Available event types:
    - "goal_start": When the agent starts processing a goal
    - "thought_created": When a thought is created (contains thought.reasoning, thought.goal_achieved, etc.)
    - "action_executed": When an action is executed (contains thought + action_result)
    - "goal_completed": When the goal processing is finished
    """

    if event_type == "goal_start":
        print(f"Agent: {data.get('agent_name')}")
        print(f"Goal: {data.get('goal')}")
    elif event_type == "thought_created":
        user_message = data.get("thought", {}).get("user_message", "")
        if user_message:
            print(user_message)

def main():
    """Example usage of the MathAgent."""
    import os
    
    # Check for API key
    api_key = os.getenv("OPPER_API_KEY")
    if not api_key:
        print("❌ ERROR: OPPER_API_KEY environment variable is required!")
        print("")
        print("To fix this:")
        print("1. Get your API key from https://platform.opper.ai")
        print("2. Set the environment variable:")
        print("   export OPPER_API_KEY='your_api_key_here'")
        print("")
        print("Alternatively, you can set it in your current session:")
        print("   OPPER_API_KEY='your_api_key_here' python example_agent.py")
        return
    
    try:
        
        description = "An agent that solves mathematical problems using calculation tools and logical reasoning."

        math_tools = [
            AddTool(),
            SubtractTool(), 
            MultiplyTool(),
            DivideTool()
        ]
        
        agent = BaseAgent(
            name="MathAgent",
            opper_api_key=api_key,
            callback=print_status,
            verbose=False,
            output_schema=MathSolution,
            tools=math_tools,
            description=description,
        )

        goal = "Calculate the result of (25 * 4) + (100 / 5) - 7"

        result = agent.process(goal)
        
        print(f"Result: {result.get('answer')}")
        
    except Exception as e:
        print(f"❌ Error running agent: {e}")
        print("This might be due to:")
        print("- Invalid API key")
        print("- Network connectivity issues")
        print("- Missing dependencies")
        print("\nPlease check your API key and internet connection.")


if __name__ == "__main__":
    main()
