"""
Base Agent class for building AI agents with Opper.
Provides a foundation for agents with a core reasoning loop (Plan -> Act -> Reflect).
"""

# No longer need ABC since BaseAgent is now a concrete class
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from opperai import Opper
import time


class Tool(BaseModel):
    """Represents a tool that an agent can use."""
    name: str = Field(description="The name of the tool")
    description: str = Field(description="Description of what the tool does")
    parameters: Dict[str, Any] = Field(description="Parameters the tool accepts")
    
    def execute(self, **kwargs) -> Any:
        """Execute the tool with given parameters."""
        # This is a placeholder - subclasses should implement actual tool logic
        raise NotImplementedError(f"Tool {self.name} execution not implemented")


class Plan(BaseModel):
    """Represents a plan for achieving the goal."""
    thoughts: str = Field(description="Reasoning about the current situation and what needs to be done")
    steps: List[str] = Field(description="Ordered list of steps to achieve the goal")
    current_step: int = Field(description="Index of the current step to execute (0-based)")
    goal_achieved: bool = Field(description="Whether the goal has been achieved")


class Action(BaseModel):
    """Represents an action to be taken."""
    thoughts: str = Field(description="Reasoning about what action to take and why")
    tool_name: str = Field(description="Name of the tool to use, or 'direct_response' for direct completion")
    tool_parameters: Dict[str, Any] = Field(description="Parameters to pass to the tool")
    expected_outcome: str = Field(description="What we expect to happen from this action")
    user_message: str = Field(description="A note to the user on what you are about to do")


class Reflection(BaseModel):
    """Represents reflection on the result of an action."""
    thoughts: str = Field(description="Analysis of what happened and what was learned")
    action_successful: bool = Field(description="Whether the action achieved its expected outcome")
    lessons_learned: str = Field(description="Key insights from this action")
    next_steps: str = Field(description="What should be done next based on this reflection")
    goal_progress: str = Field(description="Assessment of progress toward the overall goal")


class BaseAgent:
    """
    Base class for AI agents using Opper with a core reasoning loop.
    
    This class provides a foundation for building agents with:
    - A core reasoning loop (Plan -> Act -> Reflect)
    - Tool management and execution
    - Integration with Opper for LLM calls
    - Structured state management
    
    Can be used in two ways:
    1. Direct instantiation: provide tools and description in constructor
    2. Subclassing: override get_tools(), get_agent_description(), is_goal_achieved()
    """
    
    def __init__(
        self,
        name: str,
        opper_api_key: Optional[str] = None,
        max_iterations: int = 10,
        verbose: bool = False,
        output_schema: Optional[type] = None,
        tools: Optional[List[Tool]] = None,
        description: Optional[str] = None,
        callback: Optional[callable] = None
    ):
        """
        Initialize the base agent.
        
        Args:
            name: The name of the agent
            opper_api_key: Optional API key for Opper (will use env var if not provided)
            max_iterations: Maximum number of reasoning loop iterations
            verbose: Whether to print detailed execution logs
            output_schema: Optional Pydantic model for structuring the final result
            tools: Optional list of tools (if provided, get_tools() doesn't need to be implemented)
            description: Optional description (if provided, get_agent_description() doesn't need to be implemented)
            callback: Optional callback function to receive status updates (event_type, data)
        """
        self.name = name
        self.opper = Opper(http_bearer=opper_api_key)
        self.max_iterations = max_iterations
        self.verbose = verbose
        self.output_schema = output_schema
        self.callback = callback
        
        # Initialize agent state
        self.current_plan: Optional[Plan] = None
        self.execution_history: List[Dict[str, Any]] = []
        self.current_goal: Optional[str] = None
        
        # Get tools and description (from constructor or subclass)
        self.tools = tools if tools is not None else self.get_tools()
        self.description = description if description is not None else self.get_agent_description()
        
        # Initialize agent state
        self._initialize_agent()
    
    def _initialize_agent(self):
        """Initialize agent-specific state. Override in subclasses if needed."""
        pass
    
    def _emit_status(self, event_type: str, data: Any):
        """Emit a status update through the callback if one is provided."""
        if self.callback:
            try:
                self.callback(event_type, data)
            except Exception as e:
                # Don't let callback errors break the agent
                if self.verbose:
                    print(f"⚠️  Callback error for {event_type}: {e}")
    
    def get_tools(self) -> List[Tool]:
        """
        Return the list of tools available to this agent.
        Override this method if not providing tools in constructor.
        
        Returns:
            List of Tool instances this agent can use
        """
        return []
    
    def get_agent_description(self) -> str:
        """
        Return a description of what this agent does.
        Override this method if not providing description in constructor.
        
        Returns:
            String description of the agent's purpose and capabilities
        """
        return f"AI agent named {self.name}"
    
    def is_goal_achieved(self, goal: str, execution_history: List[Dict[str, Any]]) -> bool:
        """
        Check if the goal has been achieved based on execution history.
        Override this method for custom goal achievement logic.
        
        Default implementation: checks if the last reflection indicates success.
        
        Args:
            goal: The goal to check
            execution_history: History of plan-action-reflection cycles
            
        Returns:
            True if the goal is achieved, False otherwise
        """
        if not execution_history:
            return False
        
        # Default implementation: check if last reflection indicates success
        last_cycle = execution_history[-1]
        last_reflection = last_cycle.get("reflection", {})
        return last_reflection.get("action_successful", False)
    
    def add_tool(self, tool: Tool):
        """Add a tool to the agent's toolkit."""
        self.tools.append(tool)
    
    def remove_tool(self, tool_name: str):
        """Remove a tool from the agent's toolkit."""
        self.tools = [tool for tool in self.tools if tool.name != tool_name]
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """Get a specific tool by name."""
        for tool in self.tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def list_tools(self) -> List[str]:
        """Get a list of available tool names."""
        return [tool.name for tool in self.tools]
    
    def _create_plan(self, goal: str, parent_span_id: str) -> Plan:
        """Create a plan for achieving the goal."""
        context = {
            "goal": goal,
            "agent_description": self.description,
            "available_tools": [{"name": tool.name, "description": tool.description} for tool in self.tools],
            "execution_history": self.execution_history[-3:] if self.execution_history else []  # Last 3 cycles for context
        }
        
        plan_call = self.call_llm(
            name="plan",
            instructions="You are a planning assistant. Analyze the goal and create a detailed plan to achieve it. Consider the available tools and any previous execution history. If the goal is already achieved based on the history, set goal_achieved to true.",
            input_data=context,
            output_schema=Plan,
            parent_span_id=parent_span_id
        )
        
        return Plan(**plan_call.json_payload)
    
    def _decide_action(self, plan: Plan, parent_span_id: str) -> Action:
        """Decide what action to take based on the current plan."""
        context = {
            "plan": plan.dict(),
            "available_tools": [{"name": tool.name, "description": tool.description, "parameters": tool.parameters} for tool in self.tools]
        }
        
        action_call = self.call_llm(
            name="decide",
            instructions="You are an action planner. Based on the current plan and available tools, decide what specific action to take to execute the next step in the plan. Use 'direct_response' as tool_name if you can complete the goal directly without tools.",
            input_data=context,
            output_schema=Action,
            parent_span_id=parent_span_id
        )
        
        return Action(**action_call.json_payload)
    
    def _execute_action(self, action: Action) -> Dict[str, Any]:
        """Execute the specified action."""
        if action.tool_name == "direct_response":
            return {
                "type": "direct_response",
                "result": "Task completed directly without tool usage",
                "success": True
            }
        
        # Find and execute the tool
        tool = self.get_tool(action.tool_name)
        if not tool:
            return {
                "type": "error",
                "result": f"Tool '{action.tool_name}' not found",
                "success": False
            }
        
        try:
            result = tool.execute(**action.tool_parameters)
            return {
                "type": "tool_execution",
                "tool_name": action.tool_name,
                "parameters": action.tool_parameters,
                "result": result,
                "success": True
            }
        except Exception as e:
            return {
                "type": "error",
                "tool_name": action.tool_name,
                "parameters": action.tool_parameters,
                "result": f"Error executing tool: {str(e)}",
                "success": False
            }
    
    def _reflect_on_result(self, action: Action, action_result: Dict[str, Any], plan: Plan, parent_span_id: str) -> Reflection:
        """Reflect on the result of the action."""
        context = {
            "action": action.dict(),
            "action_result": action_result,
            "goal": self.current_goal
        }
        
        reflection_call = self.call_llm(
            name="reflect",
            instructions="You are a reflection assistant. Analyze what happened with this specific action and its result. Evaluate if the action was successful and what should be done next to progress toward the goal.",
            input_data=context,
            output_schema=Reflection,
            parent_span_id=parent_span_id
        )
        
        return Reflection(**reflection_call.json_payload)
    
    def _generate_final_result(self, goal: str, execution_history: List[Dict[str, Any]], parent_span_id: str) -> Any:
        """Generate the final structured result based on the output schema."""
        if not self.output_schema:
            # Return default result format if no schema specified
            return {
                "goal": goal,
                "achieved": self.is_goal_achieved(goal, execution_history),
                "iterations": len(execution_history),
                "execution_history": execution_history
            }
        
        # Generate structured result using the output schema
        context = {
            "goal": goal,
            "execution_history": execution_history,
            "agent_description": self.description,
            "goal_achieved": self.is_goal_achieved(goal, execution_history),
            "iterations": len(execution_history)
        }
        
        result_call = self.call_llm(
            name="generate_final_result",
            instructions="You are a result formatter. Based on the goal and execution history, generate a structured final result. Extract the key information and format it according to the required schema. Focus on the main outcomes and insights from the agent's work.",
            input_data=context,
            output_schema=self.output_schema,
            parent_span_id=parent_span_id
        )
        
        return result_call.json_payload
    
    def get_tools_summary(self) -> str:
        """Get a formatted summary of available tools."""
        tool_names = [tool.name for tool in self.tools]
        return f"Agent '{self.name}' tools: {', '.join(tool_names)}"
    
    def process(self, goal: str) -> Dict[str, Any]:
        """
        Process a goal using the reasoning loop: Plan -> Act -> Reflect -> Repeat.
        
        This is the main method that implements the core reasoning loop.
        It continues until the goal is achieved or max iterations are reached.
        
        Args:
            goal: The goal to achieve
            
        Returns:
            Dictionary containing the final result and execution history
        """
        self.current_goal = goal
        self.execution_history = []
        
        # Start a trace for this goal processing session
        trace = self.start_trace(
            name=f"{self.name}",
            input_data=goal
        )
        
        # Emit goal start event
        self._emit_status("goal_start", {
            "goal": goal,
            "agent_name": self.name,
            "available_tools": [tool.name for tool in self.tools]
        })
        
        if self.verbose:
            print(f"🎯 Starting goal: {goal}")
            print(f"🤖 Agent: {self.name}")
            print(f"🔧 Available tools: {[tool.name for tool in self.tools]}")
        
        iteration = 0
        while iteration < self.max_iterations:
            iteration += 1
            
            # Create a span for this iteration
            iteration_span = self.opper.spans.create(
                name=f"iteration_{iteration}",
                input=f"Iteration {iteration} of goal: {goal}",
                parent_id=trace.id
            )
            
            if self.verbose:
                print(f"\n--- Iteration {iteration} ---")
            
            # Step 1: Plan
            plan = self._create_plan(goal, iteration_span.id)
            
            # Emit plan event
            self._emit_status("plan_created", {
                "iteration": iteration,
                "plan": plan.dict()
            })
            
            if self.verbose:
                print(f"📋 Plan: {plan.thoughts}")
                print(f"📝 Steps: {plan.steps}")
            
            # Check if goal is already achieved
            if plan.goal_achieved:
                if self.verbose:
                    print("✅ Goal achieved!")
                break
            
            # Step 2: Decide and execute action
            action = self._decide_action(plan, iteration_span.id)
            
            # Emit action event
            self._emit_status("action_decided", {
                "iteration": iteration,
                "action": action.dict()
            })
            
            if self.verbose:
                print(f"⚡ Action: {action.tool_name} with {action.tool_parameters}")
            
            action_result = self._execute_action(action)
            
            # Emit action result event
            self._emit_status("action_executed", {
                "iteration": iteration,
                "action": action.dict(),
                "result": action_result
            })
            
            if self.verbose:
                print(f"📊 Result: {action_result}")
            
            # Step 3: Reflect on the result
            reflection = self._reflect_on_result(action, action_result, plan, iteration_span.id)
            
            # Emit reflection event
            self._emit_status("reflection_completed", {
                "iteration": iteration,
                "reflection": reflection.dict()
            })
            
            if self.verbose:
                print(f"🤔 Reflection: {reflection.thoughts}")
                print(f"📈 Progress: {reflection.goal_progress}")
            
            # Store this iteration's cycle
            cycle = {
                "iteration": iteration,
                "plan": plan.dict(),
                "action": action.dict(),
                "action_result": action_result,
                "reflection": reflection.dict(),
                "timestamp": time.time()
            }
            self.execution_history.append(cycle)
            
            # Update the iteration span with the results
            self.opper.spans.update(
                span_id=iteration_span.id,
                output=f"Plan: {plan.thoughts[:100]}... | Action: {action.tool_name} | Success: {reflection.action_successful}"
            )
            
            # Update current plan
            self.current_plan = plan
            
        
        # Generate the final structured result
        final_result = self._generate_final_result(goal, self.execution_history, trace.id)
        
        # Emit goal completion event
        self._emit_status("goal_completed", {
            "goal": goal,
            "achieved": self.is_goal_achieved(goal, self.execution_history),
            "iterations": iteration,
            "final_result": final_result
        })
        
        self.opper.spans.update(
            span_id=trace.id,
            output=str(final_result)
        )
        
        if self.verbose:
            print(f"\n🏁 Completed in {iteration} iterations")
            # Handle both structured and unstructured results
            if isinstance(final_result, dict) and 'achieved' in final_result:
                print(f"✅ Goal achieved: {final_result['achieved']}")
            else:
                print(f"✅ Goal achieved: {self.is_goal_achieved(goal, self.execution_history)}")
                print(f"📄 Structured result: {final_result}")
        
        return final_result
    
    def call_llm(
        self,
        name: str,
        instructions: str,
        input_schema: Optional[type] = None,
        output_schema: Optional[type] = None,
        input_data: Any = None,
        model: Optional[str] = None,
        parent_span_id: Optional[str] = None
    ):
        """
        Make a call to the LLM using Opper.
        
        This method provides a convenient way for agents to interact with LLMs
        while maintaining proper tracing and schema validation.
        
        Args:
            name: Name of the call for tracking
            instructions: Instructions for the LLM
            input_schema: Optional Pydantic model for input validation
            output_schema: Optional Pydantic model for output validation
            input_data: Input data for the call
            model: Optional specific model to use
            parent_span_id: Optional parent span ID for tracing
            
        Returns:
            The result of the LLM call
        """
        return self.opper.call(
            name=name,
            instructions=instructions,
            input_schema=input_schema,
            output_schema=output_schema,
            input=input_data,
            model=model,
            parent_span_id=parent_span_id
        )
    
    def start_trace(self, name: str, input_data: Any = None):
        """
        Start a new trace for the agent's operations.
        
        Args:
            name: Name of the trace
            input_data: Input data for the trace
            
        Returns:
            The created span
        """
        return self.opper.spans.create(
            name=name,
            input=str(input_data) if input_data else None
        )
    
    def __str__(self) -> str:
        """String representation of the agent."""
        return f"Agent(name='{self.name}', tools={len(self.tools)})"
    
    def __repr__(self) -> str:
        """Detailed representation of the agent."""
        return f"BaseAgent(name='{self.name}', description='{self.description}', tools={[tool.name for tool in self.tools]})"