from __future__ import annotations

import abc
from dataclasses import dataclass

from logging import getLogger
from types import TracebackType
from typing import Optional, Type, List

from .vcp_codes import VCPCodes, VCPCommand


class VCPError(Exception):
    pass


class VCPIOError(VCPError):
    pass


class VCPPermissionError(VCPError):
    pass


class VCPValueError(VCPError, ValueError):
    pass


@dataclass
class VCPFeatureReturn:
    value: int
    max: int


VCP_TIMEOUT = 0.04  # at least 40ms per the DDC-CI specification


class VCP(abc.ABC):

    @abc.abstractmethod # pragma: no cover
    def __init__(self):
        self.logger = getLogger(__name__)
        self.code_maximum: dict[int, int] = {}
        self._in_ctx = False

    @abc.abstractmethod # pragma: no cover
    def __enter__(self):
        self._in_ctx = True
        return self

    @abc.abstractmethod # pragma: no cover
    def __exit__(
            self,
            exception_type: Optional[Type[BaseException]],
            exception_value: Optional[BaseException],
            exception_traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        self._in_ctx = False
        return False

    def set_vcp_feature(self, code: VCPCommand, value: int, timeout: float = VCP_TIMEOUT):
        assert self._in_ctx, "This function must be run within the context manager"
        if not code.writeable:
            raise TypeError(f"cannot write read-only code: {code}")
        elif code.readable and not code.discrete:
            maximum = self.get_vcp_feature_max(code, timeout)
            if value > maximum:
                raise ValueError(f"value of {value} exceeds code maximum of {maximum} for {code.name}")
        self.logger.debug(f"SetVCPFeature(_, {repr(code)}, {value=})")
        self._set_vcp_feature(code, value, timeout)

    # TODO: discuss whether we need/want timeout here
    @abc.abstractmethod # pragma: no cover
    def _set_vcp_feature(self, code: VCPCommand, value: int, timeout: float):
        pass

    def get_vcp_feature(self, com: VCPCommand, timeout: float = VCP_TIMEOUT) -> VCPFeatureReturn:
        assert self._in_ctx, "This function must be run within the context manager"
        if not com.readable:
            raise TypeError(f"cannot read write-only code: {com}")
        self.logger.debug(f"GetVCPFeatureAndVCPFeatureReply(_, {repr(com)}, None, _, _)")
        ret = self._get_vcp_feature(com, timeout)
        if com.code == VCPCodes.input_source:
            # The input source sometimes has a high byte that needs to be masked out.
            # Requires further research. Just copy monitorcontrol for now and ignore it.
            ret = VCPFeatureReturn(ret.value & 0xff, ret.max & 0xff)
        if not com.discrete:
            self.code_maximum[com.code] = ret.max
        return ret

    @abc.abstractmethod # pragma: no cover
    def _get_vcp_feature(self, code: VCPCommand, timeout: float) -> VCPFeatureReturn:
        pass

    def get_vcp_capabilities(self, timeout: float = VCP_TIMEOUT) -> str:
        assert self._in_ctx, "This function must be run within the context manager"
        return self._get_vcp_capabilities_str(timeout)

    @abc.abstractmethod # pragma: no cover
    def _get_vcp_capabilities_str(self, timeout: float) -> str:
        pass

    def get_vcp_feature_max(self, com: VCPCommand, timeout: float = VCP_TIMEOUT) -> int:
        assert self._in_ctx, "This function must be run within the context manager"
        if not com.readable:
            raise TypeError(f"code must be readable: {com.name}")
        # code.value.value seems awkward, but we do NOT want to store max keys as VCPCodes, so that we can
        # support non_specification feature codes. Though...
        # TODO: that might mean VCPCommand needs to store int, not
        #   VCPCode as the value
        feature_code = com.code
        if feature_code in self.code_maximum:
            return self.code_maximum[feature_code]
        else:
            maximum = self.get_vcp_feature(com, timeout).max
            self.code_maximum[feature_code] = maximum
            return maximum

    @staticmethod
    @abc.abstractmethod # pragma: no cover
    def get_vcps() -> List[VCP]:
        pass


@dataclass
class Capability:
    cap: int | str
    values: list[int | str] | None


def _get_close_paren_index(caps_str: str, open_index: int) -> int:
    assert caps_str[open_index] == '('
    depth = 1
    for close_index in range(open_index + 1, len(caps_str)):
        char = caps_str[close_index]
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if not depth:
                break
    else:
        assert open_index + 1 == len(caps_str)
        return len(caps_str)
    if depth > 0:
        # '(' without ')'; just ignore it
        return len(caps_str)
    assert caps_str[close_index] == ')'
    return close_index


def _parse_caps_hex_list(caps_str: str) -> list[Capability]:
    # Data is a list of two-digit hexadecimal op-codes, possibly with associated enumeration values.
    caps_data = []
    index = 0
    while index < len(caps_str):
        if caps_str[index] == '(':
            close_index = _get_close_paren_index(caps_str, index)
            substr = caps_str[index + 1:close_index]
            value = _parse_caps_hex_list(substr)
            if caps_data and caps_data[-1].values is None:
                # Associate enumeration values with op-code
                caps_data[-1].values = [cap.cap if cap.values is None else cap for cap in value]
            else:
                # Enumeration values have no prior op-code; this should not strictly happen.
                # Examples: "vcps((01 02) 03 04)", or "vcps(01(02 03) (04 05) 06)", or
                # "vcps(01(02(03)))", etc.
                caps_data.extend(value)
            index = close_index + 1
        else:
            size = 2 if index + 1 < len(caps_str) and caps_str[index + 1] != '(' else 1
            value = caps_str[index:index + size]
            try:
                value = int(value, 16)
            except ValueError:
                # invalid hex value; just ignore it and keep the string
                pass
            cap = Capability(value, None)
            caps_data.append(cap)
            index += size
    return caps_data


Capabilities = int | str | list[Capability] | list[int] | dict[str, 'Capabilities']


def _parse_caps_dict(caps_str: str) -> dict[str, Capabilities]:
    # Data is a series of key-value pairs.
    # Some keys have standard meanings and expected value formats.
    known_keys = {'prot', 'cmds', 'vcp', 'type', 'mccs_ver', 'asset_eep', 'mpu_ver', 'model',
                  'mswhql', 'gamma_table', 'c_tmp_ofst'}
    caps_data = {}
    key = ''
    index = 0
    while index < len(caps_str):
        char = caps_str[index]
        if char == '(':
            close_index = _get_close_paren_index(caps_str, index)
            substr = caps_str[index + 1:close_index]
            # Apple Cinema Display monitors are known to use uppercase "VCP" keys.
            # LG 24UD58 monitors are known to report the "model" value without a key,
            # i.e. "24UD58cmds(...)" instead of "model(24UD58)cmds(...)".
            for known_key in known_keys:
                if key.lower().endswith(known_key):
                    extra, key = key[:-len(known_key)], known_key
                    if extra:
                        # Treat the extra prefix as a key with no value
                        caps_data[extra] = {}
                    break
            # Some keys' values are expected to be lists of two-digit hexadecimal op-codes:
            # "cmds" lists supported monitor device protocol commands, and "vcp" lists
            # monitor control panel functions (some with associated enumeration values).
            # These keys may have a suffix, e.g. "vcp_p02" or "vcp_p10".
            if any(key.lower().startswith(k) for k in {'cmds', 'vcp'}):
                # Remove all whitespace; it should not be meaningful, and hinders parsing.
                substr = substr.replace(' ', '').replace('\t', '')
                value = _parse_caps_hex_list(substr)
            else:
                value = _parse_caps_dict(substr)
            if key:
                # Associate key with its value.
                caps_data[key] = value
                key = ''
            elif isinstance(value, dict) and not caps_data:
                # The entire capabilities string is a parenthesized key-value dict itself.
                caps_data = value
            else:
                # Value has no associated key; this should not strictly happen.
                # Examples: "(prot monitor)", or "(prot(monitor)(type)(LCD)", or
                # "(()(()())())", etc. Try to keep as much parsed data as possible anyway.
                # It cannot be a hex list, because that would have been handled already.
                assert not isinstance(value, list)
                if isinstance(value, (int, str)):
                    value = {value: {}}
                # Un-nest the value, making sure that any keys shared with prior data
                # do not overwrite prior data values.
                caps_data = value | caps_data
            index = close_index + 1
        elif char.isspace():
            if key:
                # Asus PB287 monitors are known to report the "model" value without parentheses,
                # i.e. "model LCDPB287" instead of "model(LCDPB287)".
                value = ''
                while index < len(caps_str) and caps_str[index].isspace():
                    index += 1
                while index < len(caps_str) and not caps_str[index].isspace() and caps_str[index] != '(':
                    value += caps_str[index]
                    index += 1
                # Associate key with its value.
                caps_data[key] = value
                key = ''
            index += 1
        else:
            key += char
            index += 1
    if key:
        # The final key does not have a value.
        if caps_data:
            caps_data[key] = {}
        else:
            # This must be parsing a value substring of a full capabilities string;
            # just return the string itself, e.g. "monitor" in "(prot(monitor))".
            caps_data = key
    return caps_data


def parse_capabilities(caps_str: str) -> dict[str, Capabilities]:
    caps_dict = _parse_caps_dict(caps_str)
    if not isinstance(caps_dict, dict):
        # The entire string is malformed to not be a series of key-value pairs.
        caps_dict = {'': caps_dict}
    return caps_dict
