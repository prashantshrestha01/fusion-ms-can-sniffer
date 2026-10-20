#!/usr/bin/env python3
"""can_diff.py — diff two MS-CAN sniffer captures and find your button.

The sniffer logs every frame with a millisecond timestamp; pressing a dash
control changes the *data bytes* (or introduces a new ID) for that control's
message. This script ignores the timestamps, compares baseline vs. action
captures, and reports:

  1. IDs whose data bytes changed vs. baseline (most likely your button)
  2. IDs that appear only in the action capture
  3. A per-byte change breakdown for the changed IDs

Cross-references hits against the key 2011 Fusion MS-CAN IDs from the
ms-can-dbc-roadmap.md (opendbc ford_cgea1_2_bodycan_2011.dbc).

Usage:
    python3 can_diff.py baseline.log ac_button.log
    python3 can_diff.py baseline.log fan_up.log fan_down.log   # several actions, diffed one by one

Logs are the raw serial-monitor captures — banner lines, stats lines and the
"NEW" first-seen markers are all handled.
"""

import re
import sys
from collections import Counter

# [12345ms] NEW ID:0x398 DLC:8 12 34 ...  /  ID:0x00000123(ext)  /  trailing " RTR"
FRAME_RE = re.compile(
    r"\[(\d+)ms\]\s*(NEW\s+)?ID:0x([0-9a-fA-F]{3,8})(\(ext\))?\s+DLC:(\d+)(?:\s+RTR)?\s*((?:[0-9a-fA-F]{2}\s*)*)$"
)

# Key 2011 Fusion MS-CAN IDs (from opendbc ford_cgea1_2_bodycan_2011.dbc —
# see files/ms-can-dbc-roadmap.md for the full 102-message table).
KNOWN_IDS = {
    0x132: "Driver_Lock_Sw_StatM (lock switch + key cylinder)",
    0x136: "Driver_Door_Lock_CmdM (LOCK COMMAND — replay target)",
    0x2E0: "FCIM_Button_Press",
    0x326: "Compressor_Req (A/C request bit)",
    0x355: "EFP_CC_Status_MS (temp setpoints, AC/recirc/mode requests)",
    0x356: "EFP_CC_Seat_Req_Stat_MS (blower, heated/cooled seats)",
    0x357: "RCCM_CC_Status (blower/temp/mode states)",
    0x35B: "MFD_CC_Status_MS (rear mode buttons)",
    0x35C: "EFP_CC_Info_Status_MS (A/C, recirc, defrost, AUTO, fan bars)",
    0x384: "Vehicle_Access_RqstM (passive-entry / lock requests)",
    0x385: "Vehicle_Lock_Status (lock status + event counter)",
    0x386: "Remote_Start (remote-start request — phone-start project)",
    0x387: "CC_FCIM_Update (indicator lamps: AC, mode, defrost, seats)",
    0x398: "FCIM_CC_Status (PHYSICAL DASH BUTTONS — best ID to watch)",
    0x399: "Nav_CC_Status (touchscreen climate buttons)",
    0x39A: "VoiceRec_CC_Request (voice climate commands)",
    0x3A0: "Ignition_Switch_PositionM (ignition + remote-start status)",
    0x3B1: "Ajar_Stat (door/hood/decklid ajar bits — bus sanity check)",
    0x3B2: "Body_Information_5_MS (A/C clutch, coolant fan, refrig. pressure)",
    0x3C8: "EATC_FDM_Info_Status (displayed temps, fan speed)",
    0x41A: "Climate_Control_Data (in-car/outside/evap temps)",
}


def parse(path):
    """Parse a sniffer capture -> {id_int: {'count', 'datas' Counter, 'ext', 'dlc'}}."""
    ids = {}
    frames = 0
    with open(path, "r", errors="replace") as f:
        for line in f:
            m = FRAME_RE.search(line)
            if not m:
                continue
            frames += 1
            id_int = int(m.group(3), 16)
            ext = m.group(4) is not None
            dlc = int(m.group(5))
            data = bytes(int(b, 16) for b in m.group(6).split()) if m.group(6).strip() else b""
            e = ids.setdefault(id_int, {"count": 0, "datas": Counter(), "ext": ext, "dlc": set()})
            e["count"] += 1
            e["datas"][data] += 1
            e["ext"] = e["ext"] or ext
            e["dlc"].add(dlc)
    return ids, frames


def fmt_bytes(b):
    return " ".join(f"{x:02X}" for x in b) if b else "(no data)"


def id_label(id_int, ext):
    name = KNOWN_IDS.get(id_int, "")
    return f"0x{id_int:03X} ({id_int}){' ext' if ext else ''}" + (f" — {name}" if name else "")


def diff(baseline, action):
    """Return (changed, new_ids): changed = [(id, entry, ref_bytes, byte_changes)]."""
    changed, new_ids = [], []
    for id_int, a in action.items():
        b = baseline.get(id_int)
        if b is None:
            new_ids.append((id_int, a))
            continue
        new_datas = [d for d in a["datas"] if d not in b["datas"]]
        if not new_datas:
            continue
        # Reference = most common baseline data (handles length changes gracefully).
        ref = b["datas"].most_common(1)[0][0]
        # Per-byte: which positions changed, old->new values, in how many action frames.
        byte_changes = {}
        for d in new_datas:
            n = max(len(ref), len(d))
            for i in range(n):
                old = ref[i] if i < len(ref) else None
                new = d[i] if i < len(d) else None
                if old != new:
                    key = (i, old, new)
                    byte_changes[key] = byte_changes.get(key, 0) + a["datas"][d]
        changed.append((id_int, a, ref, byte_changes, sum(a["datas"][d] for d in new_datas)))
    return changed, new_ids


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    base_path, action_paths = argv[1], argv[2:]
    try:
        base_ids, base_frames = parse(base_path)
    except OSError as e:
        print(f"error: cannot read {base_path}: {e}")
        return 1

    for action_path in action_paths:
        try:
            act_ids, act_frames = parse(action_path)
        except OSError as e:
            print(f"error: cannot read {action_path}: {e}")
            continue

        print(f"=== {base_path}  vs  {action_path} ===")
        print(f"baseline: {base_frames} frames, {len(base_ids)} IDs  ·  "
              f"action: {act_frames} frames, {len(act_ids)} IDs\n")

        changed, new_ids = diff(base_ids, act_ids)

        if not changed and not new_ids:
            print("No new IDs and no data changes — the control did not alter "
                  "MS-CAN traffic in this capture.\n"
                  "Tips: longer action capture (15 s), press the button once at the "
                  "start, check ignition was ON, confirm you're on pins 3/11.")
        if changed:
            print(f"CHANGED DATA ({len(changed)}) — most likely your button:\n")
            for id_int, a, ref, byte_changes, n_new in sorted(changed, key=lambda x: -x[4]):
                print(f"  {id_label(id_int, a['ext'])}")
                print(f"    frames in action: {a['count']} "
                      f"({n_new} with data never seen in baseline)")
                print(f"    baseline bytes:   {fmt_bytes(ref)}")
                for (pos, old, new), cnt in sorted(byte_changes.items(), key=lambda x: (-x[1], x[0][0])):
                    old_s = f"{old:02X}" if old is not None else "--"
                    new_s = f"{new:02X}" if new is not None else "--"
                    print(f"    byte {pos}: {old_s} -> {new_s}   (in {cnt}/{a['count']} frames)")
                print()
        if new_ids:
            print(f"NEW IDs in action capture ({len(new_ids)}):\n")
            for id_int, a in sorted(new_ids, key=lambda x: -x[1]["count"]):
                sample = a["datas"].most_common(1)[0][0]
                print(f"  {id_label(id_int, a['ext'])}")
                print(f"    {a['count']} frames · data: {fmt_bytes(sample)}\n")

        unchanged = len(act_ids) - len(changed) - len(new_ids)
        print(f"({unchanged} IDs identical to baseline — omitted.)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
