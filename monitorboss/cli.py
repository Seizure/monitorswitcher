from argparse import ArgumentParser
from collections.abc import Sequence
from logging import getLogger
from pprint import PrettyPrinter
from time import sleep

from monitorboss import MonitorBossError
from monitorboss.config import Config, get_config
from monitorboss.impl import Feature, FeatureData
from monitorboss.impl import list_monitors, get_attribute, set_attribute, toggle_attribute, get_vcp_capabilities
from pyddc import parse_capabilities, get_vcp_com
from pyddc.vcp_codes import VCPCodes, VCPCommand

_log = getLogger(__name__)


#TODO: This does not allow for custom/OEM codes as is (for when we add such)
def _check_feature(feature: str, cfg: Config) -> VCPCommand:
    _log.debug(f"check attribute: {feature!r}")
    if feature.isdigit():
        for code in VCPCodes:
            if int(feature) == code.value:
                return get_vcp_com(code.value)
        raise MonitorBossError(
            f"{feature} is not a valid feature code."
            # TODO: should probably add a command for printing out valid codes, and refer to it here
        )
    else:
        for alias, code in cfg.feature_aliases.items():
            if alias == feature:
                return get_vcp_com(code)
        raise MonitorBossError(
            f"{feature} is not a valid feature alias."
            # TODO: should probably add a command for printing out valid aliases, and refer to it here
        )


def _check_mon(mon: str, cfg: Config) -> int:
    _log.debug(f"check monitor: {mon!r}")
    mon = cfg.monitor_names.get(mon, mon)
    try:
        return int(mon)
    except ValueError as err:
        raise MonitorBossError(
            f"{mon} is not a valid monitor.\n"
            "Valid monitors are: {', '.join(cfg.monitor_names)}, or an ID number."
        ) from err


# TODO: this will need to be modified a lot when we allow for value aliases, and all the commands
# TODO: maybe this can already be simplified now that we use VCPCodes? Do we need separate cases for the checking?
#   Or just for the error text? Maybe even that can go in feature data?
def _check_val(vcpcode: VCPCodes, val: str, cfg: Config) -> int:
    _log.debug(f"check attribute value: attr {get_vcp_com(vcpcode.value).name}, value {val}")
    match vcpcode:
        case VCPCodes.input_source:
            if val in cfg.input_source_names:
                return cfg.input_source_names[val]
            elif val in get_vcp_com(vcpcode.value).param_names:
                return get_vcp_com(vcpcode.value).param_names[val]
            try:
                return int(val)
            except ValueError as err:
                raise MonitorBossError(
                    f"{val} is not a valid input source.\n"
                    f"""Valid input sources are: {
                        ', '.join(list(get_vcp_com(vcpcode.value).param_names.keys()) + list(cfg.input_source_names))
                    }, or a code number (non-negative integer).\n"""
                    "NOTE: A particular monitor will probably support only some of these values. "
                    "Check your monitor's specs for the inputs it accepts."
                ) from err

        case VCPCodes.image_contrast:
            try:
                return int(val)
            except ValueError as err:
                raise MonitorBossError(
                    f"{val} is not a valid contrast value.\n"
                    "Valid contrast values are non-negative integers."
                ) from err

        case VCPCodes.image_luminance:
            try:
                return int(val)
            except ValueError as err:
                raise MonitorBossError(
                    f"{val} is not a valid luminance value.\n"
                    "Valid luminance values are non-negative integers"
                ) from err

        case VCPCodes.display_power_mode:
            if val in get_vcp_com(vcpcode.value).param_names:
                return get_vcp_com(vcpcode.value).param_names[val]
            try:
                return int(val)
            except ValueError as err:
                raise MonitorBossError(
                    f"{val} is not a valid power mode.\n"
                    f"""Valid power modes are: {
                        ', '.join(list(get_vcp_com(vcpcode.value).param_names.keys()))
                    }, or a code number (non-negative integer).\n"""
                    "NOTE: A particular monitor will probably support only some of these values. "
                    "Check your monitor's specs for the inputs it accepts."
                ) from err

        case VCPCodes.image_color_preset:
            if val in get_vcp_com(vcpcode.value).param_names:
                return get_vcp_com(vcpcode.value).param_names[val]
            try:
                return int(val)
            except ValueError as err:
                raise MonitorBossError(
                    f"{val} is not a valid color preset.\n"
                    f"""Valid color presets are: {
                        ', '.join(list(get_vcp_com(vcpcode.value).param_names.keys()))
                    }, or a code number (non-negative integer).\n"""
                    "NOTE: A particular monitor will probably support only some of these values. "
                    "Check your monitor's specs for the inputs it accepts."
                ) from err


# Config is not currently used, but it will be when we allow feature aliases, so just including it
def _feature_str(com: VCPCommand | int, cfg: Config) -> str:
    if isinstance(com, int):
        com = get_vcp_com(com) if get_vcp_com(com) is not None else com
    return f"{com.desc} ({com.value})"


def _monitor_str(mon: int, cfg: Config) -> str:
    monstr = f"monitor #{mon} "
    aliases = ""
    for v, k in cfg.monitor_names.items():
        if mon == k:
            aliases += v+", "
    if aliases:
        monstr += f"({aliases[:-2]})"

    return monstr.strip()


# TODO: this will need to radically change when we allow aliases for arbitrary/all features
def _value_str(com: VCPCommand | int, value: int, cfg: Config) -> str:
    valstr = f"{value}"
    param = ""
    aliases = ""
    if isinstance(com, int):
        com = get_vcp_com(com) if get_vcp_com(com) is not None else com
    if not isinstance(com, VCPCommand):
        return str(com)
    for v, k in com.param_names.items():
        if value == k:
            param = v
    if com.value == VCPCodes.input_source:
        for v, k in cfg.input_source_names.items():
            if value == k:
                aliases += v+", "
    if aliases:
        aliases = aliases[:-2]
    valstr += f" ({param + (' | ' if param and aliases else '') + aliases})" if param or aliases else ""
    return valstr


def _list_mons(args, cfg: Config):
    _log.debug(f"list monitors: {args}")
    for index, monitor in enumerate(list_monitors()):
        print(f"{_monitor_str(index, cfg)}")


def _get_caps(args, cfg: Config):
    _log.debug(f"get capabilities: {args}")
    mon = _check_mon(args.mon, cfg)
    caps_raw = get_vcp_capabilities(mon)

    if args.raw:
        print(caps_raw)
        return

    caps_dict = parse_capabilities(caps_raw)
    for s in caps_dict:
        if s.lower().startswith("cmd") or s.lower().startswith("vcp"):
            for i, c in enumerate(caps_dict[s]):
                cap = caps_dict[s][i]
                com = get_vcp_com(int(cap.cap))
                if com is not None:
                    cap.cap = _feature_str(int(cap.cap), cfg)
                    if cap.values is not None:
                        for x, p in enumerate(cap.values):
                            cap.values[x] = _value_str(com, p, cfg)

    if args.summary:
        summary = _monitor_str(mon, cfg)
        summary += ":"

        if caps_dict["type"]:
            summary += f" {caps_dict['type']}"
        if caps_dict["type"] and caps_dict["model"]:
            summary += ","
        if caps_dict["model"]:
            summary += f" model {caps_dict['model']}"
        summary += '\n'
        for s in caps_dict:
            if s.lower().startswith("vcp"):
                for c in caps_dict[s]:
                    if isinstance(c.cap, str) and (str(VCPCodes.input_source) in c.cap or str(VCPCodes.image_color_preset) in c.cap):
                        summary += f"  - {c.cap}: {', '.join(map(str, c.values))}\n"
        print(summary)
        return

    pprinter = PrettyPrinter(indent=4, sort_dicts=True)
    pprinter.pprint(caps_dict)


def _get_attr(args, cfg: Config):
    _log.debug(f"get attribute: {args}")
    vcpcom = _check_feature(args.attr, cfg)
    mons = [_check_mon(m, cfg) for m in args.mon]
    cur_vals = []
    max_vals = []
    for i, m in enumerate(mons):
        ret = get_attribute(m, vcpcom, cfg.wait_internal_time)
        cur_vals.append(ret.value)
        max_vals.append(None if vcpcom.discrete else ret.max)
        if i+1 < len(mons):
            sleep(cfg.wait_get_time)
    for mon, val, maximum in zip(mons, cur_vals, max_vals):
        print(f"{_feature_str(vcpcom, args)} for {_monitor_str(mon, cfg)} is {_value_str(vcpcom, val, cfg)}" + (f" (Maximum: {_value_str(vcpcom, maximum, cfg)})" if maximum is not None else ""))


def _set_attr(args, cfg: Config):
    _log.debug(f"set attribute: {args}")
    vcpcom = _check_feature(args.attr, cfg)
    mons = [_check_mon(m, cfg) for m in args.mon]
    val = _check_val(vcpcom.value, args.val, cfg)
    new_vals = []
    for i, m in enumerate(mons):
        new_vals.append(set_attribute(m, vcpcom, val, cfg.wait_internal_time))
        if i + 1 < len(mons):
            sleep(cfg.wait_set_time)
    new_vals = [set_attribute(m, vcpcom, val, cfg.wait_internal_time) for m in mons]
    for mon, new_val in zip(mons, new_vals):
        print(f"set {_feature_str(vcpcom, args)} for {_monitor_str(mon, cfg)} to {_value_str(vcpcom, new_val, cfg)}")


def _tog_attr(args, cfg: Config):
    _log.debug(f"toggle attribute: {args}")
    vcpcom = _check_feature(args.attr, cfg)
    mons = [_check_mon(m, cfg) for m in args.mon]
    val1 = _check_val(vcpcom.value, args.val1, cfg)
    val2 = _check_val(vcpcom.value, args.val2, cfg)
    new_vals = []
    for i, m in enumerate(mons):
        new_vals.append(toggle_attribute(m, vcpcom, val1, val2, cfg.wait_internal_time))
        if i + 1 < len(mons):
            sleep(cfg.wait_set_time)
    for mon, tog_val in zip(mons, new_vals):
        print(f"toggled {_feature_str(vcpcom, args)} for {_monitor_str(mon, cfg)} from {_value_str(vcpcom, tog_val.old, cfg)} to {_value_str(vcpcom, tog_val.new, cfg)}")


text = "Commands for manipulating and polling your monitors"
parser = ArgumentParser(description="Boss your monitors around.")
parser.add_argument("--config", type=str, help="the config file path to use")

mon_subparsers = parser.add_subparsers(title="monitor commands", help=text, dest="subcommand", required=True)

text = "List all available monitors"
list_parser = mon_subparsers.add_parser("list", help=text, description=text)
list_parser.set_defaults(func=_list_mons)

text = "Get the capabilities dictionary of a monitor"
description = ("Get the capabilities dictionary of a monitor. By default, this command parses the standard "
               "capabilities string into a structured and readable format, as well as provides human-readable names"
               "for known VCP codes and their defined options. If the --raw option is used, all other arguments will "
               "be ignored. Otherwise, if the --summary argument is used, all other arguments will be ignored.")
caps_parser = mon_subparsers.add_parser("caps", help=text, description=description)
caps_parser.set_defaults(func=_get_caps)
caps_parser.add_argument("mon", type=str, help="the monitor to retrieve capabilities from")
caps_parser.add_argument("-r", "--raw", action='store_true', help="return the original, unparsed capabilities string")
caps_parser.add_argument("-s", "--summary", action='store_true', help="return a highly formatted and abridged summary of the capabilities")

text = "return the value of a given attribute"
get_parser = mon_subparsers.add_parser("get", help=text, description=text)
get_parser.set_defaults(func=_get_attr)
get_parser.add_argument("attr", type=str, help="the attribute to return")
get_parser.add_argument("mon", type=str, nargs="+", help="the monitor to control")

text = "sets a given attribute to a given value"
set_parser = mon_subparsers.add_parser("set", help=text, description=text)
set_parser.set_defaults(func=_set_attr)
set_parser.add_argument("attr", type=str, help="the attribute to set")
set_parser.add_argument("val", type=str, help="the value to set the attribute to")
set_parser.add_argument("mon", type=str, nargs="+", help="the monitor(s) to control")

text = "toggles a given attribute between two given values"
tog_parser = mon_subparsers.add_parser("tog", help=text, description=text)
tog_parser.set_defaults(func=_tog_attr)
tog_parser.add_argument("attr", type=str, help="the attribute to toggle")
tog_parser.add_argument("val1", type=str, help="the first value to toggle between")
tog_parser.add_argument("val2", type=str, help="the second value to toggle between")
tog_parser.add_argument("mon", type=str, nargs="+", help="the monitor(s) to control")

# conf set {mon_alias, input_alias} alias id<int> [-f]
# conf set wait time<float>
# conf rm {mon_alias, input_alias} alias
# command for starting guided monitor alias wizard
# command for starting guided input alias wizard (can be retrieved from VCP/"list" command)
# -f : perform set without confirmation even if alias already exists
# what should behavior be if removing an alias that doesn't exist?

# We're done with the subparsers
del text
del description


def get_help_texts():
    return {'': parser.format_help()} | {name: subparser.format_help() for name, subparser in
                                         mon_subparsers.choices.items()}


def run(args: str | Sequence[str] | None = None):
    _log.debug(f"run CLI: {args}")
    if isinstance(args, str):
        args = args.split()
    args = parser.parse_args(args)
    try:
        cfg = get_config(args.config)
        args.func(args, cfg)
    except MonitorBossError as err:
        parser.error(str(err))
