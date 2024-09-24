import json
from textwrap import dedent

import test.pyddc
from pyddc import get_vcp_com
from pyddc.vcp_codes import VCPCodes
from test.pyddc.vcp_dummy import DummyVCP as VCP
import pyddc
pyddc.VCP = VCP
from monitorboss import config, cli, info


def test_list_human(test_conf_file, capsys):
    expected = dedent(f"""\
    {info.monitor_str(info.MonitorData(0, tuple(["foo"])))}
    {info.monitor_str(info.MonitorData(1, tuple(["bar", "baz"])))}
    {info.monitor_str(info.MonitorData(2, tuple()))}
    """)
    cli.run(f"--config {test_conf_file.as_posix()} list")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""
    
    
def test_list_json(test_conf_file, capsys):
    mdata0 = info.MonitorData(0, tuple(["foo"]))
    mdata1 = info.MonitorData(1, tuple(["bar", "baz"]))
    mdata2 = info.MonitorData(2, tuple())
    expected = json.dumps({"list": {"monitor": mdata0.serialize()}}) + "\n"
    expected += json.dumps({"list": {"monitor": mdata1.serialize()}}) + "\n"
    expected += json.dumps({"list": {"monitor": mdata2.serialize()}}) + "\n"
    cli.run(f"--config {test_conf_file.as_posix()} --json list")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_caps_raw_human(test_conf_file, capsys):
    expected = test.pyddc.CAPS_STR + "\n"
    cli.run(f"--config {test_conf_file.as_posix()} caps --raw 0")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_caps_raw_json(test_conf_file, capsys):
    expected = json.dumps({"caps": {"raw": test.pyddc.CAPS_STR}}) + "\n"
    cli.run(f"--config {test_conf_file.as_posix()} --json caps --raw 0")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


# TODO: this is going to be annoying, do it properly later
def test_caps_dict_human(test_conf_file, capsys):
    cli.run(f"--config {test_conf_file.as_posix()} caps 0")
    output = capsys.readouterr()
    assert output.out  # TODO: actually test something meaningful
    assert output.err == ""
    
    
def test_caps_dict_json(test_conf_file, capsys):
    pass  # TODO: stub


# TODO: this is going to be annoying, do it properly later
def test_caps_summary_human(test_conf_file, capsys):
    cli.run(f"--config {test_conf_file.as_posix()} caps --summary 0")
    output = capsys.readouterr()
    assert output.out  # TODO: actually test something meaningful
    assert output.err == ""
    

def test_caps_summary_json(test_conf_file, capsys):
    pass  # TODO: stub


def test_get_feature_human(test_conf_file, capsys):
    code = VCPCodes.image_luminance
    cfg = config.get_config(test_conf_file.as_posix())
    fstring = info.feature_str(info.feature_data(code.value, cfg))
    mstring = info.monitor_str(info.monitor_data(1, cfg))
    vstring = info.value_str(info.value_data(code.value, 75, cfg))
    expected = f"{fstring} for {mstring} is {vstring} (Maximum: 75)\n"
    cli.run(f"--config {test_conf_file.as_posix()} get 1 lum")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_get_feature_json(test_conf_file, capsys):
    code = VCPCodes.image_luminance
    cfg = config.get_config(test_conf_file.as_posix())
    fdata = info.feature_data(code.value, cfg)
    mdata = info.monitor_data(1, cfg)
    vdata = info.value_data(code.value, 75, cfg)
    expected = json.dumps({"get": {"monitor": mdata.serialize(), "feature": fdata.serialize(), "value": vdata.serialize()}}) + "\n"
    cli.run(f"--config {test_conf_file.as_posix()} --json get bar lum")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_set_feature_human(test_conf_file, capsys):
    code = VCPCodes.image_luminance
    cfg = config.get_config(test_conf_file.as_posix())
    fstring = info.feature_str(info.feature_data(code.value, cfg))
    mstring = info.monitor_str(info.monitor_data(1, cfg))
    vstring = info.value_str(info.value_data(code.value, 75, cfg))
    expected = f"set {fstring} for {mstring} to {vstring}\n"
    # TODO: I am setting it to the same thing it was, because this affects the state of the pyddc tests.
    #   there should be a way to have separate "Sessions" for each test, should figure out later
    cli.run(f"--config {test_conf_file.as_posix()} set bar lum 75")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_set_feature_json(test_conf_file, capsys):
    code = VCPCodes.image_luminance
    cfg = config.get_config(test_conf_file.as_posix())
    fdata = info.feature_data(code.value, cfg)
    mdata = info.monitor_data(1, cfg)
    vdata = info.value_data(code.value, 75, cfg)
    expected = json.dumps({"set": {"monitor": mdata.serialize(), "feature": fdata.serialize(), "value": vdata.serialize()}}) + "\n"
    cli.run(f"--config {test_conf_file.as_posix()} --json set bar lum 75")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_tog_feature_human(test_conf_file, capsys):
    code = VCPCodes.image_luminance
    cfg = config.get_config(test_conf_file.as_posix())
    fstring = info.feature_str(info.feature_data(code.value, cfg))
    mstring = info.monitor_str(info.monitor_data(1, cfg))
    vstring = info.value_str(info.value_data(code.value, 75, cfg))
    expected = f"toggled {fstring} for {mstring} from {vstring} to {vstring}\n"
    # TODO: I am setting it to the same thing it was, because this affects the state of the pyddc tests.
    #   there should be a way to have separate "Sessions" for each test, should figure out later
    cli.run(f"--config {test_conf_file.as_posix()} tog bar lum 75 75")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""


def test_tog_feature_json(test_conf_file, capsys):
    code = VCPCodes.image_luminance
    cfg = config.get_config(test_conf_file.as_posix())
    fdata = info.feature_data(code.value, cfg)
    mdata = info.monitor_data(1, cfg)
    vdata = info.value_data(code.value, 75, cfg)
    expected = json.dumps({"toggle": {"monitor": mdata.serialize(), "feature": fdata.serialize(), "original_value": vdata.serialize(), "new_value": vdata.serialize()}}) + "\n"
    cli.run(f"--config {test_conf_file.as_posix()} --json tog bar lum 75 75")
    output = capsys.readouterr()
    assert output.out == expected
    assert output.err == ""
