"""Whether the console sends HDR, as an Elgato HD60 X capture card sees it (Experimental).

Windows' camera driver describes the card's 10-bit P010 video the same way whether the console sends HDR10 or SDR
(BT.709, no transfer function), so the picture alone can't say how to read it: SDR read as HDR10 comes out too bright
and oversaturated, HDR10 read as SDR washed out. The card itself knows. It has a small vendor HID interface next to its
video and sound, through which Elgato's own apps read the HDMI input's state, and that's read here, the same way
Elgato's MIT-licensed sample code does (github.com/elgatosf/capture-device-support, ElgatoUVCDevice.cpp): an I2C read
of the card's microcontroller (address 0x55) through one HID output report and one input report. Nothing is written.

Which register: the sample reads 0x09, the HDMI HDR infoframe. On a real HD60 X with a PS5 that one keeps the last HDR
infoframe it got after the console leaves HDR (the PS5 stops sending it rather than sending one that says SDR), so it
says "PQ" with SDR video coming in. Register 0x00, the input signal, changes with every switch: width and height
(16-bit, little-endian, from byte 1 and 3), frame rate (byte 5), and byte 8, 1 while the console sends HDR and 0 in
SDR; all zero for a moment while the console switches (no signal). Found by watching every register while a PS5 turned
its HDR on and off (HD60 X Rev. 2, firmware 25.07.16). Anything that doesn't look like that is taken as "can't tell".

    python -m framegen.elgato        # what the card says, once a second until Ctrl+C
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

ELGATO = 0x0FD9
HD60_X = {0x0082: "HD60 X", 0x008A: "HD60 X Rev. 2"}  # the "new chip" HID protocol (Elgato's IsNewDeviceType)
MCU = 0x55
INPUT_STATUS = 0x00
POLL_S = 0.5


@dataclass(frozen=True)
class InputStatus:
    """The card's HDMI input: what the console sends. w == 0 means no signal (the console switching modes)."""
    w: int
    h: int
    fps: int
    hdr: bool

    @property
    def signal(self) -> bool:
        return self.w > 0


NO_SIGNAL = InputStatus(0, 0, 0, False)


def parse_input_status(data: bytes) -> InputStatus | None:
    """Register 0x00 as read: an InputStatus, NO_SIGNAL (all zero), or None when it doesn't look like the layout
    above (another card or firmware): then the card can't say."""
    if len(data) < 9:
        return None
    if not any(data[:9]):
        return NO_SIGNAL
    w, h, fps, flag = int.from_bytes(data[1:3], "little"), int.from_bytes(data[3:5], "little"), data[5], data[8]
    if not (320 <= w <= 7680 and 200 <= h <= 4320 and 20 <= fps <= 250 and flag in (0, 1)):
        return None
    return InputStatus(w, h, fps, flag == 1)


class Hd60x:
    """An Elgato HD60 X's vendor HID interface, for reading its microcontroller's registers. open() -> None when
    there's no HD60 X (or more than one, as which goes with which video device can't be told)."""

    def __init__(self, handle, name: str, out_len: int) -> None:
        self._h, self.name, self._out_len = handle, name, out_len
        self._lock = threading.Lock()

    @classmethod
    def open(cls) -> "Hd60x | None":
        if sys.platform != "win32":
            return None
        import ctypes
        from ctypes import wintypes as wt
        hid, cfg = ctypes.WinDLL("hid"), ctypes.WinDLL("cfgmgr32")
        k32 = ctypes.WinDLL("kernel32")
        k32.CreateFileW.restype = wt.HANDLE
        k32.CreateFileW.argtypes = (wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.HANDLE)
        k32.CloseHandle.argtypes = (wt.HANDLE,)

        class Guid(ctypes.Structure):
            _fields_ = [("d1", wt.DWORD), ("d2", wt.WORD), ("d3", wt.WORD), ("d4", ctypes.c_ubyte * 8)]

        class Attributes(ctypes.Structure):
            _fields_ = [("Size", wt.ULONG), ("VendorID", wt.USHORT), ("ProductID", wt.USHORT),
                        ("Version", wt.USHORT)]

        guid = Guid()
        hid.HidD_GetHidGuid(ctypes.byref(guid))
        size = wt.ULONG()
        if cfg.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(guid), None, 0) != 0:
            return None
        buf = ctypes.create_unicode_buffer(max(1, size.value))
        if cfg.CM_Get_Device_Interface_ListW(ctypes.byref(guid), None, buf, size.value, 0) != 0:
            return None
        found = []
        for path in (p for p in buf[:size.value].split("\0") if f"vid_{ELGATO:04x}" in p.lower()):
            h = k32.CreateFileW(path, 0xC0000000, 3, None, 3, 0, None)  # read/write, shared, OPEN_EXISTING
            if not h or h == wt.HANDLE(-1).value:
                continue
            a = Attributes(Size=ctypes.sizeof(Attributes))
            if hid.HidD_GetAttributes(h, ctypes.byref(a)) and a.ProductID in HD60_X:
                pre = ctypes.c_void_p()
                caps = (ctypes.c_ushort * 32)()  # HIDP_CAPS: usage, usage page, input/output report lengths, ...
                if hid.HidD_GetPreparsedData(h, ctypes.byref(pre)):
                    hid.HidP_GetCaps(pre, caps)
                    hid.HidD_FreePreparsedData(pre)
                if caps[3] >= 8:
                    found.append((h, HD60_X[a.ProductID], caps[3]))
                    continue
            k32.CloseHandle(h)
        if len(found) != 1:
            for h, _, _ in found:
                k32.CloseHandle(h)
            return None
        card = cls(*found[0])
        card._hid, card._k32 = hid, k32
        return card

    def read(self, register: int, n: int = 32) -> bytes | None:
        """n bytes of an MCU register, or None if the card didn't answer. Report 6 out: [length, 7 = I2C read,
        address, 1 byte written (the register), the register, bytes to read]; report 5 in, its length carrying the
        report case (7) in its high byte, as Elgato's code sends it."""
        import ctypes
        with self._lock:
            if self._h is None:
                return None
            out = (ctypes.c_ubyte * self._out_len)(6, 6, 7, MCU, 1, register, n)
            if not self._hid.HidD_SetOutputReport(self._h, out, self._out_len):
                return None
            size = 0xFF | (7 << 8)
            inp = (ctypes.c_ubyte * size)(5)
            if not self._hid.HidD_GetInputReport(self._h, inp, size):
                return None
            return bytes(inp[1:1 + n])

    def input_status(self) -> InputStatus | None:
        data = self.read(INPUT_STATUS)
        return parse_input_status(data) if data is not None else None

    def close(self) -> None:
        with self._lock:
            if self._h is not None:
                self._k32.CloseHandle(self._h)
                self._h = None


class HdrWatch:
    """Whether the console sends HDR, kept up to date from the card on a thread (every POLL_S). hdr: the last the
    card said with a signal coming in (a switch's moment without one changes nothing). Callable: watch() -> bool.
    open(video device name) -> None unless that's an Elgato HD60 X whose input it can read."""

    def __init__(self, card, first: InputStatus, poll_s: float = POLL_S, log=print) -> None:
        self.card, self.poll_s, self.log = card, poll_s, log
        self.hdr = first.hdr
        self.status = first
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True, name="elgato-hdr").start()

    @classmethod
    def open(cls, video_device: str, log=print) -> "HdrWatch | None":
        if "hd60 x" not in video_device.lower():
            return None
        try:
            card = Hd60x.open()
        except OSError:
            return None
        if card is None:
            return None
        first = card.input_status()
        if first is None:  # not the layout this was written for: can't tell
            card.close()
            return None
        return cls(card, first, log=log)

    def __call__(self) -> bool:
        return self.hdr

    def describe(self) -> str:
        s = self.status
        if not s.signal:
            return "no signal from the console yet"
        return f"the console sends {s.w}x{s.h} at {s.fps} Hz in {'HDR' if s.hdr else 'SDR'}"

    def _run(self) -> None:
        while not self._stop.wait(self.poll_s):
            try:
                s = self.card.input_status()
            except Exception:  # noqa: BLE001 - the card went away: keep the last answer
                s = None
            if s is None or not s.signal:
                continue
            self.status = s
            if s.hdr != self.hdr:
                self.hdr = s.hdr
                self.log(f"[capture] the console switched to {'HDR' if s.hdr else 'SDR'}: the picture is now read as "
                         f"{'HDR10' if s.hdr else 'SDR'}")

    def close(self) -> None:
        self._stop.set()
        self.card.close()


def main() -> int:
    card = Hd60x.open()
    if card is None:
        print("no Elgato HD60 X found (or more than one)")
        return 1
    print(f"Elgato {card.name}")
    try:
        while True:
            data = card.read(INPUT_STATUS)
            s = parse_input_status(data) if data is not None else None
            what = ("no answer" if data is None else "can't tell: " + data[:9].hex() if s is None else
                    "no signal" if not s.signal else f"{s.w}x{s.h} {s.fps} Hz {'HDR' if s.hdr else 'SDR'}")
            print(time.strftime("%H:%M:%S"), what, flush=True)
            time.sleep(1.0)
    except KeyboardInterrupt:
        return 0
    finally:
        card.close()


if __name__ == "__main__":
    sys.exit(main())
