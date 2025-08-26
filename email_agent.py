"""
Email agent for managing Gmail tasks using the Opper base agent framework.
"""

import os
import base64
import json
import re
from typing import Any, List, Dict, Optional, ClassVar
from pydantic import BaseModel, Field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from base_agent import BaseAgent, Tool


def extract_email_address(from_header: str) -> str:
    """
    Extract clean email address from From header.
    Handles formats like:
    - "Display Name" <email@domain.com>
    - Display Name <email@domain.com>
    - email@domain.com
    """
    if not from_header:
        return ""
    
    # Look for email in angle brackets first
    match = re.search(r'<([^>]+)>', from_header)
    if match:
        return match.group(1).strip()
    
    # If no angle brackets, check if the entire string is an email
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(email_pattern, from_header.strip()):
        return from_header.strip()
    
    # Fallback: return the original if we can't parse it
    return from_header


class EmailMessage(BaseModel):
    """Represents an email message."""
    id: str = Field(description="Gmail message ID")
    subject: str = Field(description="Email subject")
    sender: str = Field(description="Email sender")
    body: str = Field(description="Full email body")
    thread_id: str = Field(description="Gmail thread ID")


class DraftReply(BaseModel):
    """Represents a draft reply."""
    message_id: str = Field(description="ID of the original message being replied to")
    reply_content: str = Field(description="Generated reply content")
    subject: str = Field(description="Reply subject")
    recipient: str = Field(description="Reply recipient")


class EmailAnalysis(BaseModel):
    """Structured output for email reply analysis and generation."""
    email_category: str = Field(description="Category of the email (e.g., 'meeting_request', 'project_update', 'question', 'complaint', 'sales_inquiry', 'support_request', 'social', 'other')")
    needs_reply: bool = Field(description="Whether this email requires a reply")
    reply: Optional[str] = Field(description="The generated reply content if needs_reply is True, otherwise None")


class EmailReadAnalysis(BaseModel):
    """Comprehensive analysis of an email including categorization, labeling, and reply assessment."""
    email_category: str = Field(description="Category of the email (e.g., 'meeting_request', 'project_update', 'question', 'complaint', 'sales_inquiry', 'support_request', 'social', 'newsletter', 'promotion', 'personal', 'urgent', 'other')")
    suggested_labels: List[str] = Field(description="Suggested Gmail labels/tags for this email (e.g., ['work', 'urgent', 'follow-up'])")
    priority_level: str = Field(description="Priority level: 'low', 'medium', 'high', or 'urgent'")
    needs_reply: bool = Field(description="Whether this email requires a reply")
    reply_urgency: str = Field(description="How urgent the reply is: 'immediate', 'within_day', 'within_week', 'not_urgent' or 'no_reply_needed'")
    potential_reply: Optional[str] = Field(description="Suggested reply content if needs_reply is True, otherwise None")
    action_items: List[str] = Field(description="List of action items extracted from the email")
    sentiment: str = Field(description="Overall sentiment: 'positive', 'neutral', 'negative', or 'mixed'")
    key_points: List[str] = Field(description="Key points or topics mentioned in the email")


class GmailAuthTool(Tool):
    """Tool for authenticating with Gmail API."""
    
    # Class-level constant for Gmail API scopes
    SCOPES: ClassVar[List[str]] = ['https://www.googleapis.com/auth/gmail.modify']
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self):
        super().__init__(
            name="gmail_auth",
            description="Authenticate with Gmail API and return service object",
            parameters={
                "credentials_file": "str - Path to OAuth credentials JSON file (default: 'credentials.json')",
                "token_file": "str - Path to store token file (default: 'token.json')"
            }
        )
        self.service = None
    
    def execute(self, _parent_span_id=None, credentials_file: str = "credentials.json", token_file: str = "token.json", **kwargs) -> Dict[str, Any]:
        """Authenticate with Gmail API."""
        try:
            creds = None
            
            # Load existing token if available
            if os.path.exists(token_file):
                creds = Credentials.from_authorized_user_file(token_file, GmailAuthTool.SCOPES)
            
            # If no valid credentials, get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(credentials_file):
                        return {
                            "success": False,
                            "error": f"Credentials file '{credentials_file}' not found. Please download OAuth credentials from Google Cloud Console."
                        }
                    
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, GmailAuthTool.SCOPES)
                    # Try different ports in case of conflicts
                    try:
                        creds = flow.run_local_server(port=8080)
                    except Exception:
                        try:
                            creds = flow.run_local_server(port=8081)
                        except Exception:
                            creds = flow.run_local_server(port=0)
                
                # Save credentials for next run
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
            
            # Build service
            self.service = build('gmail', 'v1', credentials=creds)
            
            return {
                "success": True,
                "message": "Successfully authenticated with Gmail API"
            }
            
        except Exception as e:
            error_msg = str(e)
            if "OAuth 2.0 policy" in error_msg or "redirect_uri" in error_msg:
                return {
                    "success": False,
                    "error": f"OAuth setup issue: {error_msg}",
                    "help": "Please check GMAIL_SETUP.md for detailed setup instructions. You need to configure OAuth consent screen and add proper redirect URIs in Google Cloud Console."
                }
            else:
                return {
                    "success": False,
                    "error": f"Authentication failed: {error_msg}"
                }


class ListEmailsTool(Tool):
    """Tool for listing emails from Gmail with basic information."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, gmail_auth_tool: GmailAuthTool):
        super().__init__(
            name="list_emails",
            description="List emails from Gmail with basic information (subject, sender, date, etc.)",
            parameters={
                "max_results": "int - Maximum number of emails to fetch (default: 10)",
                "query": "str - Gmail search query filters (e.g., 'is:inbox', 'is:unread', 'from:example@email.com', default: 'is:inbox')",
                "include_body": "bool - Whether to include email body content (default: False for performance)"
            }
        )
        self.gmail_auth_tool = gmail_auth_tool
    
    def execute(self, _parent_span_id=None, max_results: int = 10, query: str = "is:inbox", include_body: bool = False, **kwargs) -> Dict[str, Any]:
        """List emails from Gmail."""
        try:
            if not self.gmail_auth_tool.service:
                auth_result = self.gmail_auth_tool.execute()
                if not auth_result["success"]:
                    return auth_result
            
            service = self.gmail_auth_tool.service
            
            # Fetch message list
            results = service.users().messages().list(
                userId='me', 
                q=query, 
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return {
                    "success": True,
                    "emails": [],
                    "message": f"No emails found matching query: {query}"
                }
            
            # Fetch email details
            email_list = []
            for message in messages:
                msg = service.users().messages().get(
                    userId='me', 
                    id=message['id'], 
                    format='full'
                ).execute()
                
                # Extract email details
                headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
                subject = headers.get('Subject', 'No Subject')
                sender = headers.get('From', 'Unknown Sender')
                date = headers.get('Date', 'Unknown Date')
                
                email_info = {
                    "id": message['id'],
                    "thread_id": msg['threadId'],
                    "subject": subject,
                    "sender": sender,
                    "date": date,
                    "snippet": msg.get('snippet', ''),
                    "labels": msg.get('labelIds', [])
                }
                
                # Include body if requested
                if include_body:
                    email_info["body"] = self._extract_email_body(msg['payload'])
                
                email_list.append(email_info)
            
            return {
                "success": True,
                "emails": email_list,
                "count": len(email_list),
                "query_used": query
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to list emails: {str(e)}"
            }
    
    def _extract_email_body(self, payload: Dict) -> str:
        """Extract email body from message payload."""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif part['mimeType'] == 'text/html' and not body:
                    # Fallback to HTML if no plain text
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            # Single part message
            if payload['mimeType'] == 'text/plain':
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        return body.strip()


class ReadEmailTool(Tool):
    """Tool for reading and analyzing an email with comprehensive categorization and assessment."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, gmail_auth_tool: GmailAuthTool, opper_client):
        super().__init__(
            name="read_email",
            description="Read and analyze an email, providing categorization, potential labels, reply necessity assessment, and potential reply content",
            parameters={
                "message_id": "str - Gmail message ID to analyze",
                "context": "str - Additional context about the user/organization for better analysis (optional)",
                "tone": "str - Desired tone for potential reply (professional, friendly, casual, etc.) - default: professional"
            }
        )
        self.gmail_auth_tool = gmail_auth_tool
        self.opper = opper_client
    
    def execute(self, _parent_span_id=None, message_id: str = None, context: str = "", tone: str = "professional", **kwargs) -> Dict[str, Any]:
        """Read and analyze an email comprehensively."""
        try:
            if not self.gmail_auth_tool.service:
                auth_result = self.gmail_auth_tool.execute()
                if not auth_result["success"]:
                    return auth_result
            
            service = self.gmail_auth_tool.service
            
            # Get the email message
            msg = service.users().messages().get(
                userId='me', 
                id=message_id, 
                format='full'
            ).execute()
            
            # Extract email details
            headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
            subject = headers.get('Subject', 'No Subject')
            sender = headers.get('From', 'Unknown Sender')
            date = headers.get('Date', 'Unknown Date')
            
            # Extract email body
            body = self._extract_email_body(msg['payload'])
            
            # Create full email content for analysis
            email_content = f"""
Subject: {subject}
From: {sender}
Date: {date}

{body}
"""
            
            # Prepare AI analysis prompt
            ai_instructions = f"""
You are an email analysis expert. Analyze the provided email and provide comprehensive categorization and assessment.

Your task is to:
1. Categorize the email appropriately
2. Suggest relevant Gmail labels/tags
3. Assess priority level
4. Determine if a reply is needed and urgency
5. Generate potential reply content if needed
6. Extract action items
7. Assess sentiment
8. Identify key points

Email Analysis Guidelines:
- Categories: meeting_request, project_update, question, complaint, sales_inquiry, support_request, social, newsletter, promotion, personal, urgent, other
- Labels: Use practical Gmail labels like 'work', 'personal', 'urgent', 'follow-up', 'to-read', 'important', 'travel', 'finance', etc.
- Priority: Consider deadline urgency, sender importance, and content impact
- Reply Assessment: Consider if sender expects response, question asked, action required
- Tone for replies: Use {tone} tone
- Action Items: Extract specific tasks, deadlines, or follow-ups mentioned
- Sentiment: Overall emotional tone of the email
- Key Points: Main topics, decisions, or information mentioned

Additional context: {context if context else "No additional context provided"}

Provide structured analysis with all requested fields.
"""
            
            # Prepare input data for AI analysis
            input_data = {
                "email_content": email_content,
                "subject": subject,
                "sender": sender,
                "date": date,
                "tone": tone,
                "context": context
            }
            
            # Call AI for comprehensive email analysis with proper tracing
            ai_response = self.make_ai_call(
                opper_client=self.opper,
                name="analyze_email",
                instructions=ai_instructions,
                input_data=input_data,
                output_schema=EmailReadAnalysis,
                parent_span_id=_parent_span_id
            )
            
            # Extract the structured analysis
            if hasattr(ai_response, 'json_payload') and ai_response.json_payload:
                analysis = EmailReadAnalysis(**ai_response.json_payload)
            elif isinstance(ai_response, dict):
                analysis = EmailReadAnalysis(**ai_response)
            else:
                # Fallback analysis if AI response format is unexpected
                analysis = EmailReadAnalysis(
                    email_category="other",
                    suggested_labels=["to-review"],
                    priority_level="medium",
                    needs_reply=False,
                    reply_urgency="not_urgent",
                    potential_reply=None,
                    action_items=[],
                    sentiment="neutral",
                    key_points=["Email analysis unavailable"]
                )
            
            return {
                "success": True,
                "message_id": message_id,
                "email_info": {
                    "subject": subject,
                    "sender": sender,
                    "date": date,
                    "thread_id": msg['threadId'],
                    "snippet": msg.get('snippet', '')
                },
                "analysis": {
                    "category": analysis.email_category,
                    "suggested_labels": analysis.suggested_labels,
                    "priority_level": analysis.priority_level,
                    "needs_reply": analysis.needs_reply,
                    "reply_urgency": analysis.reply_urgency,
                    "potential_reply": analysis.potential_reply,
                    "action_items": analysis.action_items,
                    "sentiment": analysis.sentiment,
                    "key_points": analysis.key_points
                },
                "full_content": email_content if len(body) < 2000 else email_content[:2000] + "...",
                "message": "Email analysis completed successfully"
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to analyze email: {str(e)}"
            }
    
    def _extract_email_body(self, payload: Dict) -> str:
        """Extract email body from message payload."""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif part['mimeType'] == 'text/html' and not body:
                    # Fallback to HTML if no plain text
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            # Single part message
            if payload['mimeType'] == 'text/plain':
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        return body.strip()


class FetchUnrepliedEmailsTool(Tool):
    """Tool for fetching unreplied emails from Gmail."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, gmail_auth_tool: GmailAuthTool):
        super().__init__(
            name="fetch_unreplied_emails",
            description="Fetch unreplied emails from Gmail inbox",
            parameters={
                "max_results": "int - Maximum number of emails to fetch (default: 5)",
                "query": "str - Additional Gmail search query filters (optional)"
            }
        )
        self.gmail_auth_tool = gmail_auth_tool
    
    def execute(self, _parent_span_id=None, max_results: int = 5, query: str = "", **kwargs) -> Dict[str, Any]:
        """Fetch unreplied emails from Gmail."""
        try:
            if not self.gmail_auth_tool.service:
                auth_result = self.gmail_auth_tool.execute()
                if not auth_result["success"]:
                    return auth_result
            
            service = self.gmail_auth_tool.service
            
            # Build search query for unreplied emails
            base_query = "is:inbox -in:chats -from:me -is:sent"
            if query:
                search_query = f"{base_query} {query}"
            else:
                search_query = base_query
            
            # Fetch message list
            results = service.users().messages().list(
                userId='me', 
                q=search_query, 
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            if not messages:
                return {
                    "success": True,
                    "emails": [],
                    "message": "No unreplied emails found"
                }
            
            # Fetch full message details
            email_details = []
            for message in messages:
                msg = service.users().messages().get(
                    userId='me', 
                    id=message['id'], 
                    format='full'
                ).execute()
                
                # Extract email details
                headers = {h['name']: h['value'] for h in msg['payload'].get('headers', [])}
                subject = headers.get('Subject', 'No Subject')
                sender = headers.get('From', 'Unknown Sender')
                
                # Extract email body
                body = self._extract_email_body(msg['payload'])
                
                email_details.append(EmailMessage(
                    id=message['id'],
                    subject=subject,
                    sender=sender,
                    body=body,
                    thread_id=msg['threadId']
                ))
            
            return {
                "success": True,
                "emails": [email.model_dump() for email in email_details],
                "count": len(email_details)
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch emails: {str(e)}"
            }
    
    def _extract_email_body(self, payload: Dict) -> str:
        """Extract email body from message payload."""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                elif part['mimeType'] == 'text/html' and not body:
                    # Fallback to HTML if no plain text
                    data = part['body'].get('data', '')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        else:
            # Single part message
            if payload['mimeType'] == 'text/plain':
                data = payload['body'].get('data', '')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
        
        return body.strip()


class CreateDraftReplyTool(Tool):
    """Tool for creating draft replies to emails."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, gmail_auth_tool: GmailAuthTool):
        super().__init__(
            name="create_draft_reply",
            description="Create a draft reply to an email",
            parameters={
                "message_id": "str - ID of the original message to reply to",
                "reply_content": "str - Content of the reply",
                "additional_recipients": "str - Additional recipients (optional, comma-separated)"
            }
        )
        self.gmail_auth_tool = gmail_auth_tool
    
    def execute(self, _parent_span_id=None, message_id: str = None, reply_content: str = None, additional_recipients: str = "", **kwargs) -> Dict[str, Any]:
        """Create a draft reply to an email."""
        try:
            # Handle both old and new calling conventions
            if message_id is None:
                message_id = kwargs.get('message_id', '')
            if reply_content is None:
                reply_content = kwargs.get('reply_content', '')
                
            if not self.gmail_auth_tool.service:
                auth_result = self.gmail_auth_tool.execute()
                if not auth_result["success"]:
                    return auth_result
            
            service = self.gmail_auth_tool.service
            
            # Get original message
            original_message = service.users().messages().get(
                userId='me', 
                id=message_id, 
                format='full'
            ).execute()
            
            headers = {h['name']: h['value'] for h in original_message['payload'].get('headers', [])}
            original_subject = headers.get('Subject', '')
            sender_raw = headers.get('From', '')
            sender_email = extract_email_address(sender_raw)
            message_id_header = headers.get('Message-ID', '')
            
            # Create reply subject
            reply_subject = original_subject
            if not reply_subject.startswith('Re:'):
                reply_subject = f"Re: {reply_subject}"
            
            # Create reply message
            reply_message = MIMEMultipart()
            reply_message['To'] = sender_email
            
            if additional_recipients:
                reply_message['Cc'] = additional_recipients
            
            reply_message['Subject'] = reply_subject
            
            # Add reference headers for threading
            if message_id_header:
                reply_message['In-Reply-To'] = message_id_header
                reply_message['References'] = message_id_header
            
            # Add body
            reply_message.attach(MIMEText(reply_content, 'plain'))
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(reply_message.as_bytes()).decode('utf-8')
            
            # Create draft
            draft_body = {
                'message': {
                    'raw': raw_message,
                    'threadId': original_message['threadId']
                }
            }
            
            draft = service.users().drafts().create(
                userId='me', 
                body=draft_body
            ).execute()
            
            return {
                "success": True,
                "draft_id": draft['id'],
                "message": f"Draft reply created successfully for message: {original_subject}",
                "reply_to": sender_email,
                "subject": reply_subject
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create draft reply: {str(e)}"
            }


class AddDraftResponseTool(Tool):
    """Tool for adding a draft response to an email thread."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, gmail_auth_tool: GmailAuthTool):
        super().__init__(
            name="add_draft_response",
            description="Create a draft response/reply to a specific email",
            parameters={
                "message_id": "str - ID of the original message to reply to",
                "response_content": "str - Content of the draft response",
                "additional_recipients": "str - Additional recipients to include (optional, comma-separated emails)",
                "custom_subject": "str - Custom subject line (optional, will use 'Re: original subject' if not provided)"
            }
        )
        self.gmail_auth_tool = gmail_auth_tool
    
    def execute(self, _parent_span_id=None, message_id: str = None, response_content: str = None, additional_recipients: str = "", custom_subject: str = "", **kwargs) -> Dict[str, Any]:
        """Create a draft response to an email."""
        try:
            if not self.gmail_auth_tool.service:
                auth_result = self.gmail_auth_tool.execute()
                if not auth_result["success"]:
                    return auth_result
            
            service = self.gmail_auth_tool.service
            
            # Get original message
            original_message = service.users().messages().get(
                userId='me', 
                id=message_id, 
                format='full'
            ).execute()
            
            headers = {h['name']: h['value'] for h in original_message['payload'].get('headers', [])}
            original_subject = headers.get('Subject', '')
            sender_raw = headers.get('From', '')
            sender_email = extract_email_address(sender_raw)
            message_id_header = headers.get('Message-ID', '')
            
            # Create response subject
            if custom_subject:
                response_subject = custom_subject
            else:
                response_subject = original_subject
                if not response_subject.startswith('Re:'):
                    response_subject = f"Re: {response_subject}"
            
            # Create response message
            response_message = MIMEMultipart()
            response_message['To'] = sender_email
            
            if additional_recipients:
                response_message['Cc'] = additional_recipients
            
            response_message['Subject'] = response_subject
            
            # Add reference headers for threading
            if message_id_header:
                response_message['In-Reply-To'] = message_id_header
                response_message['References'] = message_id_header
            
            # Add body
            response_message.attach(MIMEText(response_content, 'plain'))
            
            # Encode message
            raw_message = base64.urlsafe_b64encode(response_message.as_bytes()).decode('utf-8')
            
            # Create draft
            draft_body = {
                'message': {
                    'raw': raw_message,
                    'threadId': original_message['threadId']
                }
            }
            
            draft = service.users().drafts().create(
                userId='me', 
                body=draft_body
            ).execute()
            
            return {
                "success": True,
                "draft_id": draft['id'],
                "message_id": draft['message']['id'],
                "thread_id": original_message['threadId'],
                "subject": response_subject,
                "to": sender_email,
                "cc": additional_recipients if additional_recipients else None,
                "message": f"Draft response created successfully for: {original_subject}"
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to create draft response: {str(e)}"
            }


class GenerateReplyContentTool(Tool):
    """Tool for generating reply content using AI."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, opper_client):
        super().__init__(
            name="generate_reply_content",
            description="Analyze an email and generate structured output including category, reply necessity, and optional reply content",
            parameters={
                "original_email": "str - The full original email content to analyze",
                "sender_name": "str - Name of the original sender",
                "context": "str - Additional context for generating the reply (optional)",
                "tone": "str - Desired tone for the reply (professional, friendly, casual, etc.) - default: professional"
            }
        )
        self.opper = opper_client
    
    def execute(self, _parent_span_id=None, original_email: str = None, sender_name: str = None, context: str = "", tone: str = "professional", **kwargs) -> Dict[str, Any]:
        """Generate reply content for an email using AI."""
        try:
            # Handle both old and new calling conventions
            if original_email is None:
                original_email = kwargs.get('original_email', '')
            if sender_name is None:
                sender_name = kwargs.get('sender_name', '')
            
            # Prepare the AI prompt for structured email analysis
            ai_instructions = f"""
You are an AI assistant that analyzes emails and generates replies when appropriate.

Your task is to:
1. Categorize the email into one of these categories: 'meeting_request', 'project_update', 'question', 'complaint', 'sales_inquiry', 'support_request', 'social', 'other'
2. Determine if the email needs a reply
3. If it needs a reply, generate an appropriate response

Email reply guidelines (when generating replies):
- Use a {tone} tone
- Be helpful and responsive to the sender's needs
- Keep the reply concise but complete
- Address the main points from the original email
- Use proper email etiquette
- Personalize the greeting using the sender's name
- Do not include placeholder text like [Your Name] - leave signature lines generic
- If specific information is requested that you cannot provide, politely indicate that you'll need to research it

Additional context to consider: {context if context else "No additional context provided"}

Analyze the email and provide structured output with:
- email_category: The category of the email
- needs_reply: Whether this email requires a response
- reply: The generated reply content (only if needs_reply is true, otherwise null)
"""
            
            # Prepare input data for the AI
            input_data = {
                "original_email": original_email,
                "sender_name": sender_name,
                "tone": tone,
                "context": context
            }
            
            # Call the AI to analyze the email and generate reply with proper tracing
            ai_response = self.make_ai_call(
                opper_client=self.opper,
                name="email_reply_generator",
                instructions=ai_instructions,
                input_data=input_data,
                output_schema=EmailAnalysis,
                parent_span_id=_parent_span_id
            )
            
            # Extract the structured analysis
            if hasattr(ai_response, 'json_payload') and ai_response.json_payload:
                analysis = EmailAnalysis(**ai_response.json_payload)
            elif isinstance(ai_response, dict):
                analysis = EmailAnalysis(**ai_response)
            else:
                # Fallback if AI response format is unexpected
                analysis = EmailAnalysis(
                    email_category="other",
                    needs_reply=True,
                    reply=str(ai_response)
                )
            
            return {
                "success": True,
                "email_category": analysis.email_category,
                "needs_reply": analysis.needs_reply,
                "reply_content": analysis.reply if analysis.reply else None,
                "message": "Email analysis completed successfully",
                "tone_used": tone
            }
            
        except Exception as e:
            # Fallback to a simple template if AI generation fails
            sender_first_name = sender_name.split()[0] if sender_name else "there"
            if '<' in sender_first_name:
                sender_first_name = sender_first_name.split('<')[0].strip()
            
            fallback_reply = f"""Hi {sender_first_name},

Thank you for your email. I've received your message and will review it carefully.

{context if context else "I'll get back to you soon with a detailed response."}

Best regards"""
            
            return {
                "success": True,
                "email_category": "other",
                "needs_reply": True,
                "reply_content": fallback_reply,
                "message": f"AI generation failed ({str(e)}), used fallback template",
                "tone_used": tone,
                "fallback_used": True
            }


class AddEmailTagTool(Tool):
    """Tool for adding labels/tags to Gmail messages."""
    
    # Configure Pydantic to allow extra fields
    model_config = {"extra": "allow"}
    
    def __init__(self, gmail_auth_tool: GmailAuthTool):
        super().__init__(
            name="add_email_tag",
            description="Add labels/tags to a Gmail message",
            parameters={
                "message_id": "str - Gmail message ID to add labels to",
                "labels": "list - List of label names to add (e.g., ['work', 'urgent', 'follow-up'])",
                "create_if_missing": "bool - Whether to create labels if they don't exist (default: True)"
            }
        )
        self.gmail_auth_tool = gmail_auth_tool
    
    def execute(self, _parent_span_id=None, message_id: str = None, labels: List[str] = None, create_if_missing: bool = True, **kwargs) -> Dict[str, Any]:
        """Add labels/tags to a Gmail message."""
        try:
            if not self.gmail_auth_tool.service:
                auth_result = self.gmail_auth_tool.execute()
                if not auth_result["success"]:
                    return auth_result
            
            service = self.gmail_auth_tool.service
            
            if not labels:
                return {
                    "success": False,
                    "error": "No labels provided to add"
                }
            
            # Get existing labels to check which ones exist
            existing_labels = service.users().labels().list(userId='me').execute()
            existing_label_names = {label['name']: label['id'] for label in existing_labels.get('labels', [])}
            
            label_ids_to_add = []
            labels_added = []
            labels_created = []
            
            for label_name in labels:
                if label_name in existing_label_names:
                    # Label exists, use its ID
                    label_ids_to_add.append(existing_label_names[label_name])
                    labels_added.append(label_name)
                elif create_if_missing:
                    # Create new label
                    try:
                        new_label = service.users().labels().create(
                            userId='me',
                            body={
                                'name': label_name,
                                'labelListVisibility': 'labelShow',
                                'messageListVisibility': 'show'
                            }
                        ).execute()
                        label_ids_to_add.append(new_label['id'])
                        labels_added.append(label_name)
                        labels_created.append(label_name)
                    except HttpError as e:
                        if "already exists" in str(e).lower():
                            # Label was created by another request, try to get it
                            updated_labels = service.users().labels().list(userId='me').execute()
                            updated_label_names = {label['name']: label['id'] for label in updated_labels.get('labels', [])}
                            if label_name in updated_label_names:
                                label_ids_to_add.append(updated_label_names[label_name])
                                labels_added.append(label_name)
                        else:
                            return {
                                "success": False,
                                "error": f"Failed to create label '{label_name}': {str(e)}"
                            }
                else:
                    return {
                        "success": False,
                        "error": f"Label '{label_name}' does not exist and create_if_missing is False"
                    }
            
            if not label_ids_to_add:
                return {
                    "success": False,
                    "error": "No valid labels to add"
                }
            
            # Add labels to the message
            modify_request = {
                'addLabelIds': label_ids_to_add
            }
            
            result = service.users().messages().modify(
                userId='me',
                id=message_id,
                body=modify_request
            ).execute()
            
            # Get updated message info
            updated_message = service.users().messages().get(
                userId='me',
                id=message_id,
                format='metadata',
                metadataHeaders=['Subject', 'From']
            ).execute()
            
            headers = {h['name']: h['value'] for h in updated_message['payload'].get('headers', [])}
            subject = headers.get('Subject', 'No Subject')
            
            return {
                "success": True,
                "message_id": message_id,
                "labels_added": labels_added,
                "labels_created": labels_created,
                "message_subject": subject,
                "total_labels_on_message": len(result.get('labelIds', [])),
                "message": f"Successfully added {len(labels_added)} label(s) to message: {subject}"
            }
            
        except HttpError as e:
            return {
                "success": False,
                "error": f"Gmail API error: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to add labels: {str(e)}"
            }


class EmailTaskInput(BaseModel):
    """Input schema for email tasks."""
    task: str = Field(description="Description of the email task to perform")
    max_emails: int = Field(default=5, description="Maximum number of emails to process")
    credentials_file: str = Field(default="credentials.json", description="Path to OAuth credentials file")


class EmailTaskResult(BaseModel):
    """Output schema for email task results."""
    thoughts: str = Field(description="The agent's reasoning about the email task")
    emails_processed: int = Field(description="Number of emails that were processed")
    drafts_created: int = Field(description="Number of draft replies created")
    email_summaries: List[str] = Field(description="Brief summaries of processed emails")
    draft_summaries: List[str] = Field(description="Summaries of created draft replies")
    success: bool = Field(description="Whether the task completed successfully")
    errors: List[str] = Field(description="Any errors encountered during processing")
    next_steps: str = Field(description="Recommended next steps or actions")


def print_email_status(event_type: str, data: dict):
    """
    Callback for printing email agent status updates.
    """
    if event_type == "goal_start":
        print(f"Agent: {data.get('agent_name')}")
        print(f"Goal: {data.get('goal')}")
    elif event_type == "thought_created":
        user_message = data.get("thought", {}).get("user_message", "")
        if user_message:
            print(user_message)

def main():
    """Example usage of the EmailAgent."""
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
    
    # Check for Gmail credentials
    if not os.path.exists("credentials.json"):
        print("❌ ERROR: Gmail credentials file 'credentials.json' not found!")
        print("")
        print("To set up Gmail API access:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create a new project or select existing one")
        print("3. Enable the Gmail API")
        print("4. Configure OAuth consent screen")
        print("5. Create OAuth 2.0 credentials")
        print("6. Download credentials as 'credentials.json'")
        print("")
        return
    
    try:
        description = """An AI agent that manages Gmail tasks including:
- Listing emails from your inbox with filtering options
- Reading and analyzing emails with comprehensive categorization
- Assessing whether emails need replies and generating appropriate responses
- Creating draft responses and replies to emails
- Adding labels/tags to organize emails effectively
- Managing complete email workflows efficiently"""

        # Create Opper client for tools that need it
        from opperai import Opper
        opper_client = Opper(http_bearer=api_key)
        
        # Create tools
        gmail_auth_tool = GmailAuthTool()
        list_emails_tool = ListEmailsTool(gmail_auth_tool)
        read_email_tool = ReadEmailTool(gmail_auth_tool, opper_client)
        fetch_emails_tool = FetchUnrepliedEmailsTool(gmail_auth_tool)
        create_draft_tool = CreateDraftReplyTool(gmail_auth_tool)
        add_draft_response_tool = AddDraftResponseTool(gmail_auth_tool)
        add_email_tag_tool = AddEmailTagTool(gmail_auth_tool)
        
        email_tools = [
            gmail_auth_tool,
            list_emails_tool,
            read_email_tool,
            fetch_emails_tool,
            add_draft_response_tool,
            add_email_tag_tool,
        ]
        
        agent = BaseAgent(
            name="EmailAgent",
            opper_api_key=api_key,
            callback=print_email_status,
            verbose=False,
            output_schema=EmailTaskResult,
            tools=email_tools,
            description=description,
            max_iterations=50,
        )

        goal = "Go through the last 10 undread emails, apply labels (info, spam, news, personal) and draft responses in cases where appropriate (such as obvious follow up questions)"

        result = agent.process(goal)
        
        if isinstance(result, dict):
            print(f"\n📊 Results:")
            print(f"   Emails processed: {result.get('emails_processed', 0)}")
            print(f"   Drafts created: {result.get('drafts_created', 0)}")
            print(f"   Success: {result.get('success', False)}")
            
            if result.get('errors'):
                print(f"   Errors: {result.get('errors')}")
            
            if result.get('next_steps'):
                print(f"   Next steps: {result.get('next_steps')}")
        
    except Exception as e:
        print(f"❌ Error running email agent: {e}")
        print("This might be due to:")
        print("- Invalid API key")
        print("- Missing Gmail credentials")
        print("- Network connectivity issues")
        print("- Gmail API permissions")


if __name__ == "__main__":
    main()
