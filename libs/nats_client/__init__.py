"""
NATS client library

Provides high-level NATS client with reconnection,
JWT authentication, distributed tracing, and structured logging.
"""

from .client import NATSClient

__all__ = ['NATSClient']
