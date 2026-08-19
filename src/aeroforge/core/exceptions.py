class AeroForgeError(Exception): pass
class RetryableError(AeroForgeError): pass
class ExternalToolError(AeroForgeError): pass
class ValidationError(AeroForgeError): pass
