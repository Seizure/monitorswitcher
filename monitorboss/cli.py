from argparse import ArgumentParser
from collections.abc import Sequence
from logging import getLogger, DEBUG
from time import sleep

from monitorboss import MonitorBossError, indentation
from monitorboss.config import Config, get_config
from monitorboss.impl import list_monitors, get_feature, set_feature, toggle_feature, get_vcp_capabilities
from monitorboss.info import feature_data, monitor_data, value_data, capability_data, capability_summary_data
from monitorboss.output import caps_raw_output, caps_parsed_output, list_mons_output, \
    get_feature_output, set_feature_output, tog_feature_output
from pyddc import parse_capabilities, get_vcp_com, VCPError
from pyddc.vcp_codes import VCPCodes, VCPCommand

_log = getLogger(__name__)
_INDENT_LEVEL = 4 if _log.level >= DEBUG else None


# TODO: This does not allow for custom/OEM codes as is (for when we add such)
def _check_feature(feature: str, cfg: Config) -> VCPCommand:
    _log.debug(f"check feature: {feature!r}")
    if feature.isdigit():
        for code in VCPCodes:
            if int(feature) == code.value:
                return get_vcp_com(code.value)
        raise MonitorBossError(
            f"{feature} is not a valid feature code."
        )
    else:
        for alias, code in cfg.feature_aliases.items():
            if alias == feature:
                return get_vcp_com(code)
        for code in VCPCodes:
            com = get_vcp_com(code.value)
            if com.name == feature:
                return com
        raise MonitorBossError(
            f"{feature} is not a valid feature alias."
        )


def _check_mon(mon: str, cfg: Config) -> int:
    _log.debug(f"check monitor: {mon!r}")
    mon = cfg.monitor_names.get(mon, mon)
    try:
        return int(mon)
    except ValueError as err:
        raise MonitorBossError(
            f"{mon} is not a valid monitor.\n"
            f"Valid monitors are: {', '.join(cfg.monitor_names)}, or an ID number."
        ) from err


def _check_val(com: VCPCommand, val: str, cfg: Config) -> int:
    _log.debug(f"check feature value: ftr {com.name}, value {val}")
    # Check if input is a positive integer, and if so, just return it.
    if val.isdigit():
        return int(val)
    # if not, we need to check for valid params and aliases...
    else:
        # ...so first check if there is a param name...
        if val in com.param_names:
            return com.param_names[val]
        # ... and if not, check if there is a matching alias table for this feature and if so alias for this value...
        if com.name in cfg.value_aliases and val in cfg.value_aliases[com.name]:
            return cfg.value_aliases[com.name][val]
    # If we got here, an invalid value was provided
    error_text = f"{val} is not a valid value for feature \"{com.name}\".\nValid values are:\n"
    if com.param_names:
        error_text += f"{indentation}- [PARAM NAMES]: {', '.join(com.param_names.keys())}\n"
    if com.name in cfg.value_aliases:
        error_text += f"{indentation}- [CONFIG ALIASES]: {', '.join(cfg.value_aliases[com.name].keys())}\n"
    error_text += f"{indentation}- a code number (non-negative integer)\n"
    error_text += f"NOTE: A particular monitor may only support some of these values. Check your monitor's specs for the inputs it accepts."
    raise MonitorBossError(error_text)


def _list_mons(args, cfg: Config):
    _log.debug(f"list monitors: {args}")
    print(list_mons_output([monitor_data(index, cfg) for index, _ in enumerate(list_monitors())], args.json))


def _get_caps(args, cfg: Config):
    _log.debug(f"get capabilities: {args}")
    mons = [_check_mon(m, cfg) for m in args.monitor]
    rawcaps_list = []
    for i, m in enumerate(mons):
        rawcaps_list.append(get_vcp_capabilities(m))

    if args.raw:
        moncaps_list = []
        for mon, caps in zip(mons, rawcaps_list):
            mdata = monitor_data(mon, cfg)
            moncaps_list.append((mdata, caps))
        print(caps_raw_output(moncaps_list, args.json))
        return

    fullcaps_list = [capability_data(parse_capabilities(rawcap), cfg) for rawcap in rawcaps_list]

    if args.summary:
        summarycaps_list = [capability_summary_data(fullcap) for fullcap in fullcaps_list]
        moncaps_list = []
        for mon, caps in zip(mons, summarycaps_list):
            mdata = monitor_data(mon, cfg)
            moncaps_list.append((mdata, caps))
        print(caps_parsed_output(moncaps_list, args.json))
        return

    moncaps_list = []
    for mon, caps in zip(mons, fullcaps_list):
        mdata = monitor_data(mon, cfg)
        moncaps_list.append((mdata, caps))
    print(caps_parsed_output(moncaps_list, args.json))


def _get_feature(args, cfg: Config):
    _log.debug(f"get feature: {args}")
    vcpcom = _check_feature(args.feature, cfg)
    mons = [_check_mon(m, cfg) for m in args.monitor]
    cur_vals = []
    max_vals = []
    for i, m in enumerate(mons):
        try:
            ret = get_feature(m, vcpcom, cfg.wait_internal_time)
            cur_vals.append(ret.value)
            # TODO: discuss whether we actually want to obscure discrete "maxes"... is there a reason to?
            #   could be assigned a different name in json/strings for when it's discreet, eg "options"
            max_vals.append(None if vcpcom.discrete else ret.max)
        except (VCPError, TypeError) as err:


        if i + 1 < len(mons):
            sleep(cfg.wait_get_time)
    monvalmax_list = []
    fdata = feature_data(vcpcom.code, cfg)
    for mon, val, maximum in zip(mons, cur_vals, max_vals):
        mdata = monitor_data(mon, cfg)
        vdata = value_data(fdata.code, val, cfg)
        monvalmax_list.append((mdata, vdata, maximum))

    print(get_feature_output(fdata, monvalmax_list, args.json))


def _set_feature(args, cfg: Config):
    _log.debug(f"set feature: {args}")
    vcpcom = _check_feature(args.feature, cfg)
    mons = [_check_mon(m, cfg) for m in args.monitor]
    val = _check_val(vcpcom, args.value, cfg)
    new_vals = []
    for i, m in enumerate(mons):
        new_vals.append(set_feature(m, vcpcom, val, cfg.wait_internal_time))
        if i + 1 < len(mons):
            sleep(cfg.wait_set_time)
    new_vals = [set_feature(m, vcpcom, val, cfg.wait_internal_time) for m in mons]
    monval_list = []
    fdata = feature_data(vcpcom.code, cfg)
    for mon, new_val in zip(mons, new_vals):
        mdata = monitor_data(mon, cfg)
        vdata = value_data(fdata.code, new_val, cfg)
        monval_list.append((mdata, vdata))

    print(set_feature_output(fdata, monval_list, args.json))


def _tog_feature(args, cfg: Config):
    _log.debug(f"toggle feature: {args}")
    vcpcom = _check_feature(args.feature, cfg)
    mons = [_check_mon(m, cfg) for m in args.monitor]
    val1 = _check_val(vcpcom, args.value1, cfg)
    val2 = _check_val(vcpcom, args.value2, cfg)
    tog_vals = []
    for i, m in enumerate(mons):
        tog_vals.append(toggle_feature(m, vcpcom, val1, val2, cfg.wait_internal_time))
        if i + 1 < len(mons):
            sleep(cfg.wait_set_time)
    monvals_list = []
    fdata = feature_data(vcpcom.code, cfg)
    for mon, tog_val in zip(mons, tog_vals):
        mdata = monitor_data(mon, cfg)
        vdata_old = value_data(fdata.code, tog_val.old, cfg)
        vdata_new = value_data(fdata.code, tog_val.new, cfg)
        monvals_list.append((mdata, vdata_old, vdata_new))

    print(tog_feature_output(fdata, monvals_list, args.json))


text = "Commands for manipulating and polling your monitors"
parser = ArgumentParser(description="Boss your monitors around.")
parser.add_argument("--config", type=str, help="the config file path to use")
parser.add_argument("--json", action='store_true', help="return output in json format")

mon_subparsers = parser.add_subparsers(title="monitor commands", help=text, dest="subcommand", required=True)

text = "List all available monitors"
list_parser = mon_subparsers.add_parser("list", help=text, description=text)
list_parser.set_defaults(func=_list_mons)

text = "Get the capabilities dictionary of a monitor"
description = ("Get the capabilities of a monitor. If no flags are used, the entire capabilities string is parsed into "
               "a structured format with human-readable names provided for known VCP codes and their defined options.")
caps_parser = mon_subparsers.add_parser("caps", help=text, description=description)
caps_parser.set_defaults(func=_get_caps)
caps_parser.add_argument("monitor", type=str, nargs="+", help="the monitor to retrieve capabilities from")
caps_exclusive_flags = caps_parser.add_mutually_exclusive_group()
caps_exclusive_flags.add_argument("-r", "--raw", action='store_true', help="return the original, unparsed capabilities string")
caps_exclusive_flags.add_argument("-s", "--summary", action='store_true', help="return a highly formatted and abridged summary of the capabilities")

text = "returns the value of a given feature"
get_parser = mon_subparsers.add_parser("get", help=text, description=text)
get_parser.set_defaults(func=_get_feature)
get_parser.add_argument("monitor", type=str, nargs="+", help="the monitor(s) to control")
get_parser.add_argument("feature", type=str, help="the feature to return")

text = "sets a given feature to a given value"
set_parser = mon_subparsers.add_parser("set", help=text, description=text)
set_parser.set_defaults(func=_set_feature)
set_parser.add_argument("monitor", type=str, nargs="+", help="the monitor(s) to control")
set_parser.add_argument("feature", type=str, help="the feature to set")
set_parser.add_argument("value", type=str, help="the value to set the feature to")

text = "toggles a given feature between two given values"
tog_parser = mon_subparsers.add_parser("tog", help=text, description=text)
tog_parser.set_defaults(func=_tog_feature)
tog_parser.add_argument("monitor", type=str, nargs="+", help="the monitor(s) to control")
tog_parser.add_argument("feature", type=str, help="the feature to toggle")
tog_parser.add_argument("value1", type=str, help="the first value to toggle between")
tog_parser.add_argument("value2", type=str, help="the second value to toggle between")

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
