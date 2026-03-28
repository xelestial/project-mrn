from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from contextlib import contextmanager
import importlib.util
import sys
from types import ModuleType


@dataclass(frozen=True)
class LoadedPolicyRuntime:
    runtime_id: str
    root_dir: Path
    heuristic_policy_cls: type
    base_policy_cls: type | None
    alias_modules: dict[str, str]
    loaded_modules: dict[str, ModuleType]

    @contextmanager
    def activated(self):
        saved_plain_modules = {name: sys.modules.get(name) for name in self.loaded_modules}
        saved_policy_modules = _capture_modules(("policy",))
        root_path_str = str(self.root_dir)
        sys_path_inserted = False
        try:
            for module_name in saved_policy_modules:
                sys.modules.pop(module_name, None)
            for module_name, module in self.loaded_modules.items():
                sys.modules[module_name] = module
            if root_path_str not in sys.path:
                sys.path.insert(0, root_path_str)
                sys_path_inserted = True
            yield
        finally:
            if sys_path_inserted:
                try:
                    sys.path.remove(root_path_str)
                except ValueError:
                    pass
            for module_name in list(sys.modules):
                if module_name == "policy" or module_name.startswith("policy."):
                    sys.modules.pop(module_name, None)
            sys.modules.update(saved_policy_modules)
            for module_name, original in saved_plain_modules.items():
                if original is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = original


_RUNTIME_CACHE: dict[tuple[str, str, tuple[str, ...]], LoadedPolicyRuntime] = {}


def _capture_modules(prefixes: tuple[str, ...]) -> dict[str, ModuleType]:
    captured: dict[str, ModuleType] = {}
    for name, module in list(sys.modules.items()):
        for prefix in prefixes:
            if name == prefix or name.startswith(prefix + "."):
                captured[name] = module
                break
    return captured


def _alias_name(runtime_id: str, module_name: str) -> str:
    normalized = module_name.replace(".", "__")
    return f"_isolated_{runtime_id}_{normalized}"


def _module_path(root_dir: Path, module_name: str) -> tuple[Path, bool]:
    module_parts = module_name.split(".")
    package_dir = root_dir.joinpath(*module_parts)
    package_init = package_dir / "__init__.py"
    if package_init.exists():
        return package_init, True
    module_file = root_dir.joinpath(*module_parts).with_suffix(".py")
    if module_file.exists():
        return module_file, False
    raise FileNotFoundError(f"Cannot find module '{module_name}' under {root_dir}")


def _load_module(alias_name: str, module_name: str, root_dir: Path) -> ModuleType:
    module_file, is_package = _module_path(root_dir, module_name)
    kwargs = {}
    if is_package:
        kwargs["submodule_search_locations"] = [str(module_file.parent)]
    spec = importlib.util.spec_from_file_location(alias_name, module_file, **kwargs)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to build import spec for {module_name} at {module_file}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias_name] = module
    spec.loader.exec_module(module)
    return module


def load_policy_runtime(
    runtime_id: str,
    root_dir: str | Path,
    isolated_modules: tuple[str, ...],
    entry_module: str = "ai_policy",
) -> LoadedPolicyRuntime:
    root_path = Path(root_dir).resolve()
    cache_key = (runtime_id, str(root_path), tuple(isolated_modules))
    cached = _RUNTIME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    saved_plain_modules = {name: sys.modules.get(name) for name in isolated_modules}
    saved_policy_modules = _capture_modules(("policy",))
    loaded_modules: dict[str, ModuleType] = {}
    alias_map: dict[str, str] = {}
    root_path_str = str(root_path)
    sys_path_inserted = False

    try:
        for module_name in saved_policy_modules:
            sys.modules.pop(module_name, None)
        if root_path_str not in sys.path:
            sys.path.insert(0, root_path_str)
            sys_path_inserted = True
        for module_name in isolated_modules:
            alias_name = _alias_name(runtime_id, module_name)
            alias_map[module_name] = alias_name
            for mapped_name, mapped_module in loaded_modules.items():
                sys.modules[mapped_name] = mapped_module
            module = _load_module(alias_name, module_name, root_path)
            loaded_modules[module_name] = module
            sys.modules[module_name] = module

        entry = loaded_modules[entry_module]
        runtime = LoadedPolicyRuntime(
            runtime_id=runtime_id,
            root_dir=root_path,
            heuristic_policy_cls=getattr(entry, "HeuristicPolicy"),
            base_policy_cls=getattr(entry, "BasePolicy", None),
            alias_modules=dict(alias_map),
            loaded_modules=dict(loaded_modules),
        )
        _RUNTIME_CACHE[cache_key] = runtime
        return runtime
    finally:
        if sys_path_inserted:
            try:
                sys.path.remove(root_path_str)
            except ValueError:
                pass
        for module_name in list(sys.modules):
            if module_name == "policy" or module_name.startswith("policy."):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_policy_modules)
        for module_name, original in saved_plain_modules.items():
            if original is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = original
