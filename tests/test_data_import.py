"""Log import: CSV, column mapping, CAN definitions, CAN logs, DBC, cleaning."""

from pathlib import Path

import numpy as np
import pytest
from helpers import SHIPPED_DATA

from bakbrommer_twin.data_import import can_log, clean, csv_log
from bakbrommer_twin.data_import.can_defs import (
    CanMessage,
    CanSignal,
    load_definitions,
    save_definitions,
)
from bakbrommer_twin.data_import.dbc import parse_dbc
from bakbrommer_twin.data_import.mapping import ColumnMap, LogMapping, MappingStore, suggest
from bakbrommer_twin.data_import.rawlog import RawLog
from bakbrommer_twin.data_import.recording import Recording, list_recordings

LOGS = SHIPPED_DATA / "example_logs"
CAN_FILE = SHIPPED_DATA / "can" / "bakbrommer_example.yaml"


def _example_csv() -> RawLog:
    frame = csv_log.read_table((LOGS / "example_ride_sd.csv").read_text(encoding="utf-8"))
    mapping = MappingStore(SHIPPED_DATA / "mappings").load("example_sd_card")
    return csv_log.apply_mapping(frame, mapping, "example_ride_sd.csv")


def _example_can(name: str) -> RawLog:
    frames, bad = can_log.parse((LOGS / name).read_text(encoding="utf-8"))
    assert bad == 0
    return can_log.decode_frames(frames, load_definitions(CAN_FILE), name)


# ---- CSV and mapping ------------------------------------------------------------------------

def test_csv_separator_and_decimal_comma_are_detected() -> None:
    plain = csv_log.read_table("# comment\nt, speed\n0, 1.5\n1, 2.5\n")
    european = csv_log.read_table("t;speed\n0;1,5\n1;2,5\n")
    tabbed = csv_log.read_table("t\tspeed\n0\t1.5\n1\t2.5\n")
    for frame in (plain, european, tabbed):
        assert list(frame.columns) == ["t", "speed"]
        assert frame["speed"].tolist() == [1.5, 2.5]


def test_mapping_converts_units_scale_and_offset() -> None:
    frame = csv_log.read_table("t_ms,spd,thr_adc,temp\n0,36,0,20\n500,72,4095,30\n")
    mapping = LogMapping(name="x", time_column="t_ms", time_unit="ms", columns=[
        ColumnMap(column="spd", channel="vehicle_speed", unit="km/h"),
        ColumnMap(column="thr_adc", channel="throttle", unit="-", scale=1 / 4095),
        ColumnMap(column="temp", channel="motor_temp_l", unit="°C", offset=-2.0)])
    log = csv_log.apply_mapping(frame, mapping, "test.csv")
    time, speed = log.channels["vehicle_speed"]
    assert time.tolist() == [0.0, 0.5] and speed.tolist() == pytest.approx([10.0, 20.0])
    assert log.channels["throttle"][1].tolist() == pytest.approx([0.0, 1.0])
    assert log.channels["motor_temp_l"][1].tolist() == pytest.approx([18.0, 28.0])


def test_mapping_errors_are_readable() -> None:
    with pytest.raises(ValueError, match="does not fit channel"):
        ColumnMap(column="spd", channel="vehicle_speed", unit="bar")
    with pytest.raises(ValueError, match="unknown channel"):
        ColumnMap(column="spd", channel="warp_speed", unit="km/h")
    frame = csv_log.read_table("t,a\n0,1\n")
    with pytest.raises(ValueError, match="time column 'time'"):
        csv_log.apply_mapping(frame, LogMapping(name="x", time_column="time"), "f")
    wrong = LogMapping(name="x", time_column="t", columns=[
        ColumnMap(column="b", channel="throttle", unit="%")])
    with pytest.raises(ValueError, match="mapped column 'b'"):
        csv_log.apply_mapping(frame, wrong, "f")


def test_suggestion_recognises_the_example_columns() -> None:
    frame = csv_log.read_table((LOGS / "example_ride_sd.csv").read_text(encoding="utf-8"))
    guess = suggest(list(frame.columns))
    saved = MappingStore(SHIPPED_DATA / "mappings").load("example_sd_card")
    assert (guess.time_column, guess.time_unit) == ("t_ms", "ms")
    assert {(c.column, c.channel, c.unit) for c in guess.columns} == {
        (c.column, c.channel, c.unit) for c in saved.columns}


def test_mapping_store_round_trip(tmp_path: Path) -> None:
    store = MappingStore(tmp_path)
    mapping = LogMapping(name="Mine", time_column="t", columns=[
        ColumnMap(column="v", channel="vehicle_speed", unit="km/h", scale=2.0)])
    store.save("mine", mapping)
    assert store.list_keys() == ["mine"] and store.load("mine") == mapping


def test_example_csv_reads_with_its_flaws_reported() -> None:
    log = _example_csv()
    assert len(log.channels) == 20
    assert any("unreadable" in note for note in log.notes)  # the empty cell
    assert log.channels["vehicle_speed"][1].max() > 200 / 3.6  # the 999.9 km/h glitch


# ---- CAN ------------------------------------------------------------------------------------

def test_signal_bit_layouts_follow_the_dbc_convention() -> None:
    data = bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0])
    intel = CanSignal(name="a", start_bit=0, length=16)
    assert intel.decode(data) == 0x3412
    motorola = CanSignal(name="b", start_bit=7, length=16, byte_order="big")
    assert motorola.decode(data) == 0x1234
    nibble = CanSignal(name="c", start_bit=12, length=4)  # high nibble of byte 1
    assert nibble.decode(data) == 0x3
    signed = CanSignal(name="d", start_bit=0, length=8, signed=True, scale=0.5, offset=1.0)
    assert signed.decode(bytes([0xFE])) == pytest.approx(-2 * 0.5 + 1.0)


@pytest.mark.parametrize("order", ["little", "big"])
def test_message_encode_decode_round_trip(order: str) -> None:
    starts = (0, 16, 40) if order == "little" else (7, 23, 47)
    message = CanMessage(id=0x321, name="M", signals=[
        CanSignal(name="a", start_bit=starts[0], length=16, byte_order=order, scale=0.1),
        CanSignal(name="b", start_bit=starts[1], length=12, byte_order=order, signed=True,
                  scale=0.5),
        CanSignal(name="c", start_bit=starts[2], length=8, byte_order=order, offset=-40.0)])
    values = {"a": 123.4, "b": -77.5, "c": 85.0}
    assert message.decode(message.encode(values)) == pytest.approx(values)
    clipped = message.decode(message.encode({"a": 1e9, "b": -1e9, "c": 0.0}))
    assert clipped["a"] == pytest.approx(6553.5) and clipped["b"] == pytest.approx(-1024.0)


def test_definition_file_round_trip_and_validation(tmp_path: Path) -> None:
    definitions = load_definitions(CAN_FILE)
    assert definitions.bitrate == 500_000 and len(definitions.messages) == 6
    save_definitions(tmp_path / "copy.yaml", definitions)
    assert load_definitions(tmp_path / "copy.yaml") == definitions
    with pytest.raises(ValueError, match="does not fit"):
        CanSignal(name="x", start_bit=0, length=8, unit="bar", channel="vehicle_speed")
    with pytest.raises(ValueError, match="same byte order"):
        CanMessage(id=1, name="M", signals=[
            CanSignal(name="a", start_bit=0, length=8),
            CanSignal(name="b", start_bit=15, length=8, byte_order="big")])


def test_candump_and_savvycan_hold_the_same_frames() -> None:
    dump_text = (LOGS / "example_ride_can.log").read_text(encoding="utf-8")
    savvy_text = (LOGS / "example_ride_savvycan.csv").read_text(encoding="utf-8")
    assert can_log.detect_format(dump_text) == "candump"
    assert can_log.detect_format(savvy_text) == "savvycan"
    assert can_log.detect_format("hello\nworld") == "unknown"
    dump, _ = can_log.parse(dump_text)
    savvy, _ = can_log.parse(savvy_text)
    assert len(dump) == len(savvy) > 10_000
    assert [(f.can_id, f.data) for f in dump[:500]] == [(f.can_id, f.data) for f in savvy[:500]]
    assert dump[100].time - dump[0].time == pytest.approx(savvy[100].time - savvy[0].time,
                                                         abs=1e-5)


def test_bad_lines_and_unknown_frames_are_counted_not_fatal() -> None:
    text = ("(100.000000) can0 101#E803000000000000\n"
            "garbage line\n"
            "(100.010000) can0 7FF#0102\n"
            "(100.020000) can0 101#D007000000000000\n")
    frames, bad = can_log.parse(text)
    assert len(frames) == 3 and bad == 1
    log = can_log.decode_frames(frames, load_definitions(CAN_FILE), "t")
    time, throttle = log.channels["throttle"]
    assert time.tolist() == pytest.approx([0.0, 0.02])
    assert throttle.tolist() == pytest.approx([0.10, 0.20])  # 1000 and 2000 × 0.01 %
    assert any("0x7FF" in note for note in log.notes)
    with pytest.raises(ValueError, match="neither"):
        can_log.parse("nothing useful")


def test_can_and_csv_example_agree() -> None:
    csv_recording, _ = clean.clean(_example_csv())
    can_recording, _ = clean.clean(_example_can("example_ride_can.log"))
    count = min(csv_recording.samples, can_recording.samples)
    for channel, tolerance in (("vehicle_speed", 0.02), ("battery_voltage", 0.15),
                               ("gyro_z", 0.01)):
        difference = csv_recording.data[channel][:count] - can_recording.data[channel][:count]
        assert np.nanpercentile(np.abs(difference), 95) < tolerance, channel


def test_dbc_conversion() -> None:
    text = '''
BO_ 258 SPEEDS: 8 VCU
 SG_ vehicle_speed : 0|16@1- (0.01,0) [-300|300] "km/h" Vector__XXX
 SG_ Odd_Unit : 16|8@1+ (1,0) [0|255] "furlongs" Vector__XXX
 SG_ Muxed m1 : 24|8@1+ (1,0) [0|255] "" Vector__XXX
BO_ 2147484160 EXTENDED: 2 VCU
 SG_ battery_voltage : 7|16@0+ (0.01,0) [0|100] "V" Vector__XXX
'''
    definitions, notes = parse_dbc(text, "from dbc")
    speeds, extended = definitions.messages
    assert speeds.id == 258 and extended.id == 0x200  # extended flag removed
    assert speeds.signals[0].channel == "vehicle_speed" and speeds.signals[0].signed
    assert speeds.signals[1].unit == "-" and speeds.signals[1].channel is None
    assert extended.signals[0].byte_order == "big"
    assert extended.decode(bytes([0x1A, 0x0A]))["battery_voltage"] == pytest.approx(66.66)
    assert any("multiplexed" in note for note in notes)
    assert any("furlongs" in note for note in notes)


# ---- cleaning -------------------------------------------------------------------------------

def test_cleaning_rejects_bad_values_and_reports_them() -> None:
    recording, report = clean.clean(_example_csv())
    quality = {q.channel: q for q in report}
    assert quality["vehicle_speed"].rejected == 1  # the 999.9 km/h sample
    assert np.nanmax(recording.data["vehicle_speed"]) < 60 / 3.6
    assert quality["vehicle_speed"].rate == pytest.approx(50.0, rel=0.01)
    assert all(q.coverage > 0.99 for q in report)
    assert recording.rate == 100.0 and 60.0 < recording.duration < 120.0


def test_gaps_are_left_empty_not_interpolated() -> None:
    recording, report = clean.clean(_example_can("example_ride_can.log"))
    quality = {q.channel: q for q in report}
    assert quality["battery_current"].gaps == 1
    assert quality["battery_current"].longest_gap == pytest.approx(1.55, abs=0.06)
    time = recording.time
    inside = (time > 30.1) & (time < 31.4)
    assert np.all(np.isnan(recording.data["battery_current"][inside]))
    assert np.all(np.isfinite(recording.data["vehicle_speed"][inside]))  # other channels fine
    assert 0.97 < recording.coverage("battery_current") < 0.99
    held = recording.filled("battery_current")
    assert np.all(np.isfinite(held))


def test_resampling_and_low_pass_filter() -> None:
    rng = np.random.default_rng(1)
    time = np.sort(rng.uniform(0.0, 10.0, 800))  # irregular sampling
    clean_signal = 10.0 + 3.0 * np.sin(2 * np.pi * 0.3 * time)
    raw = RawLog("t", {"vehicle_speed": (time, clean_signal + rng.normal(0, 0.5, len(time)))})
    unfiltered, _ = clean.clean(raw, clean.CleanOptions(rate_hz=50))
    filtered, _ = clean.clean(raw, clean.CleanOptions(rate_hz=50, lowpass_hz=1.5))
    truth = 10.0 + 3.0 * np.sin(2 * np.pi * 0.3 * (unfiltered.time + time[0]))
    middle = slice(50, -50)
    error_raw = np.nanstd(unfiltered.data["vehicle_speed"][middle] - truth[middle])
    error_filtered = np.nanstd(filtered.data["vehicle_speed"][middle] - truth[middle])
    assert error_filtered < 0.5 * error_raw
    lag = np.nanmean(filtered.data["vehicle_speed"][middle] - truth[middle])
    assert abs(lag) < 0.05  # zero-phase: no delay, no offset


def test_ride_mode_is_held_not_interpolated() -> None:
    raw = RawLog("t", {"ride_mode": (np.array([0.0, 1.0, 2.0]), np.array([0.0, 2.0, 2.0])),
                       "throttle": (np.array([0.0, 2.0]), np.array([0.0, 1.0]))})
    recording, _ = clean.clean(raw, clean.CleanOptions(rate_hz=10, gap_s=5))
    assert set(np.unique(recording.data["ride_mode"])) == {0.0, 2.0}  # never 1.0 in between
    assert recording.data["throttle"][10] == pytest.approx(0.5)


def test_time_alignment_finds_a_known_offset() -> None:
    csv_raw = _example_csv()
    can_raw = _example_can("example_ride_can.log").shifted(3.7)  # another clock
    offset = clean.align_offset(csv_raw, can_raw, "vehicle_speed")
    assert offset == pytest.approx(-3.7, abs=0.05)
    merged = csv_raw.merged(can_raw.shifted(offset))
    assert len(merged.channels["vehicle_speed"][0]) > len(csv_raw.channels["vehicle_speed"][0])
    with pytest.raises(ValueError, match="both logs need"):
        clean.align_offset(csv_raw, RawLog("x", {"throttle": can_raw.channels["throttle"]}),
                           "vehicle_speed")


def test_recording_save_and_load(tmp_path: Path) -> None:
    recording, _ = clean.clean(_example_csv())
    recording.synthetic = True
    recording.save(tmp_path, "example")
    assert list_recordings(tmp_path) == ["example"]
    loaded = Recording.load(tmp_path / "example")
    assert loaded.synthetic and loaded.rate == recording.rate
    assert np.array_equal(loaded.data["throttle"], recording.data["throttle"], equal_nan=True)
    with pytest.raises(ValueError, match="lower-case"):
        recording.save(tmp_path, "Bad Name")
