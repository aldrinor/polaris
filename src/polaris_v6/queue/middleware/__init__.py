"""Dramatiq middleware for POLARIS v6.

- otel_propagate: trace-id propagation across enqueue → execute
- throttle: high-retry-rate degradation mitigation
- connection: sticky Redis connection (cookbook pattern)
"""
