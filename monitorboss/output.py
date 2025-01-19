import json
import textwrap
from logging import getLogger, DEBUG

from monitorboss import indentation
from monitorboss.info import CapabilityData, FeatureData, ValueData, MonitorData

_log = getLogger(__name__)
_INDENT_LEVEL = 4 if _log.level >= DEBUG else None


def list_mons_output(mons: list[MonitorData], json_output: bool) -> str:
    if json_output:
        monlist = []
        for mon in mons:
            monlist.append({"monitor": mon.serialize()})
        return json.dumps({"list": monlist}, indent=_INDENT_LEVEL)

    return "\n".join(map(str, mons))

def get_feature_output_single(feature: FeatureData, value: ValueData, maximum: int | None, json_output: bool) -> str:
    if json_output:


def get_feature_output(feature: FeatureData, monvalues: list[tuple[MonitorData, ValueData, int | None]], json_output: bool) -> str:
    if json_output:
        monvalue_list = []
        for mon, value, maximum in monvalues:
            item = {"monitor": mon.serialize(), "value": value.serialize()}
            if maximum:
                item["max_value"] = maximum
            monvalue_list.append(item)
        return json.dumps({"get": {"feature": feature.serialize(), "values": monvalue_list}}, indent=_INDENT_LEVEL)

    return "\n".join(map(str, [f"{feature} for {mon} is {value}" + (f" (Maximum: {maximum})" if maximum else "") for mon, value, maximum in monvalues]))


def set_feature_output(feature: FeatureData, monvalues: list[tuple[MonitorData, ValueData]], json_output: bool) -> str:
    if json_output:
        monvalue_list = [{"monitor": mon.serialize(), "value": value.serialize()} for mon, value in monvalues]
        return json.dumps({"set": {"feature": feature.serialize(), "values": monvalue_list}}, indent=_INDENT_LEVEL)

    return "\n".join(map(str, [f"set {feature} for {mon} to {value}" for mon, value in monvalues]))


def tog_feature_output(feature: FeatureData, monvalues: list[tuple[MonitorData, ValueData, ValueData]], json_output) -> str:
    if json_output:
        monvalue_list = [{"monitor": mon.serialize(), "original_value": original.serialize(), "new_value": new.serialize()} for mon, original, new in monvalues]
        return json.dumps({"toggle": {"feature": feature.serialize(), "values": monvalue_list}}, indent=_INDENT_LEVEL)

    return "\n".join(map(str, [f"toggled {feature} for {mon} from {original} to {new}" for mon, original, new in monvalues]))


def caps_raw_output(moncaps: list[tuple[MonitorData, str]], json_output: bool) -> str:
    if json_output:
        moncaps_list = [{"monitor": mon.serialize(), "data": caps} for mon, caps in moncaps]
        return json.dumps({"caps": moncaps_list, "type": "raw"}, indent=_INDENT_LEVEL)

    return "\n".join(map(str, [f"Capability string for {mon}:\n{indentation}{caps}" for mon, caps in moncaps]))


def caps_parsed_output(moncaps: list[tuple[MonitorData, CapabilityData]], json_output: bool) -> str:
    if json_output:
        moncaps_list = [{"monitor": mon.serialize(), "data": caps.serialize()} for mon, caps in moncaps]
        return json.dumps({"caps": moncaps_list, "type": "full"}, indent=_INDENT_LEVEL)

    return "\n".join(map(str, [f"{mon}:\n{textwrap.indent(str(caps), indentation)}" for mon, caps in moncaps]))

