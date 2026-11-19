"""Sound from a capture card, played in step with SmoovPlay's picture.

A capture card's sound comes in as its own DirectShow audio device, read with the video (framegen/capture.py). It's
played here on the PC's default output, through WASAPI (sounddevice, which bundles PortAudio), held back by as long
as the picture spends in SmoovPlay, so the two line up: set_delay(), which the pipeline calls every couple of
seconds (Sound in sync), as it does for chiaki-ng's sound.

DelayLine is the part that matters and needs no sound card: PCM goes in as it arrives and comes out at the
output's pace, with the queue kept at the delay. Near it, the sound plays half a percent faster or slower until it's
back, which nobody hears, so the card's clock and the output's can drift apart without the delay creeping; further
off (a change in the picture's delay, or sound that came in a burst) one percent. Only far off (over JUMP_S: at the
start, or a big change) it jumps: silence until it has filled, or the oldest sound skipped. Wherever the sound
doesn't follow on (a jump, or a gap because nothing had come), it's eased over FADE_S instead of stepping, as a
step is heard as a click.

The queue never goes below the longest recent packet plus CUSHION_S, nor below the longest recent wait between
packets plus CUSHION_S. Sound comes in packets (20 ms from a card), and with less queued than the wait for the next
one the output runs dry: a gap of silence every packet or so, heard as clicks as loud as the sound around them
(issue 17, an Elgato HD60 X with a picture delay of 31 ms). Packets also come late when the thread reading the
card is held up for a moment (a heavy game keeps SmoovPlay busier), so the cushion grows to the longest wait of the
last GAP_WINDOW_S, up to MAX_WAIT_KEEP_S. Then the sound is a little later than the picture instead, which is hard
to notice.

Player hands the sound to Windows with OUTPUT_S buffered, so the output's callback (Python, which waits its turn
with SmoovPlay's other threads) can be held up that long without Windows playing a gap; that buffer is taken off
the delay. stats() counts each kind of trouble for the log (framegen/capture.py: once a minute when something
happened, and when the session ends), so diagnostics say which one it was.
"""
from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np

JUMP_S = 0.120  # further than this from the delay: jump to it
NUDGE_S = 0.004  # further than this: half a percent faster or slower until it's back
NUDGE = 0.005
FAR_S = 0.020  # further than this: one percent (100 ms takes 10 s)
FAR_NUDGE = 0.01
MAX_S = 1.5  # never queue more than this
CUSHION_S = 0.010  # always queued on top of the longest recent packet or wait, for packets that come a little late
GAP_WINDOW_S = 60.0  # the longest wait between packets this long ago or less sets the cushion
MAX_WAIT_KEEP_S = 0.150  # but never more than this
STOP_S = 0.5  # a longer wait is the sound stopping (the card lost the picture, say), not a hold-up
FADE_S = 0.002  # where the sound doesn't follow on, eased over this
OUTPUT_S = 0.040  # Windows' own buffer (sounddevice's "low" is about 10 ms: too little when Python is busy)


def _ramp(k: int) -> np.ndarray:
    """1 down towards 0 over k sample frames, as a column."""
    return np.linspace(1.0, 0.0, k, endpoint=False, dtype=np.float32)[:, None]


class DelayLine:
    """Thread-safe: push() from the reader's thread, pull() from the output's (one thread). clock: for tests."""

    def __init__(self, rate: int, channels: int, sample_bytes: int = 2, clock=time.perf_counter) -> None:
        self.rate, self.channels = rate, channels
        self.frame = channels * sample_bytes  # bytes per sample frame (all channels)
        self._buf = bytearray()
        self._lock = threading.Lock()
        self._clock = clock
        self.target = 0  # bytes to keep queued (asked for: see _keep)
        self._packets: deque = deque(maxlen=50)  # the last packets' sizes, in bytes (a second of a card's)
        self._waits: deque = deque()  # (time, wait since the packet before), falling: the first is the longest
        self._last_in: float | None = None
        self.underruns = 0  # times it ran dry (a gap, eased): nothing had arrived
        self.skips = 0  # far too much queued: the oldest sound skipped
        self.refills = 0  # far too little (a long hold-up, or a longer delay): silent until it's back
        self.stops = 0  # waits of over STOP_S between packets
        self.longest_wait_s = 0.0  # the longest wait between packets (short of a stop), all session
        self._filling = True  # silent until the queue reaches the delay
        self._seam = False  # the next block doesn't follow on from the last: eased from where that ended
        self._last = np.zeros(channels, np.float32)  # the last sample frame played
        self._fade = max(1, int(round(FADE_S * rate)))

    @property
    def jumps(self) -> int:
        return self.skips + self.refills

    def _bytes(self, seconds: float) -> int:
        return max(0, int(round(seconds * self.rate))) * self.frame

    def set_delay(self, seconds: float) -> None:
        with self._lock:
            self.target = min(self._bytes(seconds), self._bytes(MAX_S - JUMP_S))

    @property
    def queued_s(self) -> float:
        return len(self._buf) / self.frame / self.rate

    def _keep(self) -> int:
        """Bytes to keep queued: the delay asked for, but never less than the longest recent packet or wait between
        packets, and a cushion (with the lock held)."""
        packet = min(max(self._packets, default=0) + self._bytes(CUSHION_S), self._bytes(MAX_S / 2))
        wait = self._bytes(min(self._waits[0][1] + CUSHION_S, MAX_WAIT_KEEP_S)) if self._waits else 0
        return max(self.target, packet, wait)

    @property
    def kept_s(self) -> float:
        """The delay the queue is kept at, in seconds (more than asked for when that's too short to play smoothly)."""
        with self._lock:
            return self._keep() / self.frame / self.rate

    def push(self, pcm: bytes) -> None:
        now = self._clock()
        with self._lock:
            if self._last_in is not None:
                wait = now - self._last_in
                if wait > STOP_S:
                    self.stops += 1
                else:
                    self.longest_wait_s = max(self.longest_wait_s, wait)
                    while self._waits and self._waits[-1][1] <= wait:  # (a shorter, older wait never counts again)
                        self._waits.pop()
                    self._waits.append((now, wait))
            self._last_in = now
            while self._waits and self._waits[0][0] < now - GAP_WINDOW_S:
                self._waits.popleft()
            self._packets.append(len(pcm) - len(pcm) % self.frame)
            self._buf += pcm
            over = len(self._buf) - self._bytes(MAX_S)
            if over > 0:
                del self._buf[:over + -over % self.frame]  # (whole sample frames)

    def pull(self, n: int) -> bytes:
        """n bytes (whole sample frames) for the output."""
        nf = n // self.frame
        with self._lock:
            err = len(self._buf) - self._keep()  # how far ahead of the delay the queue is
            jump = self._bytes(JUMP_S)
            if err < -jump and not self._filling:  # too little queued (a long hold-up, or a longer delay): refill
                self._filling = True
                self.refills += 1
            if self._filling:
                if err < 0:
                    return self._silence(nf)
                self._filling = False
                self._seam = True
            if err > jump:  # too much: skip the oldest sound
                del self._buf[:err]
                self.skips += 1
                self._seam = True
                err = 0
            speed = (FAR_NUDGE if abs(err) > self._bytes(FAR_S) else NUDGE if abs(err) > self._bytes(NUDGE_S) else 0)
            take = (nf if not speed else max(nf + 1, round(nf * (1 + speed))) if err > 0 else
                    min(nf - 1, round(nf * (1 - speed))))
            take = max(1, take)
            chunk = bytes(self._buf[:take * self.frame])
            del self._buf[:take * self.frame]
            if len(chunk) < take * self.frame:  # ran dry: one gap, then silent until it's back to the delay (as
                self.underruns += 1  # it was, playing on from almost nothing ran dry again and again)
                self._filling = True
            seam, self._seam = self._seam, False
        got = len(chunk) // self.frame
        if got == take == nf and not seam:  # (nearly always)
            self._last = np.frombuffer(chunk[-self.frame:], np.int16).astype(np.float32)
            return chunk
        a = np.frombuffer(chunk, np.int16).reshape(got, self.channels).astype(np.float32)
        if seam and got:  # from where the last block ended into this one
            k = min(self._fade, got)
            a[:k] += (self._last - a[0]) * _ramp(k)
        if got < take:  # ran dry: eased down into silence (and up from it when the sound's back: _seam)
            pad = np.zeros((take - got, self.channels), np.float32)
            k = min(self._fade, take - got)
            pad[:k] = (a[-1] if got else self._last) * _ramp(k)
            a = np.concatenate([a, pad])
        if take != nf:  # played a little faster (more in than out) or slower: stretched to n bytes
            x = np.linspace(0, take - 1, nf)
            a = np.stack([np.interp(x, np.arange(take), a[:, ch]) for ch in range(self.channels)], axis=1)
        self._last = a[-1].astype(np.float32)
        return np.clip(np.round(a), -32768, 32767).astype(np.int16).tobytes()

    def _silence(self, nf: int) -> bytes:
        """Silent while filling, eased down from the last sound played (with the lock held)."""
        if not self._last.any():
            return bytes(nf * self.frame)
        a = np.zeros((nf, self.channels), np.float32)
        k = min(self._fade, nf)
        a[:k] = self._last * _ramp(k)
        self._last = a[-1].copy()
        return np.round(a).astype(np.int16).tobytes()

    def stats(self) -> dict:
        """Counts for the log (sound_report)."""
        with self._lock:
            kept = self._keep() / self.frame / self.rate
        return {"ran_dry": self.underruns, "skips": self.skips, "refills": self.refills, "stops": self.stops,
                "longest_wait_ms": round(self.longest_wait_s * 1000), "kept_ms": round(kept * 1000)}


COUNTS = ("ran_dry", "output_short", "skips", "refills", "stops")


def sound_report(stats: dict, since: dict | None = None) -> str | None:
    """A line for the log from stats(): all of it (since None), or what happened after `since`, None if nothing."""
    d = {k: stats.get(k, 0) - (since or {}).get(k, 0) for k in COUNTS}
    if since is not None and not any(d.values()):
        return None
    out = (f"ran dry {d['ran_dry']} times, Windows' output ran short {d['output_short']} times, "
           f"skipped ahead {d['skips']} times, went quiet to catch up {d['refills']} times")
    if d["stops"]:
        out += f", stopped coming {d['stops']} times"
    out += f"; longest wait between the card's sound packets {stats.get('longest_wait_ms', 0)} ms"
    if "longest_call_ms" in stats:
        out += f", for Windows' calls {stats['longest_call_ms']} ms"
    out += f"; held back {stats.get('kept_ms', 0)} ms"
    if "output_ms" in stats:
        out += f" (and Windows' buffer {stats['output_ms']} ms)"
    return out


def wasapi_output() -> int | None:
    """The default output device under WASAPI (lower and steadier delay than MME, PortAudio's default)."""
    import sounddevice as sd
    for api in sd.query_hostapis():
        if "WASAPI" in api["name"] and api["default_output_device"] >= 0:
            return api["default_output_device"]
    return None


class Player:
    """Plays a DelayLine on the default output (16-bit PCM). latency: the output's own delay, in seconds, which
    set_delay() takes off so the total is what was asked for."""

    def __init__(self, rate: int, channels: int, device: int | None = None, buffer_s: float | str = OUTPUT_S) -> None:
        import sounddevice as sd
        self.line = DelayLine(rate, channels)
        self.short = 0  # times the output ran short: a call for sound came later than Windows' buffer lasts
        self.longest_call_s = 0.0  # the longest wait between Windows' calls for sound
        self._called: float | None = None
        self.latency = 1.0  # (until it's known)
        dev = wasapi_output() if device is None else device
        extra = sd.WasapiSettings(auto_convert=True) if dev is not None else None  # the card's rate, whatever Windows mixes at
        self.stream = sd.RawOutputStream(samplerate=rate, channels=channels, dtype="int16", device=dev,
                                         latency=buffer_s, extra_settings=extra, callback=self._play)
        self.stream.start()
        self.latency = float(self.stream.latency)

    def _play(self, outdata, frames, time_info, status) -> None:  # on PortAudio's thread
        # Windows' flag for this (PortAudio's output_underflow) didn't come once in a test where the calls came
        # 40 ms apart with a 23 ms buffer, so a late call counts too.
        now = time.perf_counter()
        late = False
        if self._called is not None:
            wait = now - self._called
            self.longest_call_s = max(self.longest_call_s, wait)
            late = wait > self.latency
        self._called = now
        if late or getattr(status, "output_underflow", False):
            self.short += 1
        outdata[:] = self.line.pull(frames * self.line.frame)

    def push(self, pcm: bytes) -> None:
        self.line.push(pcm)

    def set_delay(self, seconds: float) -> None:
        self.line.set_delay(seconds - self.latency)

    def stats(self) -> dict:
        return {**self.line.stats(), "output_short": self.short, "longest_call_ms": round(self.longest_call_s * 1000),
                "output_ms": round(self.latency * 1000)}

    def close(self) -> None:
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:  # noqa: BLE001 - closing
            pass
