"""
Deep Research Agent for comprehensive web research and analysis.
"""

import os
import re
import json
from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
import time

from base_agent import BaseAgent, Tool


def normalize_url(url: str) -> str:
    """Normalize URL to ensure it has a proper protocol."""
    if not url:
        return url
    
    if url.startswith('//'):
        return 'https:' + url
    elif url.startswith('/'):
        return 'https://duckduckgo.com' + url
    
    return url


class WebSearchTool(Tool):
    """Tool for performing web searches using DuckDuckGo Instant Answer API."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Search the web for information using DuckDuckGo search API",
            parameters={
                "query": "str - The search query to perform. Ideally targeting specific information that is needed.",
                "max_results": "int - Maximum number of results to return (default: 5)",
                "search_type": "str - Type of search: 'general', 'news', 'academic' (default: 'general')"
            }
        )
    
    def execute(self, _parent_span_id=None, query: str = None, max_results: int = 5, search_type: str = "general", **kwargs) -> Dict[str, Any]:
        """Perform a web search and return results."""
        try:
            if not query:
                return {
                    "success": False,
                    "error": "No search query provided"
                }
            
            # Use DuckDuckGo Instant Answer API (free, no key required)
            search_url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "pretty": "1",
                "no_redirect": "1",
                "no_html": "1",
                "skip_disambig": "1"
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(search_url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            results = []
            
            # Extract instant answer if available
            if data.get("Abstract"):
                results.append({
                    "title": data.get("Heading", "Instant Answer"),
                    "url": normalize_url(data.get("AbstractURL", "")),
                    "snippet": data.get("Abstract", ""),
                    "source": data.get("AbstractSource", "DuckDuckGo"),
                    "type": "instant_answer"
                })
            
            # Extract related topics
            for topic in data.get("RelatedTopics", [])[:max_results-len(results)]:
                if isinstance(topic, dict) and "Text" in topic:
                    results.append({
                        "title": topic.get("Result", topic.get("Text", ""))[:100] + "...",
                        "url": normalize_url(topic.get("FirstURL", "")),
                        "snippet": topic.get("Text", ""),
                        "source": "DuckDuckGo Related",
                        "type": "related_topic"
                    })
            
            # If we don't have enough results, try a different approach
            if len(results) < 2:
                # Fallback to simple web scraping approach
                try:
                    search_results = self._scrape_search_results(query, max_results)
                    results.extend(search_results)
                except Exception as e:
                    # If scraping fails, add at least a basic result
                    results.append({
                        "title": f"Search Results for: {query}",
                        "url": f"https://duckduckgo.com/?q={query.replace(' ', '+')}",
                        "snippet": f"Search performed for '{query}'. Consider using more specific terms or checking multiple sources.",
                        "source": "Search Engine",
                        "type": "search_link"
                    })
            
            return {
                "success": True,
                "query": query,
                "results": results[:max_results],
                "total_results": len(results),
                "search_type": search_type,
                "message": f"Found {len(results)} results for '{query}'"
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Network error during search: {str(e)}",
                "query": query
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Search failed: {str(e)}",
                "query": query
            }
    
    def _scrape_search_results(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        """Fallback method to scrape search results."""
        try:
            # This is a simple fallback - in production, you'd want to use proper search APIs
            search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            
            response = requests.get(search_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            
            # Extract search results (this is a simplified approach)
            for result in soup.find_all('div', class_='result')[:max_results]:
                title_elem = result.find('a', class_='result__a')
                snippet_elem = result.find('a', class_='result__snippet')
                
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    url = normalize_url(title_elem.get('href', ''))
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "source": urlparse(url).netloc if url else "Unknown",
                        "type": "web_result"
                    })
            
            return results
            
        except Exception as e:
            return []


class ContentAnalysisTool(Tool):
    """Tool for analyzing and summarizing web content."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, opper_client):
        super().__init__(
            name="analyze_content",
            description="Fetch and analyze content from web URLs, providing summaries and key insights",
            parameters={
                "url": "str - The URL to fetch and analyze",
                "analysis_type": "str - Type of analysis: 'summary', 'facts', 'key_points', 'comprehensive' (default: 'comprehensive')",
                "focus_area": "str - Specific area to focus analysis on (optional)"
            }
        )
        self.opper = opper_client
    
    def execute(self, _parent_span_id=None, url: str = None, analysis_type: str = "comprehensive", focus_area: str = "", **kwargs) -> Dict[str, Any]:
        """Fetch and analyze content from a URL."""
        try:
            if not url:
                return {
                    "success": False,
                    "error": "No URL provided for analysis"
                }
            
            # Fetch the content
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # Parse the content
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Extract text content
            text = soup.get_text()
            
            # Clean up the text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Limit text length for AI processing
            if len(text) > 8000:
                text = text[:8000] + "..."
            
            # Extract title
            title_elem = soup.find('title')
            title = title_elem.get_text(strip=True) if title_elem else "No title found"
            
            # Prepare AI analysis
            analysis_instructions = self._get_analysis_instructions(analysis_type, focus_area)
            
            input_data = {
                "url": url,
                "title": title,
                "content": text,
                "analysis_type": analysis_type,
                "focus_area": focus_area
            }
            
            # Call AI for content analysis with proper tracing
            ai_response = self.make_ai_call(
                opper_client=self.opper,
                name="analyze_web_content",
                instructions=analysis_instructions,
                input_data=input_data,
                parent_span_id=_parent_span_id,
                model="openai/gpt-5-mini"
            )
            
            # Extract analysis result
            if hasattr(ai_response, 'message') and hasattr(ai_response.message, 'content'):
                analysis_result = ai_response.message.content
            elif hasattr(ai_response, 'content'):
                analysis_result = ai_response.content
            else:
                analysis_result = str(ai_response)
            
            return {
                "success": True,
                "url": url,
                "title": title,
                "content_length": len(text),
                "analysis_type": analysis_type,
                "analysis": analysis_result,
                "focus_area": focus_area if focus_area else "general",
                "message": f"Successfully analyzed content from {urlparse(url).netloc}"
            }
            
        except requests.RequestException as e:
            return {
                "success": False,
                "error": f"Failed to fetch content from URL: {str(e)}",
                "url": url
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Content analysis failed: {str(e)}",
                "url": url
            }
    
    def _get_analysis_instructions(self, analysis_type: str, focus_area: str) -> str:
        """Get analysis instructions based on the type of analysis requested."""
        base_instruction = "You are a content analysis expert. Analyze the provided web content and provide insights."
        
        if analysis_type == "summary":
            return f"""{base_instruction}
            
            Provide a concise summary of the main content. Focus on:
            - Key topics and themes
            - Main arguments or findings
            - Important conclusions
            
            {f"Pay special attention to information related to: {focus_area}" if focus_area else ""}
            
            Keep the summary clear and factual."""
            
        elif analysis_type == "facts":
            return f"""{base_instruction}
            
            Extract key facts and data points from the content. Focus on:
            - Specific statistics, numbers, and data
            - Verifiable claims and statements
            - Important dates, names, and places
            - Research findings or study results
            
            {f"Prioritize facts related to: {focus_area}" if focus_area else ""}
            
            Present facts in a clear, organized manner."""
            
        elif analysis_type == "key_points":
            return f"""{base_instruction}
            
            Identify and extract the key points from the content. Focus on:
            - Main arguments or positions
            - Important conclusions or recommendations
            - Significant developments or changes
            - Critical insights or observations
            
            {f"Emphasize points related to: {focus_area}" if focus_area else ""}
            
            Organize the points in order of importance."""
            
        else:  # comprehensive
            return f"""{base_instruction}
            
            Provide a comprehensive analysis including:
            1. Summary of main content and themes
            2. Key facts and data points
            3. Important arguments or findings
            4. Notable quotes or statements
            5. Credibility assessment of the source
            6. Potential biases or limitations
            7. Relevance and reliability for research purposes
            
            {f"Pay special attention to aspects related to: {focus_area}" if focus_area else ""}
            
            Structure your analysis clearly with distinct sections."""


class FactVerificationTool(Tool):
    """Tool for verifying facts and cross-referencing information."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, opper_client):
        super().__init__(
            name="verify_facts",
            description="Verify facts by cross-referencing multiple sources and assessing credibility",
            parameters={
                "claim": "str - The claim or fact to verify",
                "sources": "list - List of source URLs or information to cross-reference (optional)",
                "verification_level": "str - Level of verification: 'basic', 'thorough', 'academic' (default: 'thorough')"
            }
        )
        self.opper = opper_client
    
    def execute(self, _parent_span_id=None, claim: str = None, sources: List[str] = None, verification_level: str = "thorough", **kwargs) -> Dict[str, Any]:
        """Verify a fact or claim by analyzing available sources."""
        try:
            if not claim:
                return {
                    "success": False,
                    "error": "No claim provided for verification"
                }
            
            sources = sources or []
            
            # Prepare verification instructions
            verification_instructions = self._get_verification_instructions(verification_level)
            
            input_data = {
                "claim": claim,
                "sources": sources,
                "verification_level": verification_level
            }
            
            # Call AI for fact verification with proper tracing
            ai_response = self.make_ai_call(
                opper_client=self.opper,
                name="verify_facts",
                instructions=verification_instructions,
                input_data=input_data,
                parent_span_id=_parent_span_id
            )
            
            # Extract verification result
            if hasattr(ai_response, 'message') and hasattr(ai_response.message, 'content'):
                verification_result = ai_response.message.content
            elif hasattr(ai_response, 'content'):
                verification_result = ai_response.content
            else:
                verification_result = str(ai_response)
            
            return {
                "success": True,
                "claim": claim,
                "verification_level": verification_level,
                "sources_checked": len(sources),
                "verification_result": verification_result,
                "message": f"Fact verification completed for claim about: {claim[:100]}..."
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Fact verification failed: {str(e)}",
                "claim": claim
            }
    
    def _get_verification_instructions(self, verification_level: str) -> str:
        """Get verification instructions based on the level of verification requested."""
        base_instruction = "You are a fact-checking expert. Analyze the provided claim and assess its accuracy."
        
        if verification_level == "basic":
            return f"""{base_instruction}
            
            Provide a basic fact-check assessment:
            - Is the claim plausible based on general knowledge?
            - Are there any obvious inconsistencies or red flags?
            - What is the general likelihood of accuracy?
            
            Provide a simple assessment: TRUE, FALSE, PARTIALLY TRUE, or INSUFFICIENT INFORMATION."""
            
        elif verification_level == "academic":
            return f"""{base_instruction}
            
            Provide an academic-level fact verification:
            - Assess the claim against established academic knowledge
            - Identify what types of sources would be needed for verification
            - Evaluate the specificity and verifiability of the claim
            - Consider the methodology that would be required to prove/disprove
            - Assess potential confounding factors or limitations
            
            Provide a detailed academic assessment with confidence levels and research recommendations."""
            
        else:  # thorough
            return f"""{base_instruction}
            
            Provide a thorough fact-checking analysis:
            1. Break down the claim into verifiable components
            2. Assess each component for accuracy and consistency
            3. Identify what evidence would support or refute the claim
            4. Consider alternative explanations or interpretations
            5. Evaluate the credibility and reliability of any sources
            6. Provide an overall assessment with confidence level
            7. Suggest additional verification steps if needed
            
            Structure your analysis clearly and provide a final verdict: TRUE, FALSE, PARTIALLY TRUE, or NEEDS MORE RESEARCH."""


class ResearchSynthesisTool(Tool):
    """Tool for synthesizing research findings into comprehensive reports."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, opper_client):
        super().__init__(
            name="synthesize_research",
            description="Synthesize multiple research findings into a comprehensive report",
            parameters={
                "research_data": "dict - Dictionary containing research findings from various sources",
                "research_question": "str - The main research question or topic",
                "report_style": "str - Style of report: 'executive_summary', 'academic', 'comprehensive', 'brief' (default: 'comprehensive')"
            }
        )
        self.opper = opper_client
    
    def execute(self, _parent_span_id=None, research_data: Dict = None, research_question: str = None, report_style: str = "comprehensive", **kwargs) -> Dict[str, Any]:
        """Synthesize research data into a comprehensive report."""
        try:
            if not research_data:
                return {
                    "success": False,
                    "error": "No research data provided for synthesis"
                }
            
            if not research_question:
                research_question = "General research synthesis"
            
            # Prepare synthesis instructions
            synthesis_instructions = self._get_synthesis_instructions(report_style)
            
            input_data = {
                "research_data": research_data,
                "research_question": research_question,
                "report_style": report_style
            }
            
            # Call AI for research synthesis with proper tracing
            ai_response = self.make_ai_call(
                opper_client=self.opper,
                name="synthesize_research_findings",
                instructions=synthesis_instructions,
                input_data=input_data,
                parent_span_id=_parent_span_id,
                model="openai/gpt-5-mini"
            )
            
            # Extract synthesis result
            if hasattr(ai_response, 'message') and hasattr(ai_response.message, 'content'):
                synthesis_result = ai_response.message.content
            elif hasattr(ai_response, 'content'):
                synthesis_result = ai_response.content
            else:
                synthesis_result = str(ai_response)
            
            return {
                "success": True,
                "research_question": research_question,
                "report_style": report_style,
                "sources_synthesized": len(research_data),
                "synthesis_report": synthesis_result,
                "message": f"Research synthesis completed for: {research_question}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Research synthesis failed: {str(e)}",
                "research_question": research_question
            }
    
    def _get_synthesis_instructions(self, report_style: str) -> str:
        """Get synthesis instructions based on the report style."""
        base_instruction = "You are a research synthesis expert. Analyze the provided research data and create a comprehensive report."
        
        if report_style == "executive_summary":
            return f"""{base_instruction}
            
            Create an executive summary that includes:
            - Key findings and conclusions (bullet points)
            - Main insights and trends identified
            - Recommendations based on the research
            - Confidence levels for major conclusions
            - Areas requiring further research
            
            Keep it concise and actionable for decision-makers."""
            
        elif report_style == "academic":
            return f"""{base_instruction}
            
            Create an academic-style research synthesis:
            - Introduction and research methodology
            - Literature review of sources
            - Analysis of findings with critical evaluation
            - Discussion of limitations and biases
            - Conclusions and implications
            - Recommendations for future research
            
            Use formal academic language and structure."""
            
        elif report_style == "brief":
            return f"""{base_instruction}
            
            Create a brief research summary:
            - Main question and approach
            - Top 3-5 key findings
            - Overall conclusion
            - Confidence level
            
            Keep it concise and focused on the most important insights."""
            
        else:  # comprehensive
            return f"""{base_instruction}
            
            Create a comprehensive research report including:
            1. Executive Summary
            2. Research Overview and Methodology
            3. Detailed Findings by Source/Topic
            4. Cross-Analysis and Pattern Identification
            5. Credibility Assessment of Sources
            6. Conflicting Information and Limitations
            7. Conclusions and Confidence Levels
            8. Recommendations and Next Steps
            
            Structure the report clearly with headings and provide balanced analysis."""


class ResearchTaskInput(BaseModel):
    """Input schema for research tasks."""
    research_question: str = Field(description="The research question or topic to investigate")
    depth: str = Field(default="comprehensive", description="Research depth: 'basic', 'comprehensive', 'exhaustive'")
    focus_areas: List[str] = Field(default=[], description="Specific areas or aspects to focus on")
    sources_preference: str = Field(default="mixed", description="Source preference: 'academic', 'news', 'mixed', 'government'")


class ResearchResult(BaseModel):
    """Output schema for research results."""
    research_question: str = Field(description="The original research question")
    executive_summary: str = Field(description="Executive summary of key findings")
    key_findings: List[str] = Field(description="List of key findings and insights")
    sources_analyzed: int = Field(description="Number of sources analyzed")
    credibility_assessment: str = Field(description="Overall assessment of source credibility")
    fact_verification: str = Field(description="Summary of fact verification results")
    conflicting_information: List[str] = Field(description="Any conflicting information found")
    confidence_level: str = Field(description="Confidence level in the findings: 'high', 'medium', 'low'")
    limitations: List[str] = Field(description="Limitations of the research")
    recommendations: List[str] = Field(description="Recommendations for further research or action")
    detailed_report: str = Field(description="Comprehensive detailed report")
    sources_used: List[str] = Field(description="List of sources used in the research")


def print_research_status(event_type: str, data: dict):
    """
    Callback for printing research agent status updates.
    """
    if event_type == "goal_start":
        print(f"🔍 Research Agent: {data.get('agent_name')}")
        print(f"📋 Research Goal: {data.get('goal')}")
        available_tools = data.get('available_tools', [])
        print(f"🛠️  Available Tools: {', '.join(available_tools)}")
    elif event_type == "thought_created":
        user_message = data.get("thought", {}).get("user_message", "")
        if user_message:
            print(f"💭 {user_message}")


def main():
    """Example usage of the ResearchAgent."""
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
        return
    
    try:
        description = """An AI agent that performs comprehensive deep research on any topic by:
- Conducting web searches to find relevant information
- Analyzing content from multiple sources
- Verifying facts and cross-referencing information
- Synthesizing findings into comprehensive reports
- Assessing source credibility and reliability
- Identifying knowledge gaps and areas for further research"""

        # Create Opper client for tools that need it
        from opperai import Opper
        opper_client = Opper(http_bearer=api_key)
        
        # Create research tools
        web_search_tool = WebSearchTool()
        content_analysis_tool = ContentAnalysisTool(opper_client)
        fact_verification_tool = FactVerificationTool(opper_client)
        research_synthesis_tool = ResearchSynthesisTool(opper_client)
        
        research_tools = [
            web_search_tool,
            content_analysis_tool,
            fact_verification_tool,
            research_synthesis_tool
        ]
        
        agent = BaseAgent(
            name="DeepResearchAgent",
            opper_api_key=api_key,
            callback=print_research_status,
            verbose=False,
            output_schema=ResearchResult,
            tools=research_tools,
            description=description,
            max_iterations=15
        )

        research_question = "Tell me everything you can find about Opper AI"

        print(f"🎯 Starting research on: {research_question}")
        result = agent.process(research_question)
        
        if isinstance(result, dict):
            print(f"\n📊 Research Results:")
            print(f"   Research Question: {result.get('research_question', 'N/A')}")
            print(f"   Sources Analyzed: {result.get('sources_analyzed', 0)}")
            print(f"   Confidence Level: {result.get('confidence_level', 'Unknown')}")
            print(f"   Key Findings: {len(result.get('key_findings', []))}")
            
            if result.get('executive_summary'):
                print(f"\n📋 Executive Summary:")
                print(f"   {result['executive_summary'][:200]}...")
            
            if result.get('recommendations'):
                print(f"\n💡 Recommendations:")
                for i, rec in enumerate(result.get('recommendations', [])[:3], 1):
                    print(f"   {i}. {rec}")
        
    except Exception as e:
        print(f"❌ Error running research agent: {e}")
        print("This might be due to:")
        print("- Invalid API key")
        print("- Network connectivity issues")
        print("- Missing dependencies")


if __name__ == "__main__":
    main()
