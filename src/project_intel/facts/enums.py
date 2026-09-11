from enum import Enum


class EntityType(str, Enum):
    SYSTEM = "System"
    ENVIRONMENT = "Environment"
    REPOSITORY = "Repository"
    PROJECT = "Project"
    DIRECTORY = "Directory"
    FILE = "File"
    SYMBOL = "Symbol"
    COMMIT = "Commit"
    CONTRIBUTOR = "Contributor"
    SERVICE = "Service"
    DATABASE = "Database"
    QUEUE = "Queue"
    EXTERNAL_SOURCE = "ExternalSource"
    TOOL = "Tool"
    DOCUMENT = "Document"


class RelationType(str, Enum):
    DEPENDS_ON = "depends_on"
    CALLS = "calls"
    IMPORTS = "imports"
    INHERITS_FROM = "inherits_from"
    CONTAINS = "contains"
    BELONGS_TO = "belongs_to"
    CHANGED_IN = "changed_in"
    AUTHORED_BY = "authored_by"
    DEPLOYED_BY = "deployed_by"
    COMMUNICATES_WITH = "communicates_with"
    DOCUMENTS = "documents"
    TESTS = "tests"


class FactStatus(str, Enum):
    """Closed enum for unknown/not-analyzed states; used by adapter features."""

    UNKNOWN = "unknown"
    NOT_ANALYZED = "not_analyzed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    SKIPPED_TOOL_NOT_FOUND = "skipped:tool_not_found"
    SKIPPED_VERSION_MISMATCH = "skipped:version_mismatch"
    FAILED = "failed"
