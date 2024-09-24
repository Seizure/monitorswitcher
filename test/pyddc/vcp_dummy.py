from __future__ import annotations

from types import TracebackType
from typing import List, Optional, Type

from pyddc import VCPCommand, VCPFeatureReturn, ABCVCP
from test.pyddc import CAPS_STR

supported_codes = {
    4: [],  # factory reset code (WO) TODO: should find a better WO command (with actual values)
    16: None,  # luminance (RW/continuous)
    18: None,  # contrast (RW/continuous)
    96: [27, 15, 17],  # input source code (RW/discreet); with params for USBC, dp1, and hdm1
    170: [1, 2, 4]  # image orientation (RO/discreet); with params for who knows what
}

current_values = {16: 75, 18: 75, 96: 27, 170: 2}  # lum is 75, input is USBC(27), image orientation is 2 (whatever that means)
unknown_max_values = {16: 80, 18: 100}


class DummyVCP(ABCVCP):
    def __init__(self):
        super().__init__()

    def __enter__(self):
        super().__enter__()

        return self

    def __exit__(
            self,
            exception_type: Optional[Type[BaseException]],
            exception_value: Optional[BaseException],
            exception_traceback: Optional[TracebackType],
    ) -> Optional[bool]:
        return super().__exit__(exception_type, exception_value, exception_traceback)

    def _set_vcp_feature(self, com: VCPCommand, value: int, timeout: float):
        del timeout # unused
        code = com.code
        if code not in supported_codes:
            # This is not defined behavior in practice, some monitors don't complain.
            # Therefor it is probably not worth testing against this result.
            raise OSError("The monitor does not support the specified VCP code.")
        if supported_codes[code] is None:
            if value > unknown_max_values[code]:
                raise ValueError(f"value of {value} exceeds code maximum of {unknown_max_values[code]} for {VCPCommand.name}")
            else:
                current_values[code] = value
        else:
            if value in supported_codes[code]:
                current_values[code] = value
            else:
                # This is not defined behavior in practice, some monitors don't complain.
                # Therefor it is probably not worth testing against this result.
                raise OSError("The monitor does not support the specified VCP code.")

    def _get_vcp_feature(self, com: VCPCommand, timeout: float) -> (int, int):
        del timeout # unused
        code = com.code
        if code not in supported_codes:
            # This is not defined behavior in practice, some monitors don't complain and just return garbage.
            # Therefor it is probably not worth testing against this result.
            raise OSError("The monitor does not support the specified VCP code.")
        if not com.discrete:
            maxv = unknown_max_values[code]
        else:
            # The max value on discrete features is the number of options, but there's nothing meaningful to
            #   test in that regard, and MonitorBoss doesn't use that info, so not worth worrying about
            maxv = 0
        return VCPFeatureReturn(current_values[code], maxv)

    def _get_vcp_capabilities_str(self, timeout: float) -> str:
        del timeout # unused
        return CAPS_STR

    @staticmethod
    def get_vcps() -> List[DummyVCP]:
        return [DummyVCP(), DummyVCP(), DummyVCP()]
