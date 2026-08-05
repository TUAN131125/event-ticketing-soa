"""SOAP and Seat Inventory XML namespaces."""

SOAP_ENV = "http://schemas.xmlsoap.org/soap/envelope/"
TNS = "urn:event-ticketing:seat:v1"
NSMAP = {"soap": SOAP_ENV, "seat": TNS}


def qname(local_name: str) -> str:
    return f"{{{TNS}}}{local_name}"
