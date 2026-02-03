"""
RabbitMQ queue module for publishing jobs to CloudAMQP.

This module provides functions to connect to RabbitMQ and publish
job payloads to the email_simulator queue.
"""
from __future__ import annotations
import json
import logging
import pika
from .config import settings

logger = logging.getLogger(__name__)

QUEUE_NAME = "email_simulator"


def get_connection() -> pika.BlockingConnection:
    """
    Create a RabbitMQ connection from CLOUDAMQP_URL.
    
    Returns:
        A blocking connection to RabbitMQ.
    """
    params = pika.URLParameters(settings.cloudamqp_url)
    # Set heartbeat and connection timeout for reliability
    params.heartbeat = 600
    params.blocked_connection_timeout = 300
    return pika.BlockingConnection(params)


def publish_job(job_payload: dict) -> str:
    """
    Publish a job to the email_simulator queue.
    
    Args:
        job_payload: Dictionary containing job data (message_id, to, html).
        
    Returns:
        The message_id from the job payload.
    """
    connection = get_connection()
    try:
        channel = connection.channel()
        
        # Declare queue as durable (survives broker restart)
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        
        message_id = job_payload.get("message_id", "")
        body = json.dumps(job_payload)
        
        channel.basic_publish(
            exchange="",
            routing_key=QUEUE_NAME,
            body=body,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
                content_type="application/json",
                message_id=message_id,
            ),
        )
        
        logger.info("rabbitmq_job_published", extra={
            "queue": QUEUE_NAME,
            "message_id": message_id,
            "body_length": len(body),
        })
        
        return message_id
    finally:
        connection.close()
