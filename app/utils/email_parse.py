"""
Email parsing utility for raw email content.

This module provides functions to parse raw RFC 5322 email content
and extract HTML body and Message-Id headers. Used by the Cloudflare
webhook endpoint to process raw email content.
"""
from __future__ import annotations

import email
import logging
from email.message import Message
from typing import Optional

logger = logging.getLogger(__name__)


def _find_html_in_alternatives(msg: Message, raw_content: str | None) -> Optional[str]:
    """
    Search for HTML content in alternative locations.
    
    Checks for:
    - multipart/related structures
    - Embedded HTML in other content types
    - HTML in Content-Disposition: inline attachments
    - Base64 encoded HTML
    
    Args:
        msg: Email message object.
        raw_content: Optional raw email string.
        
    Returns:
        HTML content if found, None otherwise.
    """
    # Check for multipart/related (common in Marketing Cloud)
    if msg.is_multipart():
        content_type = msg.get_content_type()
        
        # If this is multipart/related, look for HTML in related parts
        if content_type == "multipart/related":
            logger.info("email_parse_alternative_multipart_related", extra={
                "content_type": content_type,
            })
            
            # Walk through parts looking for HTML
            for part in msg.walk():
                part_type = part.get_content_type()
                content_disposition = part.get("Content-Disposition", "")
                
                # Check for HTML in various forms
                if part_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            html = payload.decode(charset, errors="replace")
                            if html.strip():
                                logger.info("email_parse_alternative_html_found", extra={
                                    "location": "multipart/related",
                                    "html_length": len(html),
                                })
                                return html
                        except Exception:
                            pass
                
                # Check for HTML in inline attachments
                if "inline" in content_disposition.lower() and part_type.startswith("text/"):
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            content = payload.decode(charset, errors="replace")
                            # Check if it looks like HTML
                            if "<html" in content.lower() or "<body" in content.lower():
                                logger.info("email_parse_alternative_html_inline", extra={
                                    "content_disposition": content_disposition,
                                    "html_length": len(content),
                                })
                                return content
                        except Exception:
                            pass
        
        # Check all parts for any HTML-like content
        for part in msg.walk():
            if part.is_multipart():
                continue
            
            part_type = part.get_content_type()
            transfer_encoding = part.get("Content-Transfer-Encoding", "").lower()
            
            # Check for base64 encoded HTML
            if transfer_encoding == "base64" and part_type.startswith("text/"):
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        content = payload.decode(charset, errors="replace")
                        if "<html" in content.lower() or "<body" in content.lower():
                            logger.info("email_parse_alternative_html_base64", extra={
                                "part_type": part_type,
                                "html_length": len(content),
                            })
                            return content
                    except Exception:
                        pass
    
    return None


def _inspect_raw_content_around_part(raw_content: str, part: Message, part_index: int) -> str | None:
    """
    Inspect raw email content around a specific part's boundaries.
    
    This helps diagnose if content exists in the raw email but isn't being
    extracted correctly by the parser.
    
    Args:
        raw_content: Raw email string.
        part: Email message part.
        part_index: Index of the part for logging.
        
    Returns:
        String containing content around the part's boundaries, or None if not found.
    """
    try:
        # Try to find the part's content in the raw email
        # Look for Content-Type header matching this part
        content_type = part.get("Content-Type", "")
        if not content_type:
            return None
        
        # Find the part's position in raw content
        # Look for the Content-Type header
        type_search = f"Content-Type: {content_type.split(';')[0].strip()}"
        type_pos = raw_content.find(type_search)
        
        if type_pos == -1:
            # Try without the full type
            main_type = part.get_content_maintype()
            sub_type = part.get_content_subtype()
            type_search = f"Content-Type: {main_type}/{sub_type}"
            type_pos = raw_content.find(type_search)
        
        if type_pos == -1:
            return None
        
        # Extract content around this position (500 chars before, 2000 chars after)
        start = max(0, type_pos - 500)
        end = min(len(raw_content), type_pos + 2000)
        context = raw_content[start:end]
        
        # Clean up for logging (replace newlines with \n for readability)
        context_preview = context.replace("\r\n", "\\r\\n").replace("\r", "\\r").replace("\n", "\\n")
        
        return context_preview[:1500]  # Limit length
    except Exception as e:
        logger.debug("email_parse_boundary_inspection_failed", extra={
            "part_index": part_index,
            "error": str(e),
        })
        return None


def _extract_html_from_message(msg: Message, raw_content: str | None = None) -> Optional[str]:
    """
    Extract HTML content from an email message.
    
    Handles various email structures:
    - multipart/alternative (prefers HTML over plain text)
    - multipart/related (finds HTML part)
    - text/html (direct HTML content)
    
    Args:
        msg: Email message object.
        raw_content: Optional raw email string for boundary inspection.
        
    Returns:
        HTML content as string, or None if not found.
    """
    content_type = msg.get_content_type()
    is_multipart = msg.is_multipart()
    
    logger.info("email_parse_extract_start", extra={
        "content_type": content_type,
        "is_multipart": is_multipart,
        "content_main_type": msg.get_content_maintype(),
        "content_sub_type": msg.get_content_subtype(),
    })
    
    # Direct HTML content
    if content_type == "text/html":
        payload = msg.get_payload(decode=True)
        payload_length_before = len(str(msg.get_payload())) if msg.get_payload() else 0
        payload_length_after = len(payload) if payload else 0
        
        logger.info("email_parse_direct_html", extra={
            "payload_length_before": payload_length_before,
            "payload_length_after": payload_length_after,
            "has_payload": payload is not None,
        })
        
        if payload:
            # Decode bytes to string, handling encoding
            charset = msg.get_content_charset() or "utf-8"
            transfer_encoding = msg.get("Content-Transfer-Encoding", "unknown")
            
            logger.info("email_parse_decoding", extra={
                "charset": charset,
                "transfer_encoding": transfer_encoding,
                "payload_type": type(payload).__name__,
            })
            
            try:
                html_content = payload.decode(charset, errors="replace")
                logger.info("email_parse_direct_html_success", extra={
                    "html_length": len(html_content),
                    "html_preview": html_content[:500] if html_content else None,
                })
                return html_content
            except (UnicodeDecodeError, AttributeError) as e:
                logger.warning("email_parse_decode_error", extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                })
                # If already a string, return as-is
                html_content = str(payload) if payload else None
                if html_content:
                    logger.info("email_parse_fallback_string", extra={
                        "html_length": len(html_content),
                        "html_preview": html_content[:500],
                    })
                    return html_content
        logger.info("email_parse_direct_html_no_payload")
        return None
    
    # Multipart messages - walk through parts
    if is_multipart:
        html_parts = []
        plain_parts = []
        part_count = 0
        
        logger.info("email_parse_multipart_start", extra={
            "content_type": content_type,
        })
        
        for part in msg.walk():
            part_count += 1
            part_type = part.get_content_type()
            content_disposition = part.get("Content-Disposition", "")
            transfer_encoding = part.get("Content-Transfer-Encoding", "unknown")
            charset = part.get_content_charset() or "unknown"
            is_part_multipart = part.is_multipart()
            
            # Log ALL parts including multipart containers for complete structure visibility
            if is_part_multipart:
                # Count sub-parts for multipart containers
                sub_parts = []
                try:
                    if hasattr(part, 'get_payload'):
                        payload = part.get_payload()
                        if isinstance(payload, list):
                            sub_parts = [p.get_content_type() for p in payload if hasattr(p, 'get_content_type')]
                except Exception:
                    pass
                
                # Get boundary information
                content_type_header = part.get("Content-Type", "")
                boundary = None
                if "boundary=" in content_type_header:
                    try:
                        boundary = content_type_header.split("boundary=")[1].split(";")[0].strip('"')
                    except Exception:
                        pass
                
                logger.info("email_parse_part_multipart_container", extra={
                    "part_index": part_count,
                    "content_type": part_type,
                    "content_main_type": part.get_content_maintype(),
                    "content_sub_type": part.get_content_subtype(),
                    "sub_parts_count": len(sub_parts) if isinstance(sub_parts, list) else 0,
                    "sub_parts_types": sub_parts[:10],  # First 10 sub-part types
                    "boundary": boundary,
                    "content_disposition": content_disposition,
                })
                # Continue to skip processing (walk() handles children)
                continue
            
            # Get payload info before decoding
            raw_payload = part.get_payload()
            payload_before_length = len(str(raw_payload)) if raw_payload else 0
            payload_before_preview = str(raw_payload)[:200] if raw_payload else None
            
            logger.info("email_parse_part_found", extra={
                "part_index": part_count,
                "content_type": part_type,
                "content_disposition": content_disposition,
                "transfer_encoding": transfer_encoding,
                "charset": charset,
                "payload_before_length": payload_before_length,
                "payload_before_preview": payload_before_preview,
                "is_multipart": is_part_multipart,
            })
            
            if part_type == "text/html":
                payload = part.get_payload(decode=True)
                payload_after_length = len(payload) if payload else 0
                payload_after_preview = payload[:200] if payload else None
                
                # Inspect raw content around HTML part if available and content is suspiciously short
                raw_boundary_content = None
                if raw_content and payload_after_length < 100:
                    raw_boundary_content = _inspect_raw_content_around_part(
                        raw_content, part, part_count
                    )
                
                logger.info("email_parse_html_part", extra={
                    "part_index": part_count,
                    "payload_before_length": payload_before_length,
                    "payload_before_preview": payload_before_preview,
                    "payload_after_length": payload_after_length,
                    "payload_after_preview": payload_after_preview,
                    "has_payload": payload is not None,
                    "payload_type": type(payload).__name__ if payload else None,
                    "raw_boundary_content": raw_boundary_content,
                })
                
                if payload:
                    # Handle both bytes and string payloads
                    if isinstance(payload, bytes):
                        try:
                            html_content = payload.decode(charset if charset != "unknown" else "utf-8", errors="replace")
                            html_parts.append(html_content)
                            logger.info("email_parse_html_part_decoded", extra={
                                "part_index": part_count,
                                "html_length": len(html_content),
                                "html_preview": html_content[:500],
                            })
                        except (UnicodeDecodeError, AttributeError) as e:
                            logger.warning("email_parse_html_part_decode_error", extra={
                                "part_index": part_count,
                                "error": str(e),
                                "error_type": type(e).__name__,
                            })
                            # Fallback: try utf-8
                            try:
                                html_content = payload.decode("utf-8", errors="replace")
                                html_parts.append(html_content)
                                logger.info("email_parse_html_part_utf8_fallback", extra={
                                    "part_index": part_count,
                                    "html_length": len(html_content),
                                    "html_preview": html_content[:500],
                                })
                            except Exception:
                                pass
                    else:
                        # Already a string
                        html_content = str(payload)
                        if html_content.strip():  # Only add if not whitespace-only
                            html_parts.append(html_content)
                            logger.info("email_parse_html_part_string", extra={
                                "part_index": part_count,
                                "html_length": len(html_content),
                                "html_preview": html_content[:500],
                            })
                        else:
                            logger.warning("email_parse_html_part_whitespace", extra={
                                "part_index": part_count,
                                "html_length": len(html_content),
                                "html_content": repr(html_content),
                            })
            
            elif part_type == "text/plain":
                payload = part.get_payload(decode=True)
                payload_after_length = len(payload) if payload else 0
                
                logger.info("email_parse_plain_part", extra={
                    "part_index": part_count,
                    "payload_before_length": payload_before_length,
                    "payload_after_length": payload_after_length,
                })
                
                # Collect plain text parts but prefer HTML
                if payload:
                    try:
                        plain_content = payload.decode(charset if charset != "unknown" else "utf-8", errors="replace")
                        plain_parts.append(plain_content)
                    except (UnicodeDecodeError, AttributeError):
                        pass
        
        logger.info("email_parse_multipart_summary", extra={
            "total_parts": part_count,
            "html_parts_count": len(html_parts),
            "plain_parts_count": len(plain_parts),
        })
        
        # Prefer HTML over plain text
        if html_parts:
            combined_html = "\n".join(html_parts)
            logger.info("email_parse_html_extracted", extra={
                "html_parts_count": len(html_parts),
                "combined_html_length": len(combined_html),
                "combined_html_preview": combined_html[:1000],
            })
            return combined_html
        
        # If no HTML found, check for alternative locations
        if not html_parts:
            logger.info("email_parse_searching_alternatives", extra={
                "reason": "no_html_parts_found_in_walk",
            })
            
            # Check for multipart/related structures (common in Marketing Cloud)
            alternative_html = _find_html_in_alternatives(msg, raw_content)
            if alternative_html:
                logger.info("email_parse_html_found_alternative", extra={
                    "html_length": len(alternative_html),
                    "html_preview": alternative_html[:1000],
                })
                return alternative_html
        
        # Fallback to plain text if no HTML found
        if plain_parts:
            logger.info("email_parse_no_html_found", extra={
                "plain_parts_count": len(plain_parts),
                "reason": "only_plain_text_parts",
            })
            return None  # Return None for plain text (we only want HTML)
        
        logger.info("email_parse_no_content_parts", extra={
            "reason": "no_html_or_plain_parts_found",
        })
    
    logger.info("email_parse_no_html", extra={
        "content_type": content_type,
        "is_multipart": is_multipart,
        "reason": "not_html_and_not_multipart",
    })
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
    logger.info("email_parse_start", extra={
        "raw_content_length": len(raw_content),
        "raw_content_preview": raw_content[:500],
    })
    
    try:
        msg = email.message_from_string(raw_content)
        logger.info("email_parse_success", extra={
            "parsed_successfully": True,
        })
    except Exception as e:
        logger.error("email_parse_failed", extra={
            "error": str(e),
            "error_type": type(e).__name__,
        })
        # If parsing fails, return empty dict
        return {"message_id": None, "html": None, "subject": None}
    
    # Extract Message-Id header
    message_id = msg.get("Message-Id")
    if message_id:
        # Remove angle brackets if present
        message_id = message_id.strip("<>")
    
    # Extract Subject header
    subject = msg.get("Subject")
    
    # Log email structure
    content_type = msg.get_content_type()
    is_multipart = msg.is_multipart()
    
    logger.info("email_parse_structure", extra={
        "message_id": message_id,
        "subject": subject,
        "content_type": content_type,
        "is_multipart": is_multipart,
        "content_main_type": msg.get_content_maintype(),
        "content_sub_type": msg.get_content_subtype(),
    })
    
    # Extract HTML content (pass raw_content for boundary inspection)
    html = _extract_html_from_message(msg, raw_content=raw_content)
    
    # Log final results
    html_length = len(html) if html else 0
    html_is_whitespace = html and html.strip() == "" if html else False
    
    logger.info("email_parse_complete", extra={
        "message_id": message_id,
        "subject": subject,
        "html_length": html_length,
        "html_is_none": html is None,
        "html_is_whitespace": html_is_whitespace,
        "html_preview": html[:1000] if html else None,
    })
    
    return {
        "message_id": message_id,
        "html": html,
        "subject": subject,
    }
