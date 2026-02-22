from .base import BaseCheck, CheckRegistry
from .structural import STRUCTURAL_CHECKS
from .cross_statement import CROSS_STATEMENT_CHECKS
from .reasonableness import REASONABLENESS_CHECKS

ALL_CHECKS = STRUCTURAL_CHECKS + CROSS_STATEMENT_CHECKS + REASONABLENESS_CHECKS
