"""
Permission System Exceptions

Custom exception classes for permission-related errors.
"""


class PermissionError(Exception):
    """Base exception for permission-related errors."""
    pass


class PermissionConfigError(PermissionError):
    """Raised when permission configuration is invalid."""
    pass


class PermissionDeniedError(PermissionError):
    """Raised when user lacks required permission."""
    
    def __init__(self, message, permission_name=None, user=None):
        super().__init__(message)
        self.permission_name = permission_name
        self.user = user


class BranchAccessDeniedError(PermissionError):
    """Raised when user lacks branch access."""
    
    def __init__(self, message, branch=None, user=None):
        super().__init__(message)
        self.branch = branch
        self.user = user
