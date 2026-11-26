"""Maya-side helpers for WipSkin plugins (needs Maya).

``scene`` is wipskin's scene query module (skinnable shapes, skinClusters,
DEFORMABLE_SHAPE_TYPES); ``feedback`` writes Maya messages and dialogs;
``skin_engine`` reads / writes skinCluster weights as SkinWeightData
(collect_skin_weights / apply_skin_weights), for adapters of your own.
"""

from wipskin.formats import scene

__all__ = ["feedback", "scene", "skin_engine"]


def __getattr__(name):
    # feedback and skin_engine need maya.api.OpenMaya while scene needs only
    # maya.cmds, so they load on first use: importing scene alone stays as
    # light as before.
    if name == "feedback":
        from wipskin.core import feedback

        return feedback

    if name == "skin_engine":
        from wipskin.formats.skin import engine

        return engine

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
