"""Lifecycle agent package."""

from .config import (
    DepartmentConfig,
    Settings,
    SpecialistConfig,
    load_departments,
    select_department,
)

__all__ = [
    "DepartmentConfig",
    "Settings",
    "SpecialistConfig",
    "load_departments",
    "select_department",
]