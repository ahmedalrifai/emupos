class EndpointUnavailableError(Exception):
    """A connection endpoint could not be opened. The message names the endpoint and the fix;
    the daemon prefixes the device id."""
