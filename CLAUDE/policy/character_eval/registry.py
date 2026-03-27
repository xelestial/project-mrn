from __future__ import annotations

"""policy/character_eval/registry — CharacterEvaluator 레지스트리."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import CharacterEvaluator


def _build_registry() -> dict:
    from .geo_pair import GeoPairEvaluator
    from .builder_swindler import BuilderSwindlerEvaluator
    from .chuno_escape import ChunoBondservantEvaluator
    from .pabal_ajeon import PabalAjeonEvaluator
    from .jagaek_sanjeok import JagaekSanjeokEvaluator
    from .shaman_pair import ShamanPairEvaluator
    from .asa_tamgwan import AsaTamgwanEvaluator
    from .doctrine_pair import DoctrinePairEvaluator

    evaluators = [
        GeoPairEvaluator(),
        BuilderSwindlerEvaluator(),
        ChunoBondservantEvaluator(),
        PabalAjeonEvaluator(),
        JagaekSanjeokEvaluator(),
        ShamanPairEvaluator(),
        AsaTamgwanEvaluator(),
        DoctrinePairEvaluator(),
    ]
    registry: dict = {}
    for ev in evaluators:
        for name in ev.characters:
            registry[name] = ev
    return registry


_REGISTRY: dict = _build_registry()


def get_evaluator(character_name: str) -> "CharacterEvaluator":
    """캐릭터 이름으로 evaluator를 반환한다."""
    ev = _REGISTRY.get(character_name)
    if ev is None:
        raise KeyError(f"CharacterEvalRegistry: unknown character {character_name!r}")
    return ev
