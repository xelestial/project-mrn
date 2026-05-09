from __future__ import annotations

from typing import Iterable

from apps.server.src.infra.backend_connection_manager import (
    FRONTEND_BACKEND_ROUTE_CATALOG,
    BackendConnectionCatalogMismatchError,
    BackendFrontendRoute,
    catalog_signature_set,
)


BACKEND_TEST_ADAPTER_ROUTE_CATALOG: tuple[BackendFrontendRoute, ...] = FRONTEND_BACKEND_ROUTE_CATALOG


def assert_backend_test_adapter_catalog_current(
    adapter_catalog: Iterable[BackendFrontendRoute] = BACKEND_TEST_ADAPTER_ROUTE_CATALOG,
) -> None:
    expected_keys = [route.key for route in FRONTEND_BACKEND_ROUTE_CATALOG]
    actual = tuple(adapter_catalog)
    actual_keys = [route.key for route in actual]
    if actual_keys != expected_keys:
        raise BackendConnectionCatalogMismatchError(
            f"backend test adapter route keys changed: expected={expected_keys}, actual={actual_keys}"
        )
    expected_signatures = catalog_signature_set(FRONTEND_BACKEND_ROUTE_CATALOG)
    actual_signatures = catalog_signature_set(actual)
    if actual_signatures != expected_signatures:
        raise BackendConnectionCatalogMismatchError(
            "backend test adapter route signatures differ from backend connection manager"
        )
