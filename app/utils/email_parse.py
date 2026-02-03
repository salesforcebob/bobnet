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
            
            # Get payload info before decoding
            raw_payload = part.get_payload()
            payload_before_length = len(str(raw_payload)) if raw_payload else 0
            
            logger.info("email_parse_part_found", extra={
                "part_index": part_count,
                "content_type": part_type,
                "content_disposition": content_disposition,
                "transfer_encoding": transfer_encoding,
                "charset": charset,
                "payload_before_length": payload_before_length,
                "is_multipart": part.is_multipart(),
            })
            
            if part_type == "text/html":
                payload = part.get_payload(decode=True)
                payload_after_length = len(payload) if payload else 0
                
                logger.info("email_parse_html_part", extra={
                    "part_index": part_count,
                    "payload_before_length": payload_before_length,
                    "payload_after_length": payload_after_length,
                    "has_payload": payload is not None,
                })
                
                if payload:
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
                        html_content = str(payload) if payload else None
                        if html_content:
                            html_parts.append(html_content)
                            logger.info("email_parse_html_part_fallback", extra={
                                "part_index": part_count,
                                "html_length": len(html_content),
                                "html_preview": html_content[:500],
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
    
    # Extract HTML content
    html = _extract_html_from_message(msg)
    
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
