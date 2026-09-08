"""Pioneer Core — a local stand-in for a legacy credit-union teller console.

No API, no test IDs, nested tables, an iframe workspace, a rotating viewstate.
Exceptional states are first-class: not-found, validation, permission denial,
fraud-hold confirmation, slow load, session expiry, a dismissible notice.
"""

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
