"""
RabbitMQ worker entry point.

This module starts a RabbitMQ consumer that processes jobs from the
email_simulator queue by calling the process_mail function.
"""
from __future__ import annotations
import json
import logging
import pika
from .queue import get_connection, QUEUE_NAME
from .worker import process_mail
from .logging import configure_json_logging

logger = logging.getLogger(__name__)


def callback(ch, method, properties, body):
    """
    Process a message from the queue.
    
    Args:
        ch: The channel object.
        method: Delivery method with delivery_tag.
        properties: Message properties.
        body: The message body (JSON string).
    """
    message_id = properties.message_id or "unknown"
    
    try:
        logger.info("rabbitmq_job_received", extra={
            "queue": QUEUE_NAME,
            "message_id": message_id,
            "delivery_tag": method.delivery_tag,
        })
        
        job = json.loads(body)
        process_mail(job)
        
        # Acknowledge the message after successful processing
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
        logger.info("rabbitmq_job_completed", extra={
            "queue": QUEUE_NAME,
            "message_id": message_id,
        })
        
    except Exception as e:
        logger.error("rabbitmq_job_failed", extra={
            "queue": QUEUE_NAME,
            "message_id": message_id,
            "error": str(e),
        })
        # Reject and requeue the message on failure
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def main() -> None:
    """Start the RabbitMQ consumer."""
    # Configure JSON logging for worker process
    configure_json_logging()
    
    logger.info("worker_starting", extra={"queue": QUEUE_NAME})
    
    connection = get_connection()
    channel = connection.channel()
    
    # Declare queue as durable (matches publisher)
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    
    # Process one message at a time (fair dispatch)
    channel.basic_qos(prefetch_count=1)
    
    # Start consuming messages
    channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
    
    logger.info("worker_ready", extra={"queue": QUEUE_NAME})
    
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        logger.info("worker_stopping", extra={"queue": QUEUE_NAME})
        channel.stop_consuming()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
