"""Provider adapter boundary.

Provider-specific network calls and signature validation belong in adapters owned
by Payment Service. The core API records only verified outcomes and never accepts
PAN, CVV or other raw payment credentials.
"""
