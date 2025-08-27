"""
Twitter Agent for interacting with Twitter/X platform using Composio tools.
"""

import os
import json
from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field
from composio import Composio
import time

from base_agent import BaseAgent, Tool


class TwitterTool(Tool):
    """Generic Twitter tool that uses Composio's direct tool execution."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, composio_client: Composio, user_id: str, tool_info: Dict[str, Any]):
        """
        Initialize a Twitter tool using Composio tool information.
        
        Args:
            composio_client: The Composio client instance
            user_id: User ID for authentication
            tool_info: Tool information from Composio API
        """
        # Extract tool information from Composio response
        function_info = tool_info.get("function", {})
        tool_name = function_info.get("name", "unknown_tool")
        tool_description = function_info.get("description", f"Execute {tool_name} on Twitter")
        
        # Extract parameters from the tool schema
        parameters_schema = function_info.get("parameters", {})
        properties = parameters_schema.get("properties", {})
        
        # Convert Composio parameter schema to our format
        tool_parameters = {}
        for param_name, param_info in properties.items():
            param_type = param_info.get("type", "string")
            param_description = param_info.get("description", f"{param_name} parameter")
            examples = param_info.get("examples", [])
            
            # Add examples to description if available
            if examples:
                param_description += f" Examples: {examples}"
            
            tool_parameters[param_name] = f"{param_type} - {param_description}"
        
        super().__init__(
            name=tool_name.lower().replace("twitter_", ""),
            description=tool_description,
            parameters=tool_parameters
        )
        self.composio_client = composio_client
        self.user_id = user_id
        self.composio_tool_name = tool_name
        self.tool_info = tool_info
    
    def execute(self, _parent_span_id=None, **kwargs) -> Dict[str, Any]:
        """Execute the Twitter tool using Composio's direct execution."""
        try:
            # Use Composio's direct tool execution
            result = self.composio_client.tools.execute(
                self.composio_tool_name,
                user_id=self.user_id,
                arguments=kwargs
            )
            
            return {
                "success": True,
                "result": f"Successfully executed {self.composio_tool_name}",
                "details": result,
                "tool_name": self.name
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing {self.composio_tool_name}: {str(e)}",
                "tool_name": self.name
            }


class TwitterResult(BaseModel):
    """Result schema for Twitter agent operations."""
    thoughts: str = Field(description="The agent's reasoning about the Twitter operation")
    success: bool = Field(description="Whether the Twitter operation was successful")
    operation: str = Field(description="The type of operation performed (post, search, follow, etc.)")
    details: Dict[str, Any] = Field(description="Detailed results of the operation")
    summary: str = Field(description="A brief summary of what was accomplished")


class TwitterAgent(BaseAgent):
    """
    AI agent for Twitter/X platform operations using Composio.
    
    This agent can:
    - Post tweets
    - Search for tweets
    - Follow/unfollow users
    - Get user profiles
    - Interact with Twitter content
    """
    
    def __init__(
        self,
        user_id: str,
        composio_api_key: Optional[str] = None,
        opper_api_key: Optional[str] = None,
        max_iterations: int = 25,
        verbose: bool = False,
        callback: Optional[callable] = None
    ):
        """
        Initialize the Twitter agent.
        
        Args:
            user_id: User ID for Composio authentication
            composio_api_key: API key for Composio (will use env var if not provided)
            opper_api_key: API key for Opper (will use env var if not provided)
            max_iterations: Maximum number of reasoning loop iterations
            verbose: Whether to print detailed execution logs
            callback: Optional callback function for status updates
        """
        self.user_id = user_id
        
        # Initialize Composio client
        # If no API key provided, Composio will automatically use COMPOSIO_API_KEY env var
        if composio_api_key:
            self.composio = Composio(api_key=composio_api_key)
        else:
            self.composio = Composio()
        
        # Initialize base agent
        super().__init__(
            name="TwitterAgent",
            opper_api_key=opper_api_key,
            max_iterations=max_iterations,
            verbose=verbose,
            output_schema=TwitterResult,
            callback=callback
        )
    
    def _initialize_agent(self):
        """Initialize Twitter-specific setup."""
        if self.verbose:
            print(f"🐦 Initializing Twitter Agent for user: {self.user_id}")
            print(f"🔑 Setting up Composio authentication...")
    
    def get_agent_description(self) -> str:
        """Return description of the Twitter agent."""
        return """AI agent specialized in Twitter/X platform operations. I can help you:
        - Post tweets and replies
        - Search for tweets and trending topics
        - Follow and unfollow users
        - Get user profile information
        - Analyze Twitter content and engagement
        
        I use Composio to securely access Twitter APIs with proper authentication."""
    
    def get_tools(self) -> List[Tool]:
        """Return the list of Twitter tools available to this agent."""
        try:
            # Get all available Twitter tools from Composio
            twitter_tools = self.composio.tools.get(user_id=self.user_id, toolkits=["TWITTER"])
            
            if self.verbose:
                print(f"📋 Found {len(twitter_tools)} Twitter tools from Composio")
            
            # Create TwitterTool instances from the Composio tool information
            tools = []
            for tool_info in twitter_tools:
                try:
                    twitter_tool = TwitterTool(self.composio, self.user_id, tool_info)
                    tools.append(twitter_tool)
                    
                    if self.verbose:
                        tool_name = tool_info.get("function", {}).get("name", "unknown")
                        print(f"  ✅ {tool_name}")
                        
                except Exception as e:
                    if self.verbose:
                        tool_name = tool_info.get("function", {}).get("name", "unknown")
                        print(f"  ❌ Failed to create tool {tool_name}: {e}")
            
            return tools
            
        except Exception as e:
            if self.verbose:
                print(f"⚠️  Error fetching Twitter tools from Composio: {e}")
            return []
    
    def check_twitter_connection(self) -> Dict[str, Any]:
        """
        Check if Twitter connection is active for the user.
        
        Returns:
            Dictionary with connection status
        """
        try:
            # Try to get tools to verify connection
            tools = self.composio.tools.get(user_id=self.user_id, toolkits=["TWITTER"])
            
            if tools:
                return {
                    "success": True,
                    "message": f"Twitter connection active with {len(tools)} tools available",
                    "tool_count": len(tools)
                }
            else:
                return {
                    "success": False,
                    "message": "No Twitter tools available - check connection setup"
                }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Error checking Twitter connection: {str(e)}"
            }
    

    
    def execute_twitter_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Convenience method to execute any Twitter tool directly.
        
        Args:
            tool_name: Name of the Composio Twitter tool (e.g., "TWITTER_POST_TWEET")
            **kwargs: Arguments for the tool
            
        Returns:
            Result of the tool execution
        """
        try:
            result = self.composio.tools.execute(
                tool_name,
                user_id=self.user_id,
                arguments=kwargs
            )
            
            return {
                "success": True,
                "result": f"Successfully executed {tool_name}",
                "details": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing {tool_name}: {str(e)}"
            }


def create_twitter_agent(user_id: str, composio_api_key: str = None, opper_api_key: str = None, verbose: bool = True) -> TwitterAgent:
    """
    Factory function to create a Twitter agent.
    
    Args:
        user_id: User ID for Composio authentication
        composio_api_key: API key for Composio (will use env var if not provided)
        opper_api_key: API key for Opper (will use env var if not provided)
        verbose: Whether to enable verbose logging
        
    Returns:
        Configured TwitterAgent instance
    """
    return TwitterAgent(
        user_id=user_id,
        composio_api_key=composio_api_key,
        opper_api_key=opper_api_key,
        verbose=verbose
    )


# Example usage
if __name__ == "__main__":
    import sys
    
    # Check environment variables first
    composio_key = os.getenv("COMPOSIO_API_KEY")
    opper_key = os.getenv("OPPER_API_KEY")
    
    if not composio_key:
        print("❌ COMPOSIO_API_KEY environment variable not set!")
        print("Please run: export COMPOSIO_API_KEY='your_key_here'")
        sys.exit(1)
    
    if not opper_key:
        print("❌ OPPER_API_KEY environment variable not set!")
        print("Please run: export OPPER_API_KEY='your_key_here'")
        sys.exit(1)
    
    
    # Get user ID from command line or use default
    user_id = sys.argv[1] if len(sys.argv) > 1 else "user@example.com"
    
    # Create the agent
    agent = create_twitter_agent(
        user_id=user_id, 
        composio_api_key=composio_key, 
        opper_api_key=opper_key,
        verbose=True
    )
    
    # Check Twitter connection status
    print("\n🔗 Checking Twitter connection...")
    connection_status = agent.check_twitter_connection()
    
    if connection_status["success"]:
        print(f"✅ {connection_status['message']}")
        
        # Example: Use the agent to perform a Twitter task
        result = agent.process("Post a timely tweet that is funny!")
        print(f"Agent result: {result}")
        
        
    else:
        print(f"❌ Connection issue: {connection_status.get('error', connection_status.get('message'))}")
        print("💡 Make sure you've set up Twitter authentication in Composio")
