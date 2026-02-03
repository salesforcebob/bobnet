"""
Email parsing utility for raw email content.

This module provides functions to parse raw RFC 5322 email content
and extract HTML body and Message-Id headers. Used by the Cloudflare
webhook endpoint to process raw email content.
"""
from __future__ import annotations

import email
from email.message import Message
from typing import Optional


def _extract_html_from_message(msg: Message) -> Optional[str]:
    """
    Extract HTML content from an email message.
    
    Handles various email structures:
    - multipart/alternative (prefers HTML over plain text)
    - multipart/related (finds HTML part)
    - text/html (direct HTML content)
    
    Args:
        msg: Email message object.
        
    Returns:
        HTML content as string, or None if not found.
    """
    content_type = msg.get_content_type()
    
    # Direct HTML content
    if content_type == "text/html":
        payload = msg.get_payload(decode=True)
        if payload:
            # Decode bytes to string, handling encoding
            charset = msg.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset, errors="replace")
            except (UnicodeDecodeError, AttributeError):
                # If already a string, return as-is
                return str(payload) if payload else None
        return None
    
    # Multipart messages - walk through parts
    if msg.is_multipart():
        html_parts = []
        plain_parts = []
        
        for part in msg.walk():
            part_type = part.get_content_type()
            
            if part_type == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_content = payload.decode(charset, errors="replace")
                        html_parts.append(html_content)
                    except (UnicodeDecodeError, AttributeError):
                        html_content = str(payload) if payload else None
                        if html_content:
                            html_parts.append(html_content)
            
            elif part_type == "text/plain":
                # Collect plain text parts but prefer HTML
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        plain_content = payload.decode(charset, errors="replace")
                        plain_parts.append(plain_content)
                    except (UnicodeDecodeError, AttributeError):
                        pass
        
        # Prefer HTML over plain text
        if html_parts:
            return "\n".join(html_parts)
        
        # Fallback to plain text if no HTML found
        if plain_parts:
            return None  # Return None for plain text (we only want HTML)
    
    return None


def parse_raw_email(raw_content: str) -> dict[str, Optional[str]]:
    """
    Parse raw RFC 5322 email content and extract Message-Id and HTML body.
    
    Args:
        raw_content: Raw email string (headers + body).
        
    Returns:
        Dictionary with keys:
        - message_id: Message-Id header value, or None if not found
        - html: HTML body content, or None if not found
        - subject: Subject header value, or None if not found
    """
    try:
        msg = email.message_from_string(raw_content)
    except Exception:
        # If parsing fails, return empty dict
        return {"message_id": None, "html": None, "subject": None}
    
    # Extract Message-Id header
    message_id = msg.get("Message-Id")
    if message_id:
        # Remove angle brackets if present
        message_id = message_id.strip("<>")
    
    # Extract Subject header
    subject = msg.get("Subject")
    
    # Extract HTML content
    html = _extract_html_from_message(msg)
    
    return {
        "message_id": message_id,
        "html": html,
        "subject": subject,
    }
