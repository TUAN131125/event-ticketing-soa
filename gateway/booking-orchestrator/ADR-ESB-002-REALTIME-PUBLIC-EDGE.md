# ADR-ESB-002 — Direct Realtime public edge (SUPERSEDED)

## Status

Superseded for the current localhost/demo architecture.

## Current decision

The browser knows only the ESB public origin. Direct WebSocket connections to Realtime Status Service on port `8008` are disabled in the frontend. Booking status is obtained through authoritative REST polling via ESB.

A future WebSocket gateway route may be introduced by a new ADR. Until then, Realtime Service remains private and this document must not be used to expose port `8008` to browsers.
