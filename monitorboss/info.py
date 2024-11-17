import textwrap
from dataclasses import dataclass

from frozendict import frozendict

from monitorboss import indentation
from monitorboss.config import Config
from pyddc import get_vcp_com
from pyddc.vcp_abc import Capabilities
from pyddc.vcp_codes import VCPCodes


@dataclass(frozen=True)
class FeatureData:
    name: str
    code: int
    aliases: tuple[str, ...]

    def serialize(self) -> dict:
        return {
            "code": self.code,
            **({"name": self.name} if self.name else {}),
            **({"aliases": self.aliases} if self.aliases else {}),
        }

    def __str__(self) -> str:
        return f"{self.name} ({self.code})" if self.name else str(self.code)


def feature_data(code: int, cfg: Config) -> FeatureData:
    com = get_vcp_com(code)
    if com:
        name = com.name
        aliases = [alias for alias, val in cfg.feature_aliases.items() if val == com.code]
    else:
        name = ""
        aliases = []
    return FeatureData(name, code, tuple(aliases))


@dataclass(frozen=True)
class MonitorData:
    id: int
    aliases: tuple[str, ...]

    def serialize(self) -> dict:
        return {
            "id": self.id,
            **({"aliases": self.aliases} if self.aliases else {}),
        }

    def __str__(self) -> str:
        return f"monitor #{self.id} ({', '.join(map(str, self.aliases))})" if self.aliases else f"monitor #{self.id}"


def monitor_data(mon: int, cfg: Config) -> MonitorData:
    return MonitorData(mon, tuple(alias for alias, val in cfg.monitor_names.items() if mon == val))


@dataclass(frozen=True)
class ValueData:
    value: int
    param: str
    aliases: tuple[str, ...]

    def serialize(self) -> dict:
        return {
            "value": self.value,
            **({"param": self.param} if self.param else {}),
            **({"aliases": self.aliases} if self.aliases else {}),
        }

    def __str__(self) -> str:
        data = ([f"PARAM: {self.param}"] if self.param else []) + ([f"ALIASES: {', '.join(map(str, self.aliases))}"] if self.aliases else [])
        return f"{self.value} ({' | '.join(data)})" if data else f"{self.value}"


def value_data(code: int, value: int, cfg: Config) -> ValueData:
    com = get_vcp_com(code)
    param = ""
    aliases = []
    if com:
        for key, val in com.param_names.items():
            if value == val:
                param = key
                break
        if com.name in cfg.value_aliases:
            aliases = [alias for alias, val in cfg.value_aliases[com.name].items() if value == val]
    return ValueData(value, param, tuple(aliases))


# TODO: do we want PYDDC to be the one to format things in a structure like this, rather than a dict?
@dataclass(frozen=True)
class CapabilityData:
    attributes: frozendict[str, str]
    cmds: frozendict[str, tuple[FeatureData, ...]]
    vcps: frozendict[str, frozendict[FeatureData, tuple[ValueData, ...]]]
    errata: frozendict[str, tuple[str, ...]] | None

    def serialize(self) -> dict:
        serialized = dict(self.attributes)
        cmds = {}
        for cmd, features in self.cmds.items():
            cmds[cmd] = [feature.serialize() for feature in features]
        serialized["cmds"] = cmds
        vcps = {}
        for vcp, vcp_features in self.vcps.items():
            vcp_data = []
            for feature, params in vcp_features.items():
                data = {"feature": feature.serialize()}
                if params:
                    data["params"] = [param.serialize() for param in params]
                vcp_data.append(data)
            vcps[vcp] = vcp_data
        serialized["vcps"] = vcps
        if self.errata:
            serialized["errata"] = dict(self.errata)
        return serialized

    def _attr_str(self) -> str:
        if not self.attributes:
            return ""
        return "\n".join(f"{attr}: {val}" for attr, val in self.attributes.items())

    def _cmds_str(self) -> str:
        if not self.cmds:
            return ""
        cmds = [f"{cmd}: {', '.join(map(str, values))}" for cmd, values in self.cmds.items()]
        if len(cmds) == 1:
            return cmds[0]
        return "CMDS:\n" + textwrap.indent("\n".join(cmds), indentation)

    def _vcp_str(self) -> str:
        if not self.vcps:
            return ""
        vcps = [
            f"{vcp}:\n" + textwrap.indent("\n".join(
                f"* {feature}" + (f": {', '.join(map(str, values))}" if values else "")
                for feature, values in features.items()
            ), indentation)
            for vcp, features in self.vcps.items()
        ]
        if len(vcps) == 1:
            return vcps[0]
        return "VCP:\n" + textwrap.indent("\n".join(vcps), indentation)

    def _errata_str(self) -> str:
        if not self.errata:
            return ""
        errata = {key: ", ".join(map(str, value)) for key, value in self.errata.items()}
        if len(errata) == 1 and not list(errata.keys())[0]:
            return f"Errata: {list(errata.values())[0]}"
        return "Errata:\n" + textwrap.indent("\n".join(
            f"{key}{': ' if key else ''}{values}"
            for key, values in errata.items()
        ), indentation)

    def __str__(self) -> str:
        sections = [self._attr_str(), self._cmds_str(), self._vcp_str(), self._errata_str()]
        return "\n".join(map(str, [s for s in sections if s]))


def capability_data(caps: dict[str, Capabilities], cfg) -> CapabilityData:
    # TODO: PYDDC definition of Capabilities currently allows for:
    #   - indefinitely nested caps.
    #   - non-int feature codes and values (passing cap.cap and cap.values data without checking)
    #   We do not account for this here, but that should change in PYDDC anyways
    cmds = frozendict({
        name: tuple(feature_data(f.cap, cfg) for f in cap) if cap else ()
        for name, cap in caps.items() if name.lower().startswith("cmd")
    })
    vcps = frozendict({
        name: frozendict({
            feature_data(f.cap, cfg): tuple(value_data(f.cap, v, cfg) for v in f.values) if f.values else ()
            for f in cap
        }) if cap else frozendict()
        for name, cap in caps.items() if name.lower().startswith("vcp")
    })
    info_fields = frozendict({
        name: cap
        for name, cap in caps.items() if name not in cmds and name not in vcps
    })
    errata: frozendict[str, tuple[str]] = frozendict()  # TODO: not sure how to find/parse out errata rn
    return CapabilityData(info_fields, cmds, vcps, errata)


# TODO: could possibly be merged with capability_data, and just include an argument for desired attributes
#   and features each, where 'None' means all (equivalent to capability_data) and supplying relevant lists
#   tells it what to filter
def capability_summary_data(caps_data: CapabilityData) -> CapabilityData:
    desired_attributes = {"type", "model"}
    attributes = {attr: value for attr, value in caps_data.attributes.items() if attr in desired_attributes}
    desired_features = {VCPCodes.input_source.value, VCPCodes.image_color_preset.value}
    vcp_features = {
        vcp: {feature: params for feature, params in features.items() if feature.code in desired_features}
        for vcp, features in caps_data.vcps.items() if features
    }
    return CapabilityData(frozendict(attributes), frozendict(), frozendict(vcp_features), frozendict())
