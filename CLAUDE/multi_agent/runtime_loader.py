from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
import importlib.util
import sys
from types import ModuleType


@dataclass
class LoadedPolicyRuntime:
    runtime_id: str
    root_dir: Path
    heuristic_policy_cls: type
    base_policy_cls: type | None
    alias_modules: dict[str, str]
    # plain_name → module object (all isolated modules including policy.* side-effects)
    _modules: dict[str, ModuleType] = field(default_factory=dict, repr=False)

    @contextmanager
    def activated(self):
        """Call-time isolation context.

        Temporarily injects all isolated modules into sys.modules under their
        plain names, and prepends root_dir to sys.path, so that any further
        import triggered during policy method calls resolves within this runtime.
        """
        root_str = str(self.root_dir)

        # Save current state
        saved_modules = {name: sys.modules.get(name) for name in self._modules}
        saved_side_effects = {
            name: module
            for name, module in list(sys.modules.items())
            if _is_side_effect_key(name) and name not in self._modules
        }
        path_had = root_str in sys.path
        if path_had:
            sys.path.remove(root_str)
        sys.path.insert(0, root_str)

        # Inject
        for name in saved_side_effects:
            sys.modules.pop(name, None)
        for plain_name, module in self._modules.items():
            sys.modules[plain_name] = module

        try:
            yield self
        finally:
            # Restore sys.path
            if root_str in sys.path:
                sys.path.remove(root_str)
            if path_had:
                sys.path.insert(0, root_str)

            # Restore sys.modules
            for name, original in saved_modules.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original
            for name, module in saved_side_effects.items():
                sys.modules[name] = module


_RUNTIME_CACHE: dict[tuple[str, str, tuple[str, ...]], LoadedPolicyRuntime] = {}

# Module name prefixes treated as runtime-local (isolated as side-effects)
_POLICY_SIDE_EFFECT_PREFIXES = ("policy", "policy_")


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


def _is_side_effect_key(name: str) -> bool:
    return any(name == p.rstrip("_") or name.startswith(p) for p in _POLICY_SIDE_EFFECT_PREFIXES)


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

    root_str = str(root_path)

    # --- Save state ---
    # 1. Save and remove explicitly listed modules
    saved_plain_modules = {name: sys.modules.get(name) for name in isolated_modules}
    # 2. Save and remove all policy.* side-effect modules
    side_effect_keys = [k for k in sys.modules if _is_side_effect_key(k)]
    saved_side_effects = {k: sys.modules.pop(k) for k in side_effect_keys}
    # 3. Save and move sys.path (insert root_path at front)
    path_had = root_str in sys.path
    if path_had:
        sys.path.remove(root_str)
    sys.path.insert(0, root_str)

    loaded_modules: dict[str, ModuleType] = {}
    alias_map: dict[str, str] = {}

    try:
        for module_name in isolated_modules:
            alias_name = _alias_name(runtime_id, module_name)
            alias_map[module_name] = alias_name
            # Make already-loaded modules in this batch visible under plain names
            # so intra-runtime imports resolve correctly
            for mapped_name, mapped_module in loaded_modules.items():
                sys.modules[mapped_name] = mapped_module
            module = _load_module(alias_name, module_name, root_path)
            loaded_modules[module_name] = module
            sys.modules[module_name] = module

        entry = loaded_modules[entry_module]

        # Capture side-effect policy.* modules that were loaded during this runtime
        # and alias them so they can be re-injected during activated()
        all_modules: dict[str, ModuleType] = dict(loaded_modules)
        for k in list(sys.modules.keys()):
            if _is_side_effect_key(k) and k not in loaded_modules:
                alias_name = _alias_name(runtime_id, k)
                alias_map[k] = alias_name
                mod = sys.modules[k]
                sys.modules[alias_name] = mod
                all_modules[k] = mod

        runtime = LoadedPolicyRuntime(
            runtime_id=runtime_id,
            root_dir=root_path,
            heuristic_policy_cls=getattr(entry, "HeuristicPolicy"),
            base_policy_cls=getattr(entry, "BasePolicy", None),
            alias_modules=dict(alias_map),
            _modules=all_modules,
        )
        _RUNTIME_CACHE[cache_key] = runtime
        return runtime

    finally:
        # Restore sys.path
        if root_str in sys.path:
            sys.path.remove(root_str)
        if path_had:
            sys.path.insert(0, root_str)

        # Restore explicit modules
        for module_name, original in saved_plain_modules.items():
            if original is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = original

        # Remove any policy.* side-effects left by this runtime's loading
        for k in list(sys.modules.keys()):
            if _is_side_effect_key(k) and k not in saved_side_effects:
                sys.modules.pop(k, None)

        # Restore original side-effect modules
        sys.modules.update(saved_side_effects)
