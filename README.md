# radiator.exe

Heats your computer up.

![green on black terminal UI with CPU/GPU temperature readouts and a progress bar](screenshot.png)

---

## What it does

Opens a green-on-black terminal UI that:

- Stress tests every CPU core simultaneously using separate processes (bypasses Python's GIL for true multi-core load)
- Stress tests the GPU via heavy numpy matrix operations
- Displays live CPU and GPU temperatures
- Displays live CPU and GPU load bars
- Shows a progress bar filling toward a target temperature of 90°C
- Progress bar turns amber at 85% of target, red when target is reached
- Keeps going until you press **[ STOP HEATING ]**

---

## Requirements

- Python 3.8+
- psutil
- GPUtil
- numpy

Install dependencies:

```
py -m pip install psutil GPUtil numpy
```

---

## Usage

```
py radiator.py
```

---

## Notes

- **CPU temperature** readings work on Linux and macOS out of the box. On Windows, `psutil` may not have sensor access depending on your hardware — if CPU TEMP shows `N/A`, the stress load is still working, you just won't see the number.
- **GPU temperature** requires an Nvidia GPU and the `GPUtil` package. AMD/Intel GPUs will show `N/A`.
- The progress bar uses an assumed idle baseline of ~35°C. If your machine runs hotter at idle, the bar will start partially filled.
- Closing the window terminates all stress processes immediately.

---

## Why

Because sometimes you want your fans to spin.
