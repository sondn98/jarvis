from enum import Enum


class ToolRiskLevel(str, Enum):
    SAFE_READ_ONLY = "safe_read_only"
    SENSITIVE_READ = "sensitive_read"
    EXTERNAL_WRITE = "external_write"
    DESTRUCTIVE = "destructive"
    UNKNOWN = "unknown"
